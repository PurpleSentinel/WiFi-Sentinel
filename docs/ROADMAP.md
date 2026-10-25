# Engineering roadmap

## Phase 0 (included)

- Receive-only ESP-IDF 802.11 management metadata firmware tested on C6; optional C5 path remains unvalidated.
- Queue bounded event export over USB serial with heartbeat/drops.
- Python SQLite/FastAPI collector with v1 schema validation.
- Threshold rules, known-SSID/BSSID heuristic, tests, offline demo and dashboard.
- Optional passive legacy BLE advertisement monitoring, bounded retention and alerts,
  with separate BLE dashboard tables and shared-radio status. See [BLE limits](BLE.md).

## Phase 1 (highest priority)

- Establish the deployed C6 board product/PCB, antenna, power and flash details; complete longer RF validation.
- Separately qualify an actual C5 board before claiming tested 5 GHz support.
- C6 native USB, channel switching and NVS persistence have been exercised. UART and C5 dual-band receive still need hardware validation.
- Firmware compilation in CI (version-pinned ESP-IDF) and representative test fixtures.
- Add explicit collection-lag metadata and loss counters to the dashboard.
- Configure log rotation. Retention cleanup now runs on a 60-second service timer, including while ingestion is idle.

## Phase 2

- Multi-port serial fan-in with bounded async ingest queue, backpressure and per-sensor health.
- Channel coverage schedule per sensor, sensor inventory, AP allowlist management UI.
- BLE extended-advertisement/PHY support, controlled known-device validation and
  longer shared-radio loss/throughput measurements; these are not supplied by
  the current passive legacy scanner.
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
