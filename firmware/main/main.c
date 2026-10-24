/*
 * WiFi Sentinel v0.1.0
 * Receive-only 802.11 management-frame telemetry for ESP32-C5.
 * No esp_wifi_80211_tx, association, injection, or radio jamming functions.
 *
 * Requires Espressif ESP-IDF v5.5.2+ targeting esp32c5.
 * Hardware validation on the specific eBeetle 2 PCB remains necessary.
 */
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

static const char *TAG = "wids";
#define RX_QUEUE_DEPTH 192
#define MAX_SSID_LEN 32
#define MGMT_HDR_LEN 24

typedef struct {
    uint8_t subtype;
    uint8_t addr1[6];
    uint8_t addr2[6];
    uint8_t bssid[6];
    uint8_t ssid[MAX_SSID_LEN + 1];
    int8_t rssi;
    uint8_t channel;
    bool protected_frame;
    int32_t reason_code;
    int32_t status_code;
    uint32_t uptime_ms;
} rx_frame_t;

static QueueHandle_t s_queue = NULL;
static volatile uint32_t s_dropped = 0;
static volatile uint32_t s_captured = 0;
static uint32_t s_beacon_counter = 0;

static const char *subtype_name(uint8_t subtype)
{
    switch (subtype) {
        case 0:  return "assoc_req";
        case 1:  return "assoc_resp";
        case 2:  return "reassoc_req";
        case 3:  return "reassoc_resp";
        case 5:  return "probe_resp";
        case 8:  return "beacon";
        case 10: return "disassoc";
        case 11: return "auth";
        case 12: return "deauth";
        default: return NULL;
    }
}

static uint16_t le16(const uint8_t *input)
{
    return (uint16_t)input[0] | ((uint16_t)input[1] << 8);
}

static void extract_ssid(rx_frame_t *out, const uint8_t *data, size_t length)
{
    /* Beacons/probe responses have 12 fixed bytes after the 24-byte header. */
    size_t position = MGMT_HDR_LEN + 12;
    while (position + 2 <= length) {
        uint8_t id = data[position++];
        uint8_t size = data[position++];
        if (position + size > length) return;  /* Malformed IE */
        if (id == 0) {
            if (size > MAX_SSID_LEN) return;
            for (uint8_t i = 0; i < size; i++) {
                /* Avoid embedding raw control codes in the NDJSON transport. */
                uint8_t ch = data[position + i];
                out->ssid[i] = (ch >= 32 && ch <= 126) ? ch : '_';
            }
            out->ssid[size] = '\0';
            return;
        }
        position += size;
    }
}

/* Called from the Wi-Fi receive task, not an ISR. Never block or print here. */
static void rx_callback(void *buffer, wifi_promiscuous_pkt_type_t type)
{
    if (type != WIFI_PKT_MGMT || !s_queue) return;
    const wifi_promiscuous_pkt_t *packet = (const wifi_promiscuous_pkt_t *)buffer;
    size_t length = packet->rx_ctrl.sig_len;
    if (length < MGMT_HDR_LEN) return;
    const uint8_t *bytes = packet->payload;
    if (((bytes[0] >> 2) & 0x03) != 0) return; /* Only management frames */

    uint8_t subtype = (bytes[0] >> 4) & 0x0f;
    if (!subtype_name(subtype)) return;
    if (subtype == 8 || subtype == 5) {
        s_beacon_counter++;
        if (s_beacon_counter % CONFIG_WIDS_BEACON_SAMPLE_N) return;
    }

    rx_frame_t output = {0};
    output.subtype = subtype;
    output.rssi = packet->rx_ctrl.rssi;
    output.channel = packet->rx_ctrl.channel;
    output.protected_frame = (bytes[1] & 0x40) != 0;
    output.reason_code = -1;
    output.status_code = -1;
    output.uptime_ms = (uint32_t)(esp_timer_get_time() / 1000);
    memcpy(output.addr1, bytes + 4, 6);
    memcpy(output.addr2, bytes + 10, 6);
    memcpy(output.bssid, bytes + 16, 6);

    /* PMF-protected management bodies are encrypted; do not interpret reason. */
    if (!output.protected_frame && (subtype == 10 || subtype == 12) && length >= 26) {
        output.reason_code = le16(bytes + 24);
    }
    if (!output.protected_frame && subtype == 11 && length >= 30) {
        output.status_code = le16(bytes + 28); /* Authentication status */
    }
    if (!output.protected_frame && (subtype == 1 || subtype == 3) && length >= 28) {
        output.status_code = le16(bytes + 26); /* Association response status */
    }
    if ((subtype == 8 || subtype == 5) && length >= MGMT_HDR_LEN + 12) {
        extract_ssid(&output, bytes, length);
    }

    __atomic_fetch_add(&s_captured, 1, __ATOMIC_RELAXED);
    if (xQueueSend(s_queue, &output, 0) != pdTRUE) {
        __atomic_fetch_add(&s_dropped, 1, __ATOMIC_RELAXED);
    }
}

