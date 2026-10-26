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

### Lossless SSID transport — 2026-10-24/25

- All 83 collector tests passed. Host-compiled checks exercise the firmware's
  actual SSID extraction/hex serialization header and feed its output through
  the collector, SQLite and API. A synthetic UTF-8 `Café` beacon triggered the
  protected-SSID/untrusted-BSSID alert.
- Coverage includes arbitrary/invalid UTF-8, NUL/control bytes, quotes and
  backslashes, distinct escaped-looking names, the 32-byte boundary, hidden /
  missing / malformed information elements, conflicting text/hex, exact-byte
  rules, Unicode case expansion and legacy database migration.
- Five Playwright checks passed, including Unicode display and raw-byte popup
  metadata, plus existing dialog, filtering, highlighting and mobile behavior.
- ESP-IDF v5.5.4 built the C6 image (837,280 bytes, 20% app-partition headroom).
  The monitoring sensor was flashed through its verified by-ID port without
  erasing NVS. Live sampled SSIDs included `ssid_hex` values that decoded to the
  stored display text; the MAC popup and configuration guidance were verified.
- Sensor ID, channel 6, sample factor 20 and heartbeat interval 15 seconds were
  preserved. No Pi network or other ESP device settings were changed.
- The Unicode alert check was synthetic and sent no RF traffic; this does not
  claim an independently captured live Unicode AP or extend C5/RF validation.

### Recurring protected-SSID alerts — 2026-10-25

- All 90 collector tests passed. Controlled-time tests verified suppression
  within cooldown and renewed alerts exactly at expiry for beacon and probe
  response sightings, including UTF-8 SSIDs.
- Tests cover shared per-BSSID/channel cooldowns across advertised protected
  names, independent channel/sensor cooldowns, returning APs, pruning, trusted /
  unprotected exclusions, and protected checks outside the monitored-BSSID list.
- A running API regression persisted repeated alerts without restarting the
  detector and generated a new alert after earlier alert history expired.
- The deployed LAN collector remained healthy with the original sensor ID,
  channel 6, sample factor 20 and 15-second heartbeat. No firmware flash, sensor
  settings or Pi network changes were required.

### Bounded per-AP advertisement sampling — 2026-10-25

- All 100 collector tests passed. Host-compiled simulations use the firmware's
  actual sampler header. Four periodic AP streams at N=20 produced
  `[50, 50, 50, 50]` across 4,000 events, instead of the original global-counter
  result `[0, 0, 0, 200]`.
- Checks cover independent beacon/probe and channel counters, factors 1–1000,
  factor changes, unsampled management subtypes, and 100,000 unique-address churn
  events. The fixed 64-entry state remained under 2 KiB in the host check;
  evicted returning identities were immediately admitted.
- Five Playwright checks passed, including sensor-reported sampling-mode display
  in Configuration. The live dialog also showed the upgraded mode correctly.
- ESP-IDF v5.5.4 built and flashed the C6 image (837,728 bytes, 20% app-partition
  headroom). Capabilities reported `per_bssid_channel_subtype` and capacity 64.
  All recorded sensor settings matched their pre-flash values: channel 6,
  sampling N=20, heartbeat 15 seconds and sensor ID `c6-sensor-01`.
- Live advertisements continued with zero reported queue drops. Only one BSSID
  was active during the live check; multi-AP fairness was verified by the
  deterministic host simulation, not an independent multi-AP RF experiment.
- No Pi network or other USB ESP device settings were changed.

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

## Issue #25 — passive BLE monitoring (2026-10-25)

- ESP-IDF **5.5.4**, ESP32-C6 target: firmware builds successfully with NimBLE
  observer enabled; central, peripheral and broadcaster roles are disabled.
  Scanning uses `passive=1`, no duplicate filtering in the controller, and no
  advertising, pairing, connection or scan-request path in application code.
  Software RF coexistence is enabled. Application image: **1,119,456 bytes**,
  **27%** of the large single-app partition remains free. Full `flash_args`
  programming verified the bootloader, application and partition-table hashes.
  NVS at 0x9000 was preserved.
