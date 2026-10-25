# Passive Bluetooth Low Energy monitoring

BLE monitoring is included from v1.2.0. The v1.1.0 source archive predates this
feature; upgrade the collector before flashing BLE-capable firmware.

The ESP32-C6 USB sensor supports optional passive **legacy BLE advertisements on
LE 1M**, alongside Wi-Fi management-frame monitoring. It does not perform active
scanning, advertising, pairing, GATT connections, or Bluetooth Classic monitoring.
Extended advertisements, coded/2M PHY observations and scan-response payloads are
not collected by this implementation. A device that only provides its name in a
scan response may therefore appear unnamed.

## Hardware and radio coverage

The tested platform is the existing ESP32-C6 sensor and Raspberry Pi 4 USB
collector. BLE and Wi-Fi share the C6's single 2.4 GHz radio. Espressif classifies
Wi-Fi sniffer RX plus BLE scanning as supported with **unstable performance**:
[ESP-IDF 5.5 ESP32-C6 RF coexistence](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32c6/api-guides/coexist.html).
Software coexistence is enabled in the firmware build. Simultaneous observations
are best effort; queue drops do not measure packets missed over the air. Use
separate sensors/collectors for dependable simultaneous coverage. The current
collector still reads one USB device. C5 BLE operation remains unvalidated.

The firmware uses a 64-report BLE queue and exports at most 20 BLE reports per
second. BLE queue overflow and export rate limiting increment its BLE dropped
counter. Wi-Fi retains its own queue, sampler and dropped counter. Scan callbacks
only copy bounded records; USB output is owned by the existing export task.

Adding NimBLE increases the application size. The supplied defaults use the
single-app large partition layout (app remains at 0x10000; NVS remains at 0x9000).
Build and flash the complete generated `flash_args`, including the new partition
table. Do not erase NVS. This is a USB-flashed single-app layout, not an OTA setup.

## Enable and configure

Upgrade the collector before the firmware. Existing Wi-Fi-only firmware remains
supported; BLE controls show as unavailable until upgraded. BLE starts disabled
on a sensor without saved BLE settings. In **Configuration**, enter the existing
configuration key and apply the sensor's BLE controls:

| Setting | Range / default | Meaning |
|---|---|---|
| BLE enabled | false initially | Enable or stop passive scanning |
| Scan interval | 10–10240 ms / 100 | Time between scan windows |
| Scan window | 10 ms up to interval / 20 | Requested receive time per window |

The controller uses 0.625 ms units; milliseconds are converted down to the nearest
unit. More scan time competes with Wi-Fi reception. Sensor settings are saved in
NVS and survive reboot without changing the saved Wi-Fi channel, band or sampling
factor. The Pi's Ethernet and Wi-Fi configuration is not modified.

Collector controls apply immediately, persist in its existing settings JSON, and
have equivalent environment defaults:

| Configuration / environment | Default | Allowed |
|---|---|---|
| `ble_retention_days` / `WIDS_BLE_RETENTION_DAYS` | 7 | 1–3650 days |
| `ble_duplicate_seconds` / `WIDS_BLE_DUPLICATE_SECONDS` | 10 | 0–3600 seconds |
| `ble_max_records` / `WIDS_BLE_MAX_RECORDS` | 100000 | 100–1000000 records per BLE table |
| `ble_filters` / `WIDS_BLE_FILTERS` | empty | Up to 256 exact rules; empty accepts all |
| `ble_alert_rules` / `WIDS_BLE_ALERT_RULES` | empty | Up to 256 exact rules; empty disables alerts |

Use one rule per line in the dialog, or comma-separated rules in the environment:

- `name:My beacon` — advertised name, case insensitive, exact match.
- `address:aa:bb:cc:dd:ee:ff` — advertiser address, case insensitive.
- `service:180f` — service UUID, in 16-bit, 32-bit or standard 128-bit notation.
- `company:004c` — four hexadecimal digits for a Bluetooth SIG company identifier.

Filters are ORed. Alerts operate only on advertisements admitted by the filters.
An advertisement may match several alert rules. The existing alert cooldown
applies per sensor and rule across all advertiser addresses, so rotating addresses
cannot bypass a rule's cooldown. Changing collector policy resets the caches.

