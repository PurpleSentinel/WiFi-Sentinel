# Release 1.3.0

Release 1.3.0 updates the Raspberry Pi/Fedora collector and dashboard with BLE
investigation tools, a more usable dashboard, and host/storage controls. The
ESP32-C6 firmware source is unchanged from v1.2.0 and retains its v1.2.0 label;
no new firmware binary is attached or flashing required for this release.

## Changes since v1.2.0

- **BLE investigation (#28/#29):** readable evidence-based advertiser labels,
  offline Bluetooth company/service names, key-protected aliases and notes,
  search/filter/sort, raw evidence, and an approximate RSSI distance-decay plot
  with adjustable reference/exponent and optional median. Address rotation
  prevents exact physical-device counts; the plot is not a location measurement.
- **Dashboard layout (#31 and follow-up):** full-width responsive views, more
  visible alert/device rows, bounded BSSID context display, sortable Devices
  columns and improved BLE layout.
- **Recent BLE metrics (#33 and follow-up):** a distinct-MAC summary card and
  rolling one-hour BLE counts and advertiser view. A distinct MAC address is not
  necessarily a distinct physical device; retained history still follows its
  configured policy and cap.
- **System (#36):** a toolbar dialog for Pi host health, process/disk use,
  read-only SQLite file/page/table metrics, retention policy and separate vendor
  cache information. It polls only while open and respects Pause.
- **Purge (#38):** a separate System dialog for one-time age-based deletion.
  Category/age selection, read-only preview, key and typed confirmation, bounded
  batch progress and stop requests make scope and actual deletion visible.
- **Automatic retention (#40):** a Retention window in Configuration for
  independent Wi-Fi/BLE maximum ages, automatic age deletion, scheduling and BLE
  count cap. Shorter/expanding deletion policies require preview and typed
  confirmation. Existing seven-day default and day-based settings are preserved
  until changed; the cap still applies if age deletion is switched off.

## Upgrade

1. Stop the collector. Back up `collector/sentinel.sqlite3` using a consistent
   SQLite backup, or copy it **after stopping** so WAL changes are included. Back
   up the adjacent `.settings.json`, `.config-key`, `.vendors.sqlite3` files and
   local `.env` separately. Protect those copies as sensitive data. The database
   path may be customized; use the paths in your installation.
2. Upgrade the collector source/package to v1.3.0 and restart the service. On
   startup, existing automatic retention applies its current age and BLE count
   limits. Records already past those limits can be deleted immediately. Review
   the current values in **Configuration → Retention** before changing them.
3. Open **System** for host/database status, **BLE** for the explorer and hourly
   metrics, and **Configuration → Retention** for ongoing policy. **System →
   Purge** is for a separate one-time deletion; use its preview before confirming.

The default dashboard port remains **8181**. Updating the collector does not
change Pi Wi-Fi, Ethernet or sensor NVS settings. The connected C6 remains
2.4 GHz Wi-Fi plus passive legacy BLE; 5 GHz requires different, validated
hardware. Existing C6 v1.2.0 firmware is compatible with the v1.3.0 collector.
This release publication does not restart or reflash an existing installation.

## Validation and limits

- **152 collector tests** and **13 Playwright browser checks** passed during
  Release 1.3 preparation. A local 1.3.0 collector wheel was built and its
  metadata and bundled dashboard asset verified. Existing Starlette/httpx test-client deprecation
  warning remains.
- On an isolated Pi 4 database with 100,000 old frames, one-time Purge preview
  took 0.058 s and deletion 6.322 s; automatic retention preview took 0.053 s
  and cleanup 6.131 s. Each preserved 202 concurrent new frames, with a maximum
  measured ingest call of 0.020 s. These are fixture measurements, not latency
  guarantees. The live production workflows were checked using read-only preview;
  no test-triggered purge or retention policy save was run on the live database.
- The deployed Pi 4/C6 continued reporting through USB and the LAN dashboard at
  `10.81.1.177:8181`. The C6 firmware was not rebuilt or reflashed for this
  collector/dashboard release.
- Radio validation remains at prototype scope. Only passive legacy BLE 1M
  advertisements are supported. Wi-Fi and BLE share a C6 radio, so simultaneous
  coverage can miss traffic. Extended BLE, physical identity continuity and
  C5/5 GHz hardware remain unvalidated.
- Dashboard read APIs, including System and retention/purge previews, remain
  unauthenticated. Configuration and deletion writes require the key and
  same-origin request, but the dashboard still needs a trusted LAN or an
  authenticated TLS/SSH access path. Purge and shorter retention policies can
  permanently delete history; backed-up copies may retain it separately.

GitHub generates source archives for the tag. There is no release-specific
firmware binary or bundled ESP-IDF toolchain. Build firmware from source only
for the verified target if you need to reflash.

[Full changes since v1.2.0](https://github.com/PurpleSentinel/WiFi-Sentinel/compare/v1.2.0...v1.3.0)
