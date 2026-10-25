# WIDS v1 serial telemetry protocol

## Framing

One ASCII line per event, beginning exactly `WIDS `, followed by one compact JSON object and `\n`. Other ESP-IDF boot/log output is ignored. Messages above 2048 bytes are ignored. `v=1` is required; no binary payloads. Default UART console setup uses 115200; actual USB transport behaviour depends on the board.

## `frame` event

```json
{
  "v": 1,
  "kind": "frame",
  "sensor_id": "c6-sensor-01",
  "channel": 6,
  "subtype": "deauth",
  "sa": "02:aa:bb:cc:dd:01",
  "da": "ff:ff:ff:ff:ff:ff",
  "bssid": "02:11:22:33:44:55",
  "rssi": -51,
  "protected": false,
  "reason_code": 7,
  "status_code": -1,
  "ssid": null,
  "uptime_ms": 123450
}
```

- `subtype`: `auth`, `deauth`, `disassoc`, `assoc_req`, `assoc_resp`, `reassoc_req`, `reassoc_resp`, `beacon`, `probe_resp`.
- `sa`/`da`/`bssid`: direct management-frame header address fields, **not authenticated identities**.
- `protected`: 802.11 frame-control Protected bit, not verification of cryptographic authenticity.
- `reason_code`: deauth/disassoc where unprotected and present; `-1` means unknown.
- `status_code`: auth/association response where unprotected and present; `-1` means unknown.
- `ssid_hex`: lossless SSID information-element bytes encoded as 0–64 hex digits
  (0–32 bytes). An empty string means a present zero-length/hidden SSID; null
  means unavailable. Current firmware emits `ssid:null` plus this field, keeping
  the entire serial message ASCII JSON even for invalid UTF-8, NUL or control bytes.
- `ssid`: legacy text field, or the collector's derived display value in APIs.
  Valid printable UTF-8 such as `Café` is displayed normally. Non-printable and
  invalid bytes become literal `\xNN` escapes; literal backslashes are doubled
  to distinguish raw bytes from names containing escape-looking text. Null is
  used for hidden/unavailable names. Legacy text-only events remain accepted,
  but bytes already replaced by older firmware cannot be recovered.
- `uptime_ms`: firmware monotonic milliseconds, may overflow every ~49.7 days.

For example, a sampled `Café` beacon uses `"ssid":null,"ssid_hex":"436166c3a9"`.
The collector stores both display text and the canonical raw hex. If a message
supplies both text and raw hex they must agree. Legacy text must fit 32 UTF-8
bytes; the bound is bytes, not Unicode character count. Upgrade the collector
before flashing the raw-hex firmware; older collectors cannot interpret the new
field. See [SSID configuration and matching](CONFIGURATION.md).

## `heartbeat` event

```json
{"v":1,"kind":"heartbeat","sensor_id":"c6-sensor-01","channel":6,"uptime_ms":60000,"captured":2048,"dropped":2}
```

`dropped` counts events that failed to enqueue for USB export. This does *not* measure RF/driver packet losses. `captured` counts events selected for queueing (after beacon sampling). The dashboard displays dropped events from the most recent heartbeat.

Sampling is per BSSID/channel with independent beacon/probe-response counters:
first sighting, then one per N observations. Startup, new identities and bounded
table eviction can increase the export rate above a global one-in-N estimate.

## USB configuration commands

Runtime-capable firmware accepts bounded `WIDS_CMD ` JSON lines on the same USB
serial connection. The collector's single reader owns both reads and writes.

```json
{"v":1,"id":"request-123","action":"get_config","settings":{}}
```

`set_config` takes a complete settings object. Example:

```json
{"v":1,"id":"request-124","action":"set_config","settings":{"sensor_id":"c6-sensor-01","band":"2.4","channel":11,"beacon_sample_n":20,"heartbeat_seconds":15}}
```

The firmware replies with a `WIDS ` line whose kind is `config_ack`, matching
`id`, boolean `ok`, effective `config`, and `capabilities` (chip, console,
regulatory country profile, bands and per-band channels). Failed commands include
an `error` and retain the prior effective configuration. Success is acknowledged
only after radio tuning and NVS commit. Requests have a maximum 767-byte body
including the prefix; oversized lines are discarded through the next newline.
Commands configure passive reception only, not RF transmissions.

Upgraded firmware also reports `capabilities.beacon_sampling` as
`per_bssid_channel_subtype` and `capabilities.beacon_sampling_capacity` as 64.
These are read-only capability metadata, not additional editable settings.

The collector validates patches, sends complete sensor settings, waits up to
eight seconds for the matching acknowledgement, and queries configuration every
five seconds to discover startup/reconnect state. It reports a timeout as an
uncertain outcome rather than claiming success. Old telemetry-only firmware can
continue reporting frames but cannot expose runtime controls.

## Dashboard API

Data reads and protected configuration writes:

