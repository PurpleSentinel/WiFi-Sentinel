# WIDS v1 serial telemetry protocol

## Framing

One ASCII line per event, beginning exactly `WIDS `, followed by one compact JSON object and `\n`. Other ESP-IDF boot/log output is ignored. Messages above 2048 bytes are ignored. `v=1` is required; no binary payloads. Default UART console setup uses 115200; actual USB transport behaviour depends on the board.

## `frame` event

```json
{
  "v": 1,
  "kind": "frame",
  "sensor_id": "c5-sensor-01",
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
{"v":1,"kind":"heartbeat","sensor_id":"c5-sensor-01","channel":6,"uptime_ms":60000,"captured":2048,"dropped":2}
```

`dropped` counts events that failed to enqueue for USB export. This does *not* measure RF/driver packet losses. `captured` counts events selected for queueing (after beacon sampling). The dashboard displays dropped events from the most recent heartbeat.

## Public local API

Read-only:

- `GET /` static dashboard
- `GET /api/health` collector basic status
- `GET /api/summary` 24-hour counts, per-subtype counts, seen sensors
- `GET /api/alerts?limit=100` last alerts, max 500
- `GET /api/frames?limit=100` recent frame metadata, max 500
- `GET /api/sensors` last-seen/queue-loss per sensor
- `GET /api/channels` counts grouped by channel

API is **unauthenticated** by design and binds to loopback by default. It must not be internet-facing.
