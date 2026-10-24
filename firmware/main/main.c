/*
 * WiFi Sentinel v0.1.0
 * Receive-only 802.11 management-frame telemetry for ESP32-C5/C6.
 * No esp_wifi_80211_tx, association, injection, or radio jamming functions.
 *
 * Requires Espressif ESP-IDF v5.5.2+ targeting esp32c5 or esp32c6.
 * C6 native USB bring-up is documented; exact PCB identity remains unknown.
 */
#include <inttypes.h>
#include <fcntl.h>
#include <unistd.h>
#include "cJSON.h"
#include "nvs.h"
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
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#endif

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

/* Runtime configuration is owned by export_task. Only sample_n is read by RX. */
typedef struct {
    uint32_t version;
    char sensor_id[41];
    int band;
    int channel;
    int sample_n;
    int heartbeat_seconds;
} runtime_config_t;

static runtime_config_t s_config = {
    .version = 1, .sensor_id = CONFIG_WIDS_SENSOR_ID,
#ifdef CONFIG_WIDS_BAND_5G
    .band = 5,
#else
    .band = 2,
#endif
    .channel = CONFIG_WIDS_CHANNEL, .sample_n = CONFIG_WIDS_BEACON_SAMPLE_N,
    .heartbeat_seconds = CONFIG_WIDS_HEARTBEAT_SECONDS,
};
static nvs_handle_t s_config_nvs;

static bool valid_identifier(const char *value)
{
    size_t length = strlen(value);
    if (!length || length > 40) return false;
    for (const char *p = value; *p; p++) {
        if (!( (*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
               (*p >= '0' && *p <= '9') || *p == '_' || *p == '-' || *p == '.')) return false;
    }
    return true;
}

static bool allowed_channel(int band, int channel)
{
    if (band == 2) {
        wifi_country_t country;
        if (esp_wifi_get_country(&country) != ESP_OK) return false;
        return channel >= country.schan && channel < country.schan + country.nchan && channel <= 14;
    }
#if CONFIG_SOC_WIFI_SUPPORT_5G
    /* Conservative non-DFS subset; driver still enforces regulatory policy. */
    if (band == 5) return channel == 36 || channel == 40 || channel == 44 || channel == 48;
#endif
    return false;
}

static bool valid_config(const runtime_config_t *config)
{
    return config->version == 1 && memchr(config->sensor_id, 0, sizeof(config->sensor_id)) &&
        valid_identifier(config->sensor_id) && allowed_channel(config->band, config->channel) &&
        config->sample_n >= 1 && config->sample_n <= 1000 &&
        config->heartbeat_seconds >= 1 && config->heartbeat_seconds <= 300;
}

static esp_err_t tune(const runtime_config_t *config)
{
#if CONFIG_SOC_WIFI_SUPPORT_5G
    esp_err_t err = esp_wifi_set_band_mode(config->band == 5 ? WIFI_BAND_MODE_5G_ONLY : WIFI_BAND_MODE_2G_ONLY);
    if (err != ESP_OK) return err;
#endif
    return esp_wifi_set_channel(config->channel, WIFI_SECOND_CHAN_NONE);
}

static bool json_integer(const cJSON *obj, const char *name, int *value)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(obj, name);
    if (!cJSON_IsNumber(item) || item->valuedouble != item->valueint) return false;
    *value = item->valueint;
    return true;
}

