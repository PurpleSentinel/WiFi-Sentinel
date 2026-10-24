# WiFi Sentinel

**Receive-only ESP32-C5 wireless intrusion detection sensor + Raspberry Pi / Fedora collector**

![Status](https://img.shields.io/badge/status-prototype-orange) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Firmware](https://img.shields.io/badge/ESP--IDF-5.5.2%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> **Build status:** the Python collector, API, dashboard and synthetic tests run on a development computer. The C firmware is an ESP-IDF implementation intended for ESP32-C5 and **has not been compiled, flashed or RF-validated on the specific eBeetle 2 board** in this release. Validate the board's USB console, antenna, regulatory channels and capture behaviour before treating it as a deployed sensor. No hardware-specific GPIO assignments are assumed.

WiFi Sentinel captures a small set of **802.11 management-frame metadata** passively, reports events via USB serial, and applies explainable anomaly rules in a Python collector. It does **not** inject frames, disconnect clients, attempt logins, crack passwords, decode user traffic, or perform countermeasures.

## Scope

| Feature | State | Notes |
|---|---|---|
| Passive deauthentication/disassociation monitoring | Implemented in source | Requires board hardware validation |
| Authentication/association monitoring | Implemented in source | 802.11 management status, not WPA password success |
| Fixed-channel 2.4 GHz or 5 GHz selection | Implemented in source | One band/channel at a time; requires valid regulatory channel |
| Protected SSID / unfamiliar BSSID alert | Implemented | Heuristic; configured allowlists needed |
| Sensor IDs and replay | Implemented | One live USB port per collector process; multi-port fan-in is a roadmap item |
| Local web UI / API / SQLite | Implemented | Localhost binding, no login interface |
| Synthetic demonstration and deterministic tests | Implemented | No RF attacks generated |
| Real-board RF capture, high-traffic performance, PMF verification | **Not yet validated** | Follow validation checklist |
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

ESP32-C6 boards can also run the sensor on **2.4 GHz only**. See the
[C6 build instructions](firmware/README.md) for native USB Serial/JTAG defaults.

1. Confirm the exact **eBeetle 2 ESP32-C5 board**, console interface and external/internal antenna. The *ESP32-C5 chipset* features are confirmed; the PCB implementation remains a verification item.
2. Install ESP-IDF v5.5.2+ (recommend v5.5.4 patch series) and select `esp32c5`.
3. `cd firmware && idf.py set-target esp32c5 && idf.py menuconfig`.
4. Choose a *legal* fixed 2.4 GHz or 5 GHz channel, sensor ID, console output, and beacon sample factor.
5. `idf.py build && idf.py -p /dev/ttyACM0 flash monitor` (port is an **example**; find yours).
6. Verify the `WIDS` heartbeat prefix and sampled beacons without the collector before connecting to the Pi.
7. On the Pi/Fedora machine run the collector with `WIDS_SERIAL_PORT=/dev/serial/by-id/...` (USB telemetry and sensor configuration).

See **[Firmware](firmware/README.md)**, **[Fedora setup](docs/FEDORA_SETUP.md)**, **[Pi setup](docs/RASPBERRY_PI.md)** and **[Validation](docs/VALIDATION.md)**.

## Architecture

```mermaid
flowchart TD
  RF[Nearby 802.11 management frames] --> C5[ESP32-C5 promiscuous RX]
  C5 -->|bounded FreeRTOS queue| EXPORT[USB serial NDJSON telemetry]
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
├── firmware/                 ESP-IDF esp32c5 management-frame receiver
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
├── .github/workflows/        Python CI
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

Only monitor networks for which you have authority. 802.11 frame metadata contains MAC addresses and SSIDs and may be personal information. Retain only what you need, secure the Pi filesystem, and avoid sharing raw logs publicly. SQLite data and alerts expire after 7 days by default; attached sensor identity and last-seen information persists until removed. **The dashboard has no authentication** and intentionally binds to `127.0.0.1` unless explicitly changed. Use SSH forwarding or a properly protected reverse proxy for remote access. See [Security](SECURITY.md).

## Documentation

- [Dashboard Configuration and Status dialogs](docs/CONFIGURATION.md)

- [Architecture and data flow](docs/ARCHITECTURE.md)
- [BOM, eBeetle 2 hardware unknowns and scaling](docs/HARDWARE.md)
- [Fedora development and ESP-IDF setup](docs/FEDORA_SETUP.md)
- [Raspberry Pi 5 deployment](docs/RASPBERRY_PI.md)
- [Detection methodology, tuning and false positives](docs/DETECTION.md)
- [JSON telemetry protocol](docs/PROTOCOL.md)
- [Security, privacy and threat model](SECURITY.md)
- [Validation checklist, known issues and acceptance criteria](docs/VALIDATION.md)
- [Operations, backup, troubleshooting](docs/OPERATIONS.md)
- [Roadmap](docs/ROADMAP.md)
- [Authoritative upstream references](docs/REFERENCES.md)

## Version and contributions

Initial **v0.1.0 prototype**, MIT licensed. Contributions welcome via PR; run unit tests, review changes for passive-only operation, and document real hardware test results. The Python tests are automated in GitHub Actions. Firmware compilation is a separate manual validation task because the current archive does not bundle the ESP-IDF toolchain.