Identical reports are suppressed by sensor, address, address type, event type and
raw payload for the configured interval; RSSI changes alone do not bypass this.
Zero disables collector duplicate suppression. Changed payloads remain visible.
The duplicate and cooldown caches each have at most 1024 entries; oldest entries
are evicted under churn. Cache eviction or collector restart can allow earlier
re-reporting/re-alerting. Sensor rate limits remain active independently.

The record cap applies separately to BLE observations and BLE alerts. When a cap
is exceeded, the oldest batch is removed, leaving about 90% of the cap to avoid
expensive trimming on each insert. Time retention also runs at startup, policy
changes and every 60 seconds while idle. SQLite can reuse deleted pages; file
size does not immediately shrink. Counts reflect retained, filtered observations,
not every advertisement transmitted in the area.

## Dashboard and interpretation

- **BLE**, immediately after **Devices**, contains the 24-hour BLE observation
  count, up to 200 advertiser summaries grouped by sensor/address/type, and the
  latest 100 retained BLE advertisements. Devices and Reporting contain Wi-Fi
  observations; BLE data is fetched only while its tab is active.
- **Alerts** includes `ble_match` alerts and exports them with `protocol:ble`.
  Wi-Fi channel and BSSID are null for BLE. Alert source addresses are red.
- Select an advertiser label to open evidence, protected aliases/notes and the
  [RSSI distance model](BLE_RANGING.md). Search/filter/sort apply before the result cap;
  raw recent advertisements are secondary expandable sections. See [explorer](BLE_EXPLORER.md).
- Click a BLE address to see raw advertisement hex, local name, service UUIDs,
  manufacturer/service data, RSSI, sensor and timestamps. Random BLE addresses
  never initiate a MAC vendor lookup; public addresses can use the existing
  registration lookup. Bluetooth company IDs label advertisement data and are
  not proof of the device manufacturer or owner.
- **Status** shows BLE support, effective scan state, received advertisement
  reports, dropped/rate-limited reports, free heap, and the last stack/controller error (0 is clear).
  When disconnected, status is explicitly stale/unavailable.

BLE public and random address spaces are distinct from Wi-Fi identities. Random
addresses may rotate and public-looking address bits do not override the BLE
address type. Counts must never be treated as exact physical-device counts.
Host receive UTC timestamps are used, not authenticated RF capture timestamps.
Malformed AD structures are flagged and their raw payload is retained; missing
names or manufacturer data are normal. No vendor/model identity is inferred from
an unrecognized company identifier.

## Software-only example

The existing `demo` command generates Wi-Fi events. To inspect a deterministic
BLE advertisement without RF or a sensor, run from `collector/` with its virtual
environment active. This uses a separate temporary database, not the live store:

```bash
cat > /tmp/wifi-sentinel-ble-example.ndjson <<'EOF'
{"v":1,"kind":"ble","sensor_id":"demo-ble","address":"cc:bb:aa:11:22:33","address_type":"random","rssi":-55,"event_type":0,"payload_hex":"05095465737403030f18","uptime_ms":100}
EOF
WIDS_DATABASE=/tmp/wifi-sentinel-ble-example.sqlite3 WIDS_SERIAL_PORT= wifi-sentinel replay /tmp/wifi-sentinel-ble-example.ndjson
WIDS_DATABASE=/tmp/wifi-sentinel-ble-example.sqlite3 WIDS_SERIAL_PORT= WIDS_HOST=127.0.0.1 WIDS_PORT=8182 wifi-sentinel serve
```

Open `http://127.0.0.1:8182` and select **BLE** after Devices. The fixture advertises
name `Test` and service `180f`, with a random address and RSSI -55. It generates
no RF traffic and has no physical-device identity. Alert rules remain disabled
unless configured. Existing settings for that temporary database override its
environment defaults, just as in normal operation.

## Identification and approximate ranging enhancements

Post-v1.2 collector/UI work for #28/#29 adds the [BLE explorer](BLE_EXPLORER.md)
and [RSSI distance curve](BLE_RANGING.md). Company/service names use an offline
attributed SIG snapshot; unknown identifiers remain numeric. Aliases/notes are
key-protected, persist per sensor/address/type and do not follow address rotation.
Model settings are session-only and per identity. Range estimates, name claims
and company IDs are not evidence of physical identity or precise location.

The BLE summary's **Unique devices** card matches Capture Freshness and counts
distinct advertiser MAC addresses across sensors and address types over 24 hours. It uses all
retained observations, not the table cap or filters, and does not claim an exact
physical-device count. See [metric definition](BLE_EXPLORER.md#unique-devices-metric).
