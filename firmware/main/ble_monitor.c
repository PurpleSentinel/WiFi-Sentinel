/* Passive observer only. No advertisements, connections or active scan requests. */
#include "ble_monitor.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"

typedef struct {
    uint8_t address[6], type, event_type, length, payload[31];
    int8_t rssi;
    uint32_t uptime_ms;
} report_t;

static QueueHandle_t reports;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static wids_ble_config_t config = {.enabled = false, .interval_ms = 100, .window_ms = 20};
static bool synced, scanning;
static int last_error;
static uint32_t captured, dropped;
static int64_t last_export;

static int gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    if (event->type == BLE_GAP_EVENT_DISC) {
        const struct ble_gap_disc_desc *desc = &event->disc;
        if (desc->length_data > 31 || desc->event_type > 3 || desc->addr.type > 1) return 0;
        report_t item = {.type = desc->addr.type, .event_type = desc->event_type,
            .length = desc->length_data, .rssi = desc->rssi,
            .uptime_ms = (uint32_t)(esp_timer_get_time() / 1000)};
        memcpy(item.address, desc->addr.val, 6);
        memcpy(item.payload, desc->data, item.length);
        __atomic_fetch_add(&captured, 1, __ATOMIC_RELAXED);
        if (xQueueSend(reports, &item, 0) != pdTRUE)
            __atomic_fetch_add(&dropped, 1, __ATOMIC_RELAXED);
    } else if (event->type == BLE_GAP_EVENT_DISC_COMPLETE) {
        portENTER_CRITICAL(&mux);
        scanning = false;
        portEXIT_CRITICAL(&mux);
    }
    return 0;
}

static int start_scan(wids_ble_config_t next)
{
    uint8_t own_type;
    int rc = ble_hs_id_infer_auto(0, &own_type);
    if (rc) return rc;
    struct ble_gap_disc_params params = {0};
    params.passive = 1;
    params.filter_duplicates = 0; /* Collector performs time-bounded deduplication. */
    params.itvl = next.interval_ms * 8 / 5;
    params.window = next.window_ms * 8 / 5;
    return ble_gap_disc(own_type, BLE_HS_FOREVER, &params, gap_event, NULL);
}

static void on_sync(void)
{
    wids_ble_config_t next;
    portENTER_CRITICAL(&mux);
    next = config;
    portEXIT_CRITICAL(&mux);
    int address_rc = ble_hs_util_ensure_addr(0);
    int rc = address_rc ? address_rc : next.enabled ? start_scan(next) : 0;
    portENTER_CRITICAL(&mux);
    synced = address_rc == 0;
    last_error = rc;
    scanning = next.enabled && rc == 0;
    portEXIT_CRITICAL(&mux);
}

static void on_reset(int reason)
{
    portENTER_CRITICAL(&mux);
    synced = scanning = false;
    last_error = reason;
    portEXIT_CRITICAL(&mux);
}

static void host_task(void *arg)
{
    (void)arg;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void wids_ble_init(wids_ble_config_t initial)
{
    config = initial;
    reports = xQueueCreate(64, sizeof(report_t));
    if (!reports) { last_error = ESP_ERR_NO_MEM; return; }
    esp_err_t rc = nimble_port_init();
    if (rc != ESP_OK) { last_error = rc; return; }
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    nimble_port_freertos_init(host_task);
}

wids_ble_config_t wids_ble_config(void)
{
    portENTER_CRITICAL(&mux);
    wids_ble_config_t value = config;
    portEXIT_CRITICAL(&mux);
    return value;
}

esp_err_t wids_ble_apply(wids_ble_config_t next)
{
    if (next.interval_ms < 10 || next.interval_ms > 10240 || next.window_ms < 10 ||
        next.window_ms > next.interval_ms) return ESP_ERR_INVALID_ARG;
    portENTER_CRITICAL(&mux);
    bool ready = synced;
    wids_ble_config_t previous = config;
    portEXIT_CRITICAL(&mux);
    if (!ready) return ESP_ERR_INVALID_STATE;
    int rc = ble_gap_disc_cancel();
    if (rc && rc != BLE_HS_EALREADY) return ESP_FAIL;
    rc = next.enabled ? start_scan(next) : 0;
    if (rc) {
        if (previous.enabled) start_scan(previous);
        bool active = ble_gap_disc_active();
        portENTER_CRITICAL(&mux);
        last_error = rc;
        scanning = active;
        portEXIT_CRITICAL(&mux);
        return ESP_FAIL;
    }
    xQueueReset(reports);
    portENTER_CRITICAL(&mux);
    config = next;
    scanning = next.enabled;
    last_error = 0;
    portEXIT_CRITICAL(&mux);
    return ESP_OK;
}

bool wids_ble_scanning(void) { portENTER_CRITICAL(&mux); bool v = scanning; portEXIT_CRITICAL(&mux); return v; }
int wids_ble_error(void) { portENTER_CRITICAL(&mux); int v = last_error; portEXIT_CRITICAL(&mux); return v; }
uint32_t wids_ble_captured(void) { return __atomic_load_n(&captured, __ATOMIC_RELAXED); }
uint32_t wids_ble_dropped(void) { return __atomic_load_n(&dropped, __ATOMIC_RELAXED); }

void wids_ble_export(const char *sensor_id)
{
    report_t item;
    if (!reports || xQueueReceive(reports, &item, 0) != pdTRUE) return;
    /* Bound USB output to 20 BLE reports/s, independently of Wi-Fi traffic. */
    int64_t now = esp_timer_get_time();
    if (now - last_export < 50000) {
        __atomic_fetch_add(&dropped, 1, __ATOMIC_RELAXED);
        return;
    }
    last_export = now;
    printf("WIDS {\"v\":1,\"kind\":\"ble\",\"sensor_id\":\"%s\",\"address\":\"", sensor_id);
    for (int i = 5; i >= 0; i--) printf(i ? "%02x:" : "%02x", item.address[i]);
    printf("\",\"address_type\":\"%s\",\"rssi\":%d,\"event_type\":%u,\"payload_hex\":\"",
           item.type ? "random" : "public", item.rssi, item.event_type);
    for (unsigned i = 0; i < item.length; i++) printf("%02x", item.payload[i]);
    printf("\",\"uptime_ms\":%" PRIu32 "}\n", item.uptime_ms);
    fflush(stdout);
}
