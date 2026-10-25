#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

typedef struct {
    bool enabled;
    uint16_t interval_ms;
    uint16_t window_ms;
} wids_ble_config_t;

void wids_ble_init(wids_ble_config_t initial);
esp_err_t wids_ble_apply(wids_ble_config_t config);
wids_ble_config_t wids_ble_config(void);
void wids_ble_export(const char *sensor_id);
bool wids_ble_scanning(void);
int wids_ble_error(void);
uint32_t wids_ble_captured(void);
uint32_t wids_ble_dropped(void);