static void report_config(const char *id, const char *error)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "v", 1);
    cJSON_AddStringToObject(root, "kind", "config_ack");
    cJSON_AddStringToObject(root, "id", id);
    cJSON_AddBoolToObject(root, "ok", error == NULL);
    if (error) cJSON_AddStringToObject(root, "error", error);
    cJSON *values = cJSON_AddObjectToObject(root, "config");
    cJSON_AddStringToObject(values, "sensor_id", s_config.sensor_id);
    cJSON_AddStringToObject(values, "band", s_config.band == 5 ? "5" : "2.4");
    cJSON_AddNumberToObject(values, "channel", s_config.channel);
    cJSON_AddNumberToObject(values, "beacon_sample_n", s_config.sample_n);
    cJSON_AddNumberToObject(values, "heartbeat_seconds", s_config.heartbeat_seconds);
    cJSON *caps = cJSON_AddObjectToObject(root, "capabilities");
    cJSON_AddStringToObject(caps, "chip", CONFIG_IDF_TARGET);
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    cJSON_AddStringToObject(caps, "console", "USB Serial/JTAG");
#else
    cJSON_AddStringToObject(caps, "console", "UART / build-time console");
#endif
    wifi_country_t country;
    if (esp_wifi_get_country(&country) == ESP_OK) {
        char code[4] = {0};
        memcpy(code, country.cc, 3);
        cJSON_AddStringToObject(caps, "country", code);
    }
    cJSON *bands = cJSON_AddArrayToObject(caps, "bands");
    cJSON_AddItemToArray(bands, cJSON_CreateString("2.4"));
    cJSON *channels = cJSON_AddObjectToObject(caps, "channels");
    cJSON *two = cJSON_AddArrayToObject(channels, "2.4");
    for (int i = 1; i <= 14; i++) if (allowed_channel(2, i)) cJSON_AddItemToArray(two, cJSON_CreateNumber(i));
#if CONFIG_SOC_WIFI_SUPPORT_5G
    cJSON_AddItemToArray(bands, cJSON_CreateString("5"));
    cJSON *five = cJSON_AddArrayToObject(channels, "5");
    for (int i = 36; i <= 48; i += 4) if (allowed_channel(5, i)) cJSON_AddItemToArray(five, cJSON_CreateNumber(i));
#endif
    char *line = cJSON_PrintUnformatted(root);
    if (line) { printf("WIDS %s\n", line); fflush(stdout); cJSON_free(line); }
    cJSON_Delete(root);
}

static void handle_command(const char *line)
{
    if (strncmp(line, "WIDS_CMD ", 9)) return;
    cJSON *root = cJSON_Parse(line + 9);
    if (!root) return;
    const cJSON *id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
    int version;
    if (!cJSON_IsString(id) || !valid_identifier(id->valuestring) ||
        !cJSON_IsString(action) || !json_integer(root, "v", &version) || version != 1) {
        cJSON_Delete(root); return;
    }
    const char *error = NULL;
    if (!strcmp(action->valuestring, "set_config")) {
        runtime_config_t next = s_config;
        const cJSON *values = cJSON_GetObjectItemCaseSensitive(root, "settings");
        const cJSON *sid = cJSON_GetObjectItemCaseSensitive(values, "sensor_id");
        const cJSON *band = cJSON_GetObjectItemCaseSensitive(values, "band");
        if (!cJSON_IsObject(values) || cJSON_GetArraySize(values) != 5 ||
            !cJSON_IsString(sid) || !valid_identifier(sid->valuestring) || !cJSON_IsString(band) ||
            (strcmp(band->valuestring, "2.4") && strcmp(band->valuestring, "5")) ||
            !json_integer(values, "channel", &next.channel) ||
            !json_integer(values, "beacon_sample_n", &next.sample_n) ||
            !json_integer(values, "heartbeat_seconds", &next.heartbeat_seconds)) {
            error = "Invalid sensor configuration";
        } else {
            strcpy(next.sensor_id, sid->valuestring);
            next.band = !strcmp(band->valuestring, "5") ? 5 : 2;
            if (!valid_config(&next)) error = "Unsupported band, channel or setting range";
        }
        if (!error) {
            esp_err_t err = esp_wifi_set_promiscuous(false);
            if (err == ESP_OK) err = tune(&next);
            if (err == ESP_OK) err = nvs_set_blob(s_config_nvs, "config", &next, sizeof(next));
            if (err == ESP_OK) err = nvs_commit(s_config_nvs);
            if (err != ESP_OK) {
                /* Restore both radio and pending NVS changes on failure. */
                ESP_ERROR_CHECK(tune(&s_config));
                ESP_ERROR_CHECK(nvs_set_blob(s_config_nvs, "config", &s_config, sizeof(s_config)));
                ESP_ERROR_CHECK(nvs_commit(s_config_nvs));
                error = esp_err_to_name(err);
            } else {
                xQueueReset(s_queue);
                s_config.band = next.band;
                s_config.channel = next.channel;
                s_config.heartbeat_seconds = next.heartbeat_seconds;
                strcpy(s_config.sensor_id, next.sensor_id);
                __atomic_store_n(&s_config.sample_n, next.sample_n, __ATOMIC_RELAXED);
            }
            ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
        }
    } else if (strcmp(action->valuestring, "get_config")) {
        error = "Unknown command";
    }
    report_config(id->valuestring, error);
    cJSON_Delete(root);
}