static void json_string(const char *str)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)str; *p; ++p) {
        if (*p == '"' || *p == '\\') putchar('\\');
        putchar(*p);
    }
    putchar('"');
}

static void emit_mac(const uint8_t mac[6])
{
    printf("%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2],
           mac[3], mac[4], mac[5]);
}

static void report_frame(const rx_frame_t *frame)
{
    printf("WIDS {\"v\":1,\"kind\":\"frame\",\"sensor_id\":");
    json_string(CONFIG_WIDS_SENSOR_ID);
    printf(",\"channel\":%u,\"subtype\":\"%s\",\"sa\":\"", frame->channel,
           subtype_name(frame->subtype));
    emit_mac(frame->addr2);
    printf("\",\"da\":\"");
    emit_mac(frame->addr1);
    printf("\",\"bssid\":\"");
    emit_mac(frame->bssid);
    printf("\",\"rssi\":%d,\"protected\":%s,\"reason_code\":%" PRId32
           ",\"status_code\":%" PRId32 ",\"ssid\":", frame->rssi,
           frame->protected_frame ? "true" : "false", frame->reason_code, frame->status_code);
    if (frame->ssid[0]) json_string((const char *)frame->ssid);
    else printf("null");
    printf(",\"uptime_ms\":%" PRIu32 "}\n", frame->uptime_ms);
    fflush(stdout);
}

static void report_heartbeat(void)
{
    printf("WIDS {\"v\":1,\"kind\":\"heartbeat\",\"sensor_id\":");
    json_string(CONFIG_WIDS_SENSOR_ID);
    printf(",\"channel\":%d,\"uptime_ms\":%" PRIu32
           ",\"captured\":%" PRIu32 ",\"dropped\":%" PRIu32 "}\n",
           CONFIG_WIDS_CHANNEL, (uint32_t)(esp_timer_get_time() / 1000),
           __atomic_load_n(&s_captured, __ATOMIC_RELAXED),
           __atomic_load_n(&s_dropped, __ATOMIC_RELAXED));
    fflush(stdout);
}

static void export_task(void *context)
{
    (void)context;
    rx_frame_t frame;
    TickType_t last_heartbeat = xTaskGetTickCount();
    for (;;) {
        if (xQueueReceive(s_queue, &frame, pdMS_TO_TICKS(1000)) == pdTRUE) {
            report_frame(&frame);
        }
        if (xTaskGetTickCount() - last_heartbeat >= pdMS_TO_TICKS(CONFIG_WIDS_HEARTBEAT_SECONDS * 1000)) {
            report_heartbeat();
            last_heartbeat = xTaskGetTickCount();
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "WiFi Sentinel passive monitor - ESP32-C5");
    ESP_LOGI(TAG, "Configure sensor via idf.py menuconfig; no transmission of attack frames");
    s_queue = xQueueCreate(RX_QUEUE_DEPTH, sizeof(rx_frame_t));
    if (!s_queue) {
        ESP_LOGE(TAG, "Unable to allocate telemetry queue");
        abort();
    }
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_config));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    wifi_promiscuous_filter_t filter = {.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT};
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(rx_callback));
    ESP_ERROR_CHECK(esp_wifi_start());
#ifdef CONFIG_WIDS_BAND_5G
    ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY));
#else
    ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_2G_ONLY));
#endif
    esp_err_t channel_status = esp_wifi_set_channel(CONFIG_WIDS_CHANNEL, WIFI_SECOND_CHAN_NONE);
    if (channel_status != ESP_OK) {
        ESP_LOGE(TAG, "Cannot tune channel %d (band/regulatory constraints?) error=%s",
                 CONFIG_WIDS_CHANNEL, esp_err_to_name(channel_status));
        ESP_ERROR_CHECK(channel_status);
    }
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    if (strlen(CONFIG_WIDS_SENSOR_ID) > 40) {
        ESP_LOGE(TAG, "Sensor ID must be <= 40 characters");
        abort();
    }
    BaseType_t created = xTaskCreate(export_task, "wids_uart", 4096, NULL, 4, NULL);
    if (created != pdPASS) abort();
    ESP_LOGI(TAG, "Receiving on channel %d, reporting only management frames", CONFIG_WIDS_CHANNEL);
}