- Collector regression suite: **118 passed**. Tests exercise strict BLE wire
  bounds and address types, raw-byte preservation, absent/malformed AD fields,
  16/32/128-bit service UUID normalization, name/company/service/address rules,
  duplicate suppression, per-sensor/rule cooldown under address churn, cache
  capacity, indexed storage, independent BLE retention, record caps, API reads,
  configuration validation/persistence, legacy sensor support, and startup policy
  application before cleanup. The existing Starlette/httpx deprecation warning
  remains unrelated to this feature.
- **Six browser checks passed**, including separate BLE/Wi-Fi tables, BLE
  configuration toggles, scan status, raw detail display, safe text rendering,
  red alert-source addresses, and no MAC-vendor request for random BLE addresses
  even when their bits look like a globally registered MAC. Existing keyboard,
  dialog, polling/pause, mobile and reduced-motion checks pass.
- Flashed only the designated C6 at the stable by-id path ending
  `40:4C:CA:4D:6F:E4-if00`; the unrelated ESP device was not opened.
  BLE enable and disable were acknowledged through the authenticated dashboard
  API. Sensor ID `c6-sensor-01`, Wi-Fi band 2.4 GHz, channel **6**, beacon sample
  factor **20** and heartbeat **15 seconds** remained unchanged.
- Uncontrolled live comparison, two successive **30-second** windows with BLE
  interval/window **100/20 ms**:

  | BLE mode | Stored Wi-Fi reports | Retained BLE observations | BLE status |
  |---|---:|---:|---|
  | Disabled | 17 | 0 | Not scanning; error 0 |
  | Enabled | 11 | 50 | Scanning; error 0 |

  In the enabled phase, firmware status snapshots advanced from 1 to 435 BLE
  advertisement reports and from 0 to 28 dropped/rate-limited BLE reports.
  Configuration/status snapshots refresh every five seconds, so those counters
  do not have exact phase-boundary timing. Wi-Fi heartbeat queue drops remained
  **0**. Free heap was about **236.6 KB**, with a minimum around **233.2 KB**.
  These are sampled, environmentally variable observations, **not** a controlled
  RF packet-loss measurement or evidence of reliable simultaneous coverage.
  Espressif rates this sniffer/scan combination as unstable; see [BLE limits](BLE.md).
- Live payloads included names `Linksys` and `LHB-039D31AE`, public and random
  addresses, service UUIDs and manufacturer data. These advertised identities
  were not independently verified against a controlled physical test device.
  Parser/rule tests use deterministic fixtures; no test advertisements or attack
  frames were transmitted. Controlled device verification and extended RF soak
  testing remain deployment validation tasks.
- A browser against **http://10.81.1.177:8181** showed live BLE Overview counts,
  31 advertiser rows at that moment, a functioning BLE detail dialog, scanning
  status, and Reporting observations. No JavaScript errors or page overflow at
  390 px were found. Address counts are not physical-device counts.
- Reset the C6 and restarted the collector: BLE remained enabled at 100/20 ms,
  scan state returned true with error 0, and all saved Wi-Fi settings remained
  intact. Left BLE enabled on this installation, with default empty BLE alert
  rules. The collector remains on its existing Ethernet LAN bind address.
  No Pi Ethernet or Wi-Fi configuration was changed; `wlan0` remains without a
  carrier. The existing transient service still requires the documented startup
  arrangement after a Pi reboot.

### Dedicated BLE tab

The BLE 24-hour count, advertiser summaries and latest advertisements now live
in a fifth **BLE** tab immediately after **Devices**. Devices and Reporting only
fetch and show Wi-Fi data. Six browser checks cover the new order, BLE details,
keyboard navigation, active-tab loading, pause behavior and mobile layout. A live
LAN browser also confirmed populated BLE tables and no JavaScript errors.

### BLE documentation audit

Updated the README, setup/build guides, architecture, dashboard/configuration,
protocol/detection, hardware, operations, security/privacy, vendor-data guidance,
contributor guidance, references and roadmap for passive BLE and the fifth tab.
Historical validation entries above retain their original measurements; current
BLE observations are in the dedicated BLE tab rather than Overview/Devices/
Reporting. The software-only BLE replay example was checked against the collector
parser/storage, and relative Markdown file links and changed-file checksums were
verified. Documentation describes controlled-device and extended-advertisement
validation as outstanding rather than claiming those tests passed.