- `GET /` static dashboard
- `GET /api/health` collector basic status
- `GET /api/summary` 24-hour counts, per-subtype counts, seen sensors
- `GET /api/alerts?limit=100` last alerts, max 500
- `GET /api/frames?limit=100` recent frame metadata, max 500
- `GET /api/sensors` last-seen/queue-loss per sensor
- `GET /api/channels` counts grouped by channel
- `GET /api/devices?limit=200&role=all` classified unicast address summaries from the last
  24 hours, max 500; see [device observation semantics](DASHBOARD.md)
- `GET /api/alert-sources` retained alert contributing-source identities and legacy unknown-source count
- `GET /api/mac/{address}` retained local observations and associated alerts
- `GET /api/mac/{address}/vendor` local registry and cached prefix-only enrichment; `?refresh=true` retries enrichment
- `GET /api/configuration` current settings and sensor capabilities (no key)
- `POST /api/configuration/collector` validated collector settings patch
- `POST /api/configuration/sensor` acknowledged sensor settings patch

Read endpoints are **unauthenticated** and bind to loopback by default. POST
endpoints require a configuration key and matching request origin. See
[Configuration](CONFIGURATION.md). Do not expose the service to the internet.

## `ble` event (optional passive legacy advertisements)

```json
{"v":1,"kind":"ble","sensor_id":"c6-sensor-01","address":"cc:bb:aa:11:22:33","address_type":"random","rssi":-55,"event_type":0,"payload_hex":"05095465737403030f18","uptime_ms":123450}
```

`address_type` is `public` or `random`, taken from the BLE report, not inferred
from MAC bits. `event_type` is legacy advertisement type 0–3; scan responses (4)
are excluded. `payload_hex` preserves 0–31 advertisement bytes (0–62 hex digits).
RSSI must be -127..20 and uptime an unsigned 32-bit integer. The collector decodes
AD structures and flags malformed fields without losing the original bytes.

BLE-capable `config_ack` adds `ble_enabled` (boolean), `ble_interval_ms` and
`ble_window_ms` to `config`, and `ble:true`, `ble_mode:passive_legacy_1m`, and
`ble_coexistence:shared_radio_unstable` to `capabilities`. Top-level `ble_status`
contains `scanning` (boolean), `captured` and `dropped` (unsigned counters),
`error` (signed stack/controller status), and `free_heap_bytes` /
`minimum_free_heap_bytes` (whole-sensor heap measurements).
The complete sensor settings object has eight fields; legacy five-field commands
remain supported and preserve BLE settings. All three BLE fields must be supplied
together when using the eight-field command. Timing must be 10–10240 ms with
window no greater than interval. See [BLE monitoring](BLE.md) for limits.

Additional reads:

- `GET /api/ble/observations?limit=100` (max 500), optional `address` and
  `address_type=public|random` filters.
- `GET /api/ble/devices?limit=200` (max 500), latest retained observations grouped
  by sensor/address/type in the last 24 hours; includes `has_more`.
- `/api/summary` adds `ble_observations_24h`; alert totals include BLE alerts.
- `/api/alerts` adds `protocol` (`wifi` or `ble`), and BLE `address_type`.
  BLE `bssid` and `channel` are null, with `source_macs` holding the advertiser.
  Alert IDs are unique within their protocol, not across both tables.


BLE API results feed the dedicated **BLE** tab after Devices. Wi-Fi `/api/devices`
and `/api/frames` remain Wi-Fi-only. Observation records include decoded
`local_name`, `service_uuids`, `manufacturer_data` (company ID and raw data),
`service_data` (UUID and raw data) and `ad_malformed`, alongside the canonical
`payload_hex`. BLE device summaries add first/last seen and observation counts;
these are retained advertisement/address counts, not unique physical devices.

## BLE explorer APIs (post-v1.2)

- `GET /api/ble/devices?limit=200&query=...&address_type=all&alert_only=false&sort=recent`:
  `query` up to 200 characters searches labels/notes, addresses/sensors, service
  and company names/IDs. Types: all/public/random; sort: recent/rssi/name.
  Filtering precedes the 1–500 result limit. Response adds `total_identities`
  (unfiltered 24-hour sensor/address/type count), `limit`, `query`, and enriched
  `display_label`, `label_source`, `advertised_name`, `category`, `address_subtype`,
  `company_details`, `service_details`, `identity_confidence` and `alert_associated`.
- `GET /api/ble/observations` accepts optional `sensor_id` in addition to address/type.
- `GET /api/ble/advertiser?sensor_id=...&address=...&address_type=random` requires
  the complete identity. Returns evidence, label and up to 100 latest retained
  observations from that identity only. Empty history returns a null advertiser.
- `GET /api/ble/labels` lists up to 1024 persistent operator labels, including
  identities whose observations have expired.
- `POST /api/ble/label` requires `X-Configuration-Key`, matching Origin and JSON
  fields `sensor_id`, `address`, `address_type`, `alias`, `notes`. Unknown fields
  or invalid text/identity return 400. Empty alias and notes delete the record.
  These writes do not reset detector windows or change sensor settings.

Alias/notes limits and persistence are in [BLE explorer](BLE_EXPLORER.md). Read
endpoints remain unauthenticated. The [RSSI model](BLE_RANGING.md) runs locally
on the selected identity's samples; it adds no RF commands or ranging API.
