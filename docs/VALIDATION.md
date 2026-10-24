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

### MAC lookup and hardware documentation audit — 2026-10-24

- 43 collector tests passed, including exact multi-source alert persistence,
  legacy schema migration, source expiry, normalized lookup, longest-prefix
  matching, prefix-only network requests, persistent cache reuse, and offline /
  corrupt-cache / missing-registry fallbacks.
- Four Playwright browser checks passed, covering clickable MACs and red source
  highlighting across tabs and nested Configuration lookups, vendor text safety,
  retry/error states, mobile layout, focus restoration, and existing controls.
- The live popup for the retained Nokia BSSID loaded its registered organization,
  additional organization address, local observations and legacy alert context.
  The older alert correctly retains an unknown contributing-source identity.
- `/proc/device-tree/model` confirmed Raspberry Pi 4 Model B Rev 1.2. Hardware
  documentation now uses the tested C6 / Pi 4 path and records board-level
  unknowns, while separating optional unvalidated C5/5 GHz claims.
- Cross-document hardware-reference searches and local Markdown-link checks
  passed. Sensor channel remained 6; no Pi network or other ESP device settings
  were modified, and no firmware reflash was needed for these changes.

### Device role classification — 2026-10-24

- 55 collector tests passed, including advertisement-based AP evidence, hidden
  SSIDs, association/reassociation client evidence, rejected responses, mixed
  roles, inconsistent headers, evidence expiry, and server-side role filtering
  before limiting results. Existing source highlighting and lookup tests passed.
- Five Playwright browser checks passed, including role labels/evidence, filter
  persistence, paused filtering, popup consistency, red source links, keyboard
  controls and mobile layout.
- Live API checks distinguished 11 Access Points, one Client / Host and 25
  Unknown addresses at the time of verification. All four role filters matched
  their API classifications. The Nokia MAC popup displayed AP classification
  with its advertisement evidence. No browser JavaScript errors were observed.
- Monitoring remained on channel 6. No firmware or Pi network changes were made.

### Idle retention cleanup — 2026-10-24

- All 58 collector tests passed. A time-controlled running-server test advanced
  the clock past retention, ticked the independent cleanup timer, and verified
  expired frames and alerts disappeared from the APIs with no further ingestion.
  Sensor registration remained present.
- Regression checks confirmed cleanup failures are logged and retried, and
  shutdown joins the worker before closing SQLite, including context exceptions.
- The live service reported its 60-second retention schedule at startup; the
  LAN API remained healthy and the sensor remained on channel 6.

## What has NOT been validated

- C5 compilation and hardware operation; only the C6 target has been built/flashed in this installation.
- Exact C6 board model/PCB, antenna arrangement, flash capacity and power consumption; no eBeetle 2 board identification has been established.
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

### Stage B: build & flash the C6

Set `SENSOR_PORT` to the verified by-ID path from [Hardware](HARDWARE.md) and stop the collector first. Do not use the other ESP device's port.

```bash
source ~/esp/esp-idf/export.sh
cd firmware
idf.py set-target esp32c6
idf.py build
idf.py -p "$SENSOR_PORT" flash monitor
```

Log exact board marking, PCB revision, ESP chip revision, IDF patch version, USB VID/PID/port, selected console mode, RAM/flash usage and compile warnings/errors. Resolve all build issues; do not claim binary compatibility until checked.

### Stage C: passive RF sanity check

- [ ] Confirm normal boot and heartbeat `WIDS` lines with unique sensor ID.
- [ ] Place near your own AP on an authorised, quiet 2.4 GHz channel.
- [ ] Set beacon sample N=1 and verify parsed SSID/BSSID/channel and plausibly varying RSSI.
- [ ] Confirm no unexpected `esp_wifi_connect`/packet transmission in source or observed behaviour.
- [ ] Return sampling to N=20 and measure `dropped` counter during a busy period.
- [ ] Optional C5 only: separately qualify a C5 board before testing a permitted 5 GHz channel. The connected C6 cannot perform this test.
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
