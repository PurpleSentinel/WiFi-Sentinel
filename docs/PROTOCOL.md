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
- `ssid`: short, best-effort SSID from sampled beacon/probe response; null if hidden or unavailable. Firmware sanitizes non-ASCII/control bytes with `_`.
- `uptime_ms`: firmware monotonic milliseconds, may overflow every ~49.7 days.

## `heartbeat` event

```json
{"v":1,"kind":"heartbeat","sensor_id":"c6-sensor-01","channel":6,"uptime_ms":60000,"captured":2048,"dropped":2}
```

`dropped` counts events that failed to enqueue for USB export. This does *not* measure RF/driver packet losses. `captured` counts events selected for queueing (after beacon sampling). The dashboard displays dropped events from the most recent heartbeat.

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
- `GET /api/devices?limit=200` observed unicast address summaries from the last
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