## Issues #28/#29 — BLE explorer and RSSI curve (post-v1.2)

- **123 collector tests** and **seven browser checks** pass. The new coverage
  exercises SIG company/service name decoding, unknown identifiers, label
  precedence/provenance, random-address formats, exact sensor/address/type
  separation, protected alias writes, persistence/deletion/caps, pre-limit
  search/filter/sort and legacy BLE name backfill.
- Browser checks exercise the selected-advertiser model with A=-59 dBm and n=2:
  -59 dBm maps to 1 metre; -79 dBm maps to 10 metres. They also exercise median
  smoothing, invalid/non-finite and missing inputs, stale/out-of-window samples,
  out-of-plot estimates without clamping, independent per-identity model settings,
  pause behavior, protected aliases, safe text and mobile layout.
- The offline snapshot was retrieved from official Bluetooth SIG public YAML:
  **4057 company IDs** and **76 standard service UUIDs**, with embedded retrieval
  UTC, source URLs and raw-source digests. Unknown IDs remain numeric; names and
  service/company labels are unverified claims, not model/owner identity.
- Backed up the live collector database and restarted the service. Startup
  migrated retained local-name evidence and created label storage. Existing
  C6 firmware, saved Wi-Fi/BLE settings and Pi networking were not changed.
- A live LAN browser loaded 200 capped advertiser summaries from roughly 803
  identities at that moment, displayed readable evidence labels, selected an
  exact identity and rendered an uncalibrated decay curve with its raw RSSI.
  Desktop and 390 px mobile screenshots were visually inspected. No JavaScript
  errors or mobile page overflow were observed.
- This verifies software behavior and live presentation, **not physical ranging
  accuracy**. No controlled RF calibration or distance-reference experiment was
  performed. The initial A/n values are illustrative, and the measured-reference
  checkbox is an operator assertion only. The model uses at most 100 retained,
  possibly filtered/deduplicated samples, not an exhaustive RSSI stream.
- Updated repository docs and hierarchical wiki cover the explorer, alias privacy,
  registry provenance/maintenance, browser-session model controls and calibration
  limits. These are post-v1.2 enhancements, not content in its original archive.

## Issue #31 — full-width dashboard layout

Removed the 1460px page cap and aligned the header/content with shared 18–36px
responsive gutters. Eight browser checks pass, including all five tabs at
1920, 2560, 768, 390 and 320px widths and viewport-fitting dialogs. BLE checks
also verify the selected workspace and RSSI plot use the extra desktop width.
Live LAN checks cover actual advertiser/curve rendering on wide and mobile
screens. No collector, firmware, radio or host networking changes are required.

Alerts height follow-up: a browser-only 80-row fixture confirmed the Alerts table
expands beyond the former 480px cap with no internal vertical overflow at 1920px
and 390px. No fixture alerts were stored in the collector database.

## Devices table — compact BSSID context redesign

The live 200-row Devices result contained up to eight BSSIDs per address, with
16 rows containing multiple contexts. They were previously joined into a single
nowrap cell. The table now uses proportional bounded columns, wrapping text,
separate date/time lines and two vertical BSSID previews. Longer lists open a
searchable full-context dialog without changing table width.

Browser coverage uses an 80-BSSID fixture to verify bounded desktop table width
at 1280/1920/2560px, contained mobile overflow, all-context visibility, filtering,
red source highlighting and Escape/focus restoration. Nine distinct dashboard
browser checks pass (the five tab checks were rerun after the Escape fix).
A live 1366px check measured a 1267px table within its 1267px panel, with no
horizontal overflow. Nested MAC details and mobile dialog sizing were verified.
No backend records, RF settings or Pi networking were modified by this redesign.

Devices height follow-up: removed its internal 480px cap. The live 200-row table
expanded to its full content height at desktop/mobile sizes with no inner
vertical overflow or unintended page-level horizontal overflow.

Devices sorting follow-up: all nine headings have paired direction arrows and
accessible keyboard controls. Six tab browser checks pass, including numerical
frames (2/10/100), chronological timestamps, channels, SSIDs, BSSID counts and
persistence after redraw. Live 200-row checks verify ascending/descending frame
sorting and mobile containment. Sorting acts on loaded rows without backend or
sensor configuration changes.