static void poll_commands(void)
{
    static char line[768];
    static size_t used = 0;
    static bool oversized = false;
    char ch;
    for (int budget = 0; budget < 1024 && read(STDIN_FILENO, &ch, 1) == 1; budget++) {
        if (ch == '\n') {
            line[used] = 0;
            if (!oversized) handle_command(line);
            used = 0; oversized = false;
        } else if (ch != '\r' && !oversized) {
            if (used < sizeof(line) - 1) line[used++] = ch;
            else oversized = true;
        }
    }
}

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
        if (s_beacon_counter % __atomic_load_n(&s_config.sample_n, __ATOMIC_RELAXED)) return;
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
    json_string(s_config.sensor_id);
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
    json_string(s_config.sensor_id);
    printf(",\"channel\":%d,\"uptime_ms\":%" PRIu32
           ",\"captured\":%" PRIu32 ",\"dropped\":%" PRIu32 "}\n",
           s_config.channel, (uint32_t)(esp_timer_get_time() / 1000),
           __atomic_load_n(&s_captured, __ATOMIC_RELAXED),
           __atomic_load_n(&s_dropped, __ATOMIC_RELAXED));
    fflush(stdout);
}

static void export_task(void *context)
{
    (void)context;
    rx_frame_t frame;
    TickType_t last_heartbeat = xTaskGetTickCount();
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG
    usb_serial_jtag_driver_config_t usb_config = {
        .rx_buffer_size = 2048, .tx_buffer_size = 2048,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb_config));
    usb_serial_jtag_vfs_use_driver();
#endif
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    for (;;) {
        poll_commands();
        if (xQueueReceive(s_queue, &frame, pdMS_TO_TICKS(50)) == pdTRUE) {
            report_frame(&frame);
        }
        if (xTaskGetTickCount() - last_heartbeat >= pdMS_TO_TICKS(s_config.heartbeat_seconds * 1000)) {
            report_heartbeat();
            last_heartbeat = xTaskGetTickCount();
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "WiFi Sentinel passive monitor - %s", CONFIG_IDF_TARGET);
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
    ESP_ERROR_CHECK(nvs_open("wids", NVS_READWRITE, &s_config_nvs));
    runtime_config_t saved;
    size_t size = sizeof(saved);
    if (nvs_get_blob(s_config_nvs, "config", &saved, &size) == ESP_OK &&
        size == sizeof(saved) && valid_config(&saved)) s_config = saved;
    ESP_ERROR_CHECK(tune(&s_config));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    if (!valid_identifier(s_config.sensor_id)) {
        ESP_LOGE(TAG, "Sensor ID must be <= 40 characters");
        abort();
    }
    BaseType_t created = xTaskCreate(export_task, "wids_uart", 4096, NULL, 4, NULL);
    if (created != pdPASS) abort();
    ESP_LOGI(TAG, "Receiving on channel %d, reporting only management frames", s_config.channel);
}
