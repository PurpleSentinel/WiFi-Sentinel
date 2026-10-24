# Validation and acceptance checklist

## What has been validated for this archive

### ESP32-C6 bring-up — 2026-10-24

- USB chip identification confirmed ESP32-C6 revision v0.0; this is not a C5.
- Built and flashed with ESP-IDF v5.5.4 using the C6 target defaults and native
  USB Serial/JTAG console. Application image size: 806,608 bytes.
- A 35-second serial check received 17 sampled beacons and two heartbeats on
  2.4 GHz channel 6; the latest heartbeat reported zero export queue drops.
- The collector API on localhost port 8181 reported serial enabled, one live
  `c6-sensor-01` sensor, and persisted beacon observations.
- All 21 collector tests passed. FastAPI/Starlette emitted one test-client
  deprecation warning.

This is an initial receive/USB/collector sanity check, not a 24-hour acceptance
test, independent RF comparison, or validation of the C5/5 GHz path.

### Configuration and Status dialogs — 2026-10-24

- Runtime configuration firmware built and flashed to the C6 with ESP-IDF
  v5.5.4; the final application image is 836,752 bytes.
- Live browser control switched the sensor from channel 6 to 11. Both its USB
  acknowledgement and subsequent telemetry confirmed channel 11.
- After resetting the sensor and restarting the collector, channel 11 was
  retained from NVS and collector overrides were loaded from disk. Monitoring
  was restored to channel 6 after verification.
- All 29 collector tests passed, including configuration authorization, origin
  checks, validation, persistence, acknowledgement failures, timeouts,
  disconnects, and fragmented/oversized serial input. One existing dependency
  deprecation warning remains.
- Playwright Chromium checks passed for both dialogs, including multiple-sensor,
  empty and failed-request states, paused opening, save authorization, keyboard
  focus/Escape, and mobile layout. A live-browser save exercised the real USB
  command and collector persistence paths as well.
- Pi Wi-Fi/Ethernet configuration and the other USB ESP device were unchanged.

- Python syntax and unit tests can run on host machine without physical hardware.
- Test cases cover parsing, invalid input rejection, detection windows/cooldowns, allowlists, API and DB writes.
- Synthetic demo is wholly offline and transmits **no RF frames**.

### Dashboard tabs and pulsing logo — software checks

The tabbed dashboard change passed 32 collector tests and three Playwright
Chromium browser checks. Coverage includes device aggregation, unknown SSIDs,
group/zero-address exclusion, API limits, keyboard tab navigation, active-tab
polling, pause/refresh behavior, filters/export, dialogs from every view,
empty/error states, safe SSID rendering, mobile layout, and reduced-motion
branding. These checks do not extend RF coverage or validate additional hardware.
All four views also loaded successfully against the running LAN collector; the
Devices view displayed 30 observed addresses during that check. Live reduced-motion
rendering produced a static logo, with no browser JavaScript errors.

## What has NOT been validated

- Compilation against a complete ESP-IDF toolchain, especially ESP32-C5-specific Wi-Fi band mode and RX metadata declarations.
- eBeetle 2 hardware USB console/boot flow, antenna, flash capacity and power consumption.
- Validity of 5 GHz promiscuous receive on the exact board/firmware combination.
- Wi-Fi frames captured under PMF/WPA3 networks on production hardware.
- High-rate loss/deduplication, multiple simultaneously active real RF sensors.
- Intrusion-detection sensitivity/specificity under realistic RF noise.

The project is deliberately labelled **prototype**, not certified security equipment.

## Test plan

### Stage A: software only

```bash
cd collector
python -m pip install -e '.[dev]'
python -m pytest -q tests
wifi-sentinel demo
wifi-sentinel serve
```

Verify dashboard shows synthetic counts and at least 3 triggered flood/failed-status alert types. Check `/api/summary`, `/api/alerts`, `/api/frames`, `/api/health`.

### Stage B: build & flash

```bash
source ~/esp/esp-idf/export.sh
cd firmware
idf.py set-target esp32c5
idf.py build
idf.py -p /dev/ttyACM0 flash monitor
```

Log exact board marking, PCB revision, ESP chip revision, IDF patch version, USB VID/PID/port, selected console mode, RAM/flash usage and compile warnings/errors. Resolve all build issues; do not claim binary compatibility until checked.

### Stage C: passive RF sanity check

- [ ] Confirm normal boot and heartbeat `WIDS` lines with unique sensor ID.
- [ ] Place near your own AP on an authorised, quiet 2.4 GHz channel.
- [ ] Set beacon sample N=1 and verify parsed SSID/BSSID/channel and plausibly varying RSSI.
- [ ] Confirm no unexpected `esp_wifi_connect`/packet transmission in source or observed behaviour.
- [ ] Return sampling to N=20 and measure `dropped` counter during a busy period.
- [ ] Repeat on a legitimate, region-permitted 5 GHz channel after choosing 5 GHz Kconfig mode.
- [ ] Verify observer reports match independently captured (authorised) monitor-mode management metadata (e.g. a laptop Wi-Fi adapter that supports monitor mode).
- [ ] Verify protected management frames are not parsed as plaintext reason codes.

### Stage D: live harmless operational validation

- [ ] Restart a test AP under your control and review normal disconnect management traffic.
- [ ] Connect/disconnect approved test devices to observe association/authentication frames.
- [ ] Verify time drift between firmware uptime and collector ingest UTC timestamps.
- [ ] Validate serial unplug/replug reconnect and loss reporting.
- [ ] Validate restore/restart leaves SQLite readable and old data expires after configured period.
- [ ] Tune thresholds from normal baseline; document known false-positive patterns.

Do not stage disruptive deauthentication floods against live networks; synthetic playback exercises rules without active attack traffic.

## Acceptance criteria for a first deployed sensor

1. All host tests green, firmware compiles without unexplained warnings, documented board-flashing process.
2. Passive receive on exact intended channel confirmed for at least 24 hours.
3. Heartbeat seen approximately every configured interval and sustained `dropped` counter remains zero or operationally acceptable.
4. Counts/alerts consistent with a separate authorised observation method.
5. Documented channel coverage and privacy retention, localhost-only or authenticated remote access.
6. False-positive review performed with actual AP maintenance/roaming events.