## Issue #33 — BLE unique-device metric

Added a Unique devices card matching Capture Freshness styling. The API's
`ble_unique_addresses_24h` counts distinct advertiser MAC addresses across
sensors/address types over retained 24-hour observations, independent of table filters/caps.
It does not merge identities using names, aliases, company data or RSSI and does
not claim exact physical-device counts.

124 collector tests pass, covering empty data, repeated reports, cross-sensor
deduplication across address types, old observations and counts beyond the
200-row UI limit. Browser checks cover matching styles, accessible descriptions,
refresh/pause, independence from table filters and preserving the last metric
value on refresh error. Fixed fixture time makes existing smoothing checks
independent of browser execution speed.

The live LAN aggregate reported 966 distinct addresses during the
check. Four/two/one-card layouts were verified at 1920/768/390px with no page
overflow or JavaScript errors. Only the collector service was restarted; sensor
and host network settings were unchanged. Repository docs and wiki explain the
metric definition and address-rotation limitations.

MAC-only clarification: Unique devices now uses `COUNT(DISTINCT address)`,
ignoring both sensor and public/random address type. One MAC with three
sensor/type identities counts as one unique device in tests. A live snapshot
showed 975 distinct MACs and 975 advertiser identities: equality is legitimate
when each MAC has only one sensor/type combination. Collector tests (124) and
both BLE browser checks pass with the corrected definition.

## Rolling-hour BLE display (2026-10-26)

BLE advertisement counts, MAC-only counts, advertiser identities and list/name
aggregates now use a rolling last hour. The selected advertiser's observation
count also uses that hour; raw history remains inspectable and no retention or
stored observations are reset. Existing daily summary fields remain available,
and Wi-Fi's 24-hour reporting is unchanged.

125 collector tests and ten browser checks pass. Coverage includes the exact
one-hour boundary, exclusion just outside the window, cross-sensor MAC
aggregation, preserved older/raw records, legacy daily fields and hourly UI labels.
The live LAN check reported 127 distinct MACs / 5624 reports in one hour versus
1604 distinct MACs in 24 hours; the list reported `window_hours:1`. These are
addresses, not authenticated physical devices. The collector was restarted to
load the new queries; sensor and host network settings were unchanged.

## System diagnostics

`test_system_metrics.py` checks CPU/memory calculations, missing/permission-restricted reads, SQL time budgets, unchanged database files, cache reuse/expiry, concurrency and API output. `browser_system.py` covers toolbar order, paused/manual and periodic reads, close/focus, errors and narrow screens. See [System](SYSTEM.md).

## Data purge validation

`test_purge.py` covers strict UTC cutoff boundaries, scopes, invalid ages, read-only previews, expiry, preserved records, BLE accounting, partial failure, cancellation, duplicate/concurrent jobs, cooperating ingestion/retention and API authorization. `browser_purge.py` covers preview invalidation, confirmation, errors, progress/Pause, no-match state, key clearing, nested-dialog focus and mobile layout. Destructive checks use isolated databases. See [Purge](PURGE.md).

On the deployed Raspberry Pi 4, an isolated 100,000-frame fixture preview took 0.058 seconds and purge took 6.322 seconds. Concurrent ingestion preserved all 202 new frames; the maximum measured ingest call was 0.020 seconds. This is a local measurement, not a latency guarantee. Live production verification uses preview only.

## Automatic retention validation

`test_automatic_retention.py` covers legacy day settings and hour precedence, exact UTC boundaries, disabled age cleanup with active BLE cap, preview/authorization, persistence, busy coordination, scheduling and error retry. `browser_retention.py` checks the nested Configuration window, custom ages, preview invalidation, key handling, Pause, focus and mobile layout. Destructive tests use isolated databases; live Pi verification previews only. See [Retention](RETENTION.md).

On the Raspberry Pi 4, an isolated 100,000-frame fixture gave a 0.053-second retention preview and a 6.131-second automatic cleanup. All 202 concurrent new frames survived; the longest measured ingest call was 0.020 seconds. These are fixture measurements, not latency guarantees.
