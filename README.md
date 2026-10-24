# WiFi Sentinel

**Receive-only ESP32-C6 wireless intrusion detection sensor + Raspberry Pi 4 / Fedora collector**

![Status](https://img.shields.io/badge/status-prototype-orange) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Firmware](https://img.shields.io/badge/ESP--IDF-5.5.2%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> **Tested hardware:** ESP32-C6 revision v0.0 with native USB Serial/JTAG, connected to a Raspberry Pi 4 Model B Rev 1.2. ESP-IDF v5.5.4 build/flash, live 2.4 GHz telemetry, runtime channel switching and persistence have been exercised. The exact sensor board product/PCB and antenna remain unidentified. Optional C5/5 GHz support is unvalidated; the connected C6 is **2.4 GHz only**. See [hardware evidence](docs/HARDWARE.md) and [validation limits](docs/VALIDATION.md).

WiFi Sentinel captures a small set of **802.11 management-frame metadata** passively, reports events via USB serial, and applies explainable anomaly rules in a Python collector. It does **not** inject frames, disconnect clients, attempt logins, crack passwords, decode user traffic, or perform countermeasures.

## Scope

| Feature | State | Notes |
|---|---|---|
| Passive deauthentication/disassociation monitoring | Implemented in source | Requires board hardware validation |
| Authentication/association monitoring | Implemented in source | 802.11 management status, not WPA password success |
| Fixed-channel 2.4 GHz selection | Tested on C6 | One channel at a time; optional C5/5 GHz path is unvalidated |
| Protected SSID / unfamiliar BSSID alert | Implemented | Heuristic; configured allowlists needed |
| Sensor IDs and replay | Implemented | One live USB port per collector process; multi-port fan-in is a roadmap item |
| Local web UI / API / SQLite | Implemented | Localhost binding, no login interface |
| Synthetic demonstration and deterministic tests | Implemented | No RF attacks generated |
| Live C6 RF/USB sanity check | Exercised | High-traffic performance, accuracy and PMF remain unvalidated |
| Channel hopping, true RF jamming detection, EAPOL parsing, PCAP | **Out of scope** | Not promised |

## Quick start: software-only demonstration (Fedora, Raspberry Pi OS, macOS, Linux)

```bash
unzip wifi-sentinel.zip
cd wifi-sentinel/collector
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

# Writes simulated frames/alerts to collector/sentinel.sqlite3:
wifi-sentinel demo

# Start dashboard. Without WIDS_SERIAL_PORT this is demo-only:
wifi-sentinel serve
```

Open **http://127.0.0.1:8181**. The synthetic dataset exercises authentication,
deauthentication, disassociation and unsuccessful authentication-response rules.

Run tests:

```bash
python -m pytest -q tests
```

## Hardware steps

The tested sensor is an ESP32-C6, with native USB Serial/JTAG and 2.4 GHz capture.

1. Identify the chip/USB serial and exact board where possible; see [Hardware](docs/HARDWARE.md).
2. Install the tested ESP-IDF v5.5.4 toolchain for `esp32c6`.
3. `cd firmware && idf.py set-target esp32c6 && idf.py menuconfig`.
4. Choose a permitted 2.4 GHz channel and sensor ID. C6 defaults select USB Serial/JTAG and channel 6.
5. Set `SENSOR_PORT` to the **verified** `/dev/serial/by-id/...` path, then run `idf.py build && idf.py -p "$SENSOR_PORT" flash monitor`. Stop any collector using that port first.
6. Verify `WIDS` heartbeats and sampled beacons, then stop the serial monitor.
7. Configure `WIDS_SERIAL_PORT` with the same by-ID path and start the collector. This installation's other ESP currently uses `/dev/ttyACM0`; do not flash or open it.

The source also includes optional C5/5 GHz support; it has not been hardware-validated and is not the connected sensor.

See **[Firmware](firmware/README.md)**, **[Fedora setup](docs/FEDORA_SETUP.md)**, **[Pi setup](docs/RASPBERRY_PI.md)** and **[Validation](docs/VALIDATION.md)**.

## Architecture

```mermaid
flowchart TD
  RF[Nearby 802.11 management frames] --> SENSOR[ESP32-C6 promiscuous RX]
  SENSOR -->|bounded FreeRTOS queue| EXPORT[USB serial NDJSON telemetry]
  EXPORT -->|WIDS v1 messages| READ[Python serial reader]
  READ --> VALIDATE[Protocol validation]
  VALIDATE --> DETECT[Sliding-window IDS rules]
  DETECT --> DB[(SQLite metadata + alerts)]
  DB --> API[FastAPI dashboard API]
  API --> UI[Vanilla JS local dashboard]
```

The radio is **receive-only by application design**: firmware configures STA mode but never joins a network. Monitoring a network does not require its Wi-Fi password. No captured packet payloads, handshake secrets or credentials are persisted. The single radio cannot observe multiple channels simultaneously. Two sensors on two channels provide better continuity than hopping across both.

## Repository map

```text
wifi-sentinel/
├── firmware/                 ESP-IDF C6 receiver; optional C5 target
│   ├── main/main.c           Frame parsing, beacon sampling, queue, NDJSON
│   └── main/Kconfig.projbuild Band, channel, sensor ID, heartbeat
├── collector/
│   ├── wids/                 Protocol, detection engine, storage, CLI, API
│   ├── wids/static/index.html Offline-friendly self-contained web UI
│   ├── tests/                Deterministic Python tests
│   └── pyproject.toml        Dependencies / console script
├── config/collector.env.example
├── docs/                     Detailed architecture, hardware, protocols,
│                             threat model, setup and validation
├── examples/                 Sample NDJSON events and local replay
├── scripts/                  Fedora/Pi bootstrap helper scripts
├── systemd/                  Optional user service template
└── LICENSE
```

## Detection rules

- `deauth_flood`: default 20 observed deauth frames / 10 seconds / sensor/BSSID/channel.
- `disassoc_flood`: default 20 observed disassociation frames / 10 seconds.
- `auth_flood`: default 40 observed authentication frames / 10 seconds.
- `failed_auth_burst`: default 12 nonzero 802.11 authentication/association *status codes* / 10 seconds. **Not equivalent to detecting WPA password-guessing**.
- `protected_ssid_untrusted_bssid`: received beacon/probe response advertises one of your protected SSIDs from a BSSID not in your trusted allowlist. Could be a legitimate new AP; investigate before attributing.

All defaults are tunable environment variables, with 60-second repeat-alert cooldowns. No automated response. See [Detection design](docs/DETECTION.md).

## Responsible scope and data handling

Only monitor networks for which you have authority. 802.11 frame metadata contains MAC addresses and SSIDs and may be personal information. Retain only what you need, secure the Pi filesystem, and avoid sharing raw logs publicly. SQLite data and alerts expire after 7 days by default; attached sensor identity and last-seen information persists until removed. **Dashboard reads have no authentication; configuration writes require a key** and intentionally binds to `127.0.0.1` unless explicitly changed. Use SSH forwarding or a properly protected reverse proxy for remote access. See [Security](SECURITY.md).

## Documentation

- [Dashboard tabs, device observations and animation](docs/DASHBOARD.md)
- [Clickable MACs, vendor details and red alert sources](docs/MAC_LOOKUP.md)
- [Dashboard Configuration and Status dialogs](docs/CONFIGURATION.md)

- [Architecture and data flow](docs/ARCHITECTURE.md)
- [Tested hardware, BOM, board unknowns and scaling](docs/HARDWARE.md)
- [Fedora development and ESP-IDF setup](docs/FEDORA_SETUP.md)
- [Raspberry Pi 4 deployment](docs/RASPBERRY_PI.md)
- [Detection methodology, tuning and false positives](docs/DETECTION.md)
- [JSON telemetry protocol](docs/PROTOCOL.md)
- [Security, privacy and threat model](SECURITY.md)
- [Validation checklist, known issues and acceptance criteria](docs/VALIDATION.md)
- [Operations, backup, troubleshooting](docs/OPERATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [Authoritative upstream references](docs/REFERENCES.md)

## Version and contributions

**Release v1.0.0** (hardware validation remains at prototype scope), MIT licensed. Contributions welcome via PR; run unit tests, review changes for passive-only operation, and document real hardware test results. Run the Python and browser checks locally; no GitHub CI checks were reported for recent PRs. Firmware compilation is a separate manual validation task because the current archive does not bundle the ESP-IDF toolchain.
