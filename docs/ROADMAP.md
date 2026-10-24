# Engineering roadmap

## Phase 0 (included)

- Receive-only ESP-IDF 802.11 management metadata firmware for C5.
- Queue bounded event export over USB serial with heartbeat/drops.
- Python SQLite/FastAPI collector with v1 schema validation.
- Threshold rules, known-SSID/BSSID heuristic, tests, offline demo and dashboard.

## Phase 1 (highest priority)

- Hardware bring-up on exact eBeetle 2 PCB and C5 ESP-IDF patch version.
- Confirm native USB / UART console, dual-band RX, channel behaviour, power/antenna.
- Firmware compilation in CI (version-pinned ESP-IDF) and representative test fixtures.
- Add explicit collection-lag metadata and loss counters to the dashboard.
- Periodic retention cleanup timer and configured log rotation.

## Phase 2

- Multi-port serial fan-in with bounded async ingest queue, backpressure and per-sensor health.
- Channel coverage schedule per sensor, sensor inventory, AP allowlist management UI.
- Detection of high-rate association requests from diverse sources and abnormal auth patterns.
- Per-BSSID baseline/variance detectors, suppression for maintenance windows.
- Explicit PMF capability advertising based on RSN IE parsing (separate from PMF verification).

## Phase 3

- MQTT/TLS or HTTPS mutually authenticated uplink when remote untethered sensors are required (requires independent reliable networking and RF capacity planning).
- Authenticated UI (SSO), TLS, audit logging, RBAC and multi-user access.
- Optional external alert sinks (webhooks/Slack), alert acknowledgement and analyst notes.
- Export formats and SIEM integration; richer incident correlation with approved AP logs.
- Retention controls to support data-protection assessments.

## Not planned

Frame injection, deauth transmission, password guessing, automatic disconnects, covert collection, or network disruption. This is an observation and detection platform.
