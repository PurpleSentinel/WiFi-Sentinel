# Operations runbook

The tested deployment is a Raspberry Pi 4 with a USB ESP32-C6. Use its verified by-ID path; another ESP currently occupies `/dev/ttyACM0`. See [Hardware](HARDWARE.md).

## Start/stop

```bash
cd wifi-sentinel/collector
source .venv/bin/activate
wifi-sentinel serve
# Ctrl+C stops collector
```

For systematic boot start, see `docs/RASPBERRY_PI.md` for the user service template.

## Health

```bash
curl -s http://127.0.0.1:8181/api/health
curl -s http://127.0.0.1:8181/api/summary
curl -s 'http://127.0.0.1:8181/api/alerts?limit=10'
```

`/api/health` means only that the web service is reachable; it does not assert an active USB or healthy RF receive path. `/api/sensors` gives last-seen UTC and queue drop count; check it too.

## Common problems

| Symptom | Checks |
|---|---|
| `idf.py: command not found` | Source ESP-IDF `export.sh`, confirm correct virtual env/toolchain |
| Unknown target `esp32c6` | ESP-IDF too old; use v5.5.2+ |
| Flash port not found | Check actual PCB USB data path/cable, `lsusb`, `dmesg`, `/dev/serial/by-id` |
| Permission denied on `/dev/tty*` | User group and active session; stop any other serial terminal |
| No `WIDS` lines | Wrong console selected, firmware not flashed, capture quiet; heartbeat should still appear |
| Only heartbeat but no frames | Wrong channel/band, RF placement/antenna, receive configuration; reduce beacon sampling temporarily |
| Frame channel 0 or unexpected | Verify ESP-IDF promiscuous RX metadata on the actual C6 revision (or separately qualified C5) |
| `dropped` increasing | Reduce beacon telemetry, shorten USB path/avoid overloaded Pi, check host logs |
| All rules quiet while frames arrive | Threshold too high, wrong BSSID filters, no relevant subtype |
| Many rogue-SSID alerts | Complete list of legitimate multi-BSSID APs and extenders/mesh nodes |
| UI unreachable remotely | Expected: default binding is 127.0.0.1; use SSH forward, not public exposure |
| Wrong timestamps | Pi host clock not synced, USB ingestion delay, data uses host UTC receive time |

## Retention

**Configuration → Retention** manages ongoing Wi-Fi/BLE age limits, the automatic
age deletion switch, cleanup interval and the BLE record cap. It previews the
impact before a key-protected save. Age cleanup runs at startup when enabled,
after a confirmed policy save and on the configured schedule (default 60 seconds).
The BLE cap remains active even when age deletion is disabled. Cleanup uses
committed batches of at most 500 rows per table and yields between batches.

The Retention window and `GET /api/retention` show last run, rows deleted,
errors, and next scheduled time. Failed runs retry on the next interval. A manual
Purge blocks a new automatic run until it finishes. Shutdown joins workers before
SQLite closes. Sensor records/labels, configuration and vendor cache are excluded.
CLI demo/replay construction still applies startup policy. See [Automatic
retention](RETENTION.md) for exact cutoffs, preview, compatibility and backup.

## Backup / incident preservation

- Stop collector before copying the database, or use SQLite's backup API rather than copying a live WAL-mode DB file alone.
- Preserve DB provenance (hostname, UTC time, collection channel, detector config, SHA256 digest) and avoid altering the original.
- Export only minimum data necessary, encrypted at rest if transferred.
- Deleting SQLite database and WAL/SHM files resets the local store (stop application first).
- Frames do **not** contain raw 802.11 packet bytes. This is not a replacement for a full forensic capture tool.

## Updating

Back up SQLite, check `git diff` and release notes, run Python tests and repeat firmware smoke tests for changed IDF versions. Avoid auto-upgrading firmware without a verified rollback process. There is no general migration framework; startup migrations add nullable alert source-identity and frame `ssid_hex` columns compatibly. Legacy alert sources and original SSID bytes remain unknown where they were not recorded. See [MAC details](MAC_LOOKUP.md).

Upgrade the collector before flashing raw-SSID firmware. Old text-only telemetry
is accepted by the new collector, but an old collector cannot decode `ssid_hex`.
The database upgrade preserves historical SSID display text rather than guessing
which bytes an older sensor replaced. For the full SSID test suite install a
host C compiler; the firmware codec integration checks otherwise report skips.

## BLE operation and troubleshooting

Upgrade the collector before flashing BLE firmware. Stop the serial reader,
flash the complete generated image set including the large-app partition table,
and preserve NVS. Startup creates separate `ble_observations` and `ble_alerts`
tables alongside existing Wi-Fi data. Back up the complete database and saved
collector settings; raw BLE advertising bytes are part of that backup.

Enable BLE through Configuration, confirm **Status** reports passive scanning and
error 0, then open **BLE** immediately after Devices. Devices and Reporting now
show Wi-Fi data only. Use your configured dashboard address in these read-only
checks (loopback is the default; an Ethernet-bound deployment uses its LAN IP):

```bash
curl -s http://127.0.0.1:8181/api/configuration
curl -s 'http://127.0.0.1:8181/api/ble/devices?limit=20'
curl -s 'http://127.0.0.1:8181/api/ble/observations?limit=20'
```

| Symptom | Checks |
|---|---|
| BLE controls unavailable | Update sensor firmware; confirm USB connection and reported BLE capability |
| BLE enabled but not scanning | Inspect Status error, reconnect/reload Configuration and confirm the effective settings |
| No BLE rows | Check enable state, scan window, observation filters and nearby legacy LE 1M advertisements; many names appear only in excluded scan responses |
| BLE dropped count rises | Includes queue overflow and the 20-report/second export limit; reduce scan duty or use a less busy location; collector filters operate after USB export |
| Fewer Wi-Fi reports with BLE on | Shared-radio competition is expected; disable BLE or use independent sensors for reliable coverage |
| Same gadget appears at new addresses | Private BLE addresses rotate; do not treat advertiser rows as a physical-device inventory |
| BLE history disappears sooner than time retention | Independent BLE record cap trims oldest batches to about 90% of the configured cap |

BLE time retention defaults to seven days and the cap to 100,000 rows per BLE
table. The configured cleanup worker also expires BLE data while idle when automatic age deletion is enabled.
Deleted SQLite pages are reusable; the file does not immediately shrink. Empty
BLE alert rules disable BLE alerts, and empty observation filters accept all.
Default scan interval/window are 100/20 ms; saved NVS values survive reboot.
See [BLE controls, privacy and limitations](BLE.md).

## Explorer labels, registry and ranging

Collector startup adds a nullable `local_name` column and identity/name indexes
to BLE observations, backfilling names once from retained raw bytes. It creates
`ble_labels` without changing existing frames, sensor NVS or radio settings.
Back up SQLite before upgrading. Aliases/notes survive observation retention;
clear them explicitly (both fields empty), and use `/api/ble/labels` to find stale
annotations. The label cap is 1024 identities.

Search/filter/sort applies before the visible result cap; unknown identifiers
remain explicit. Offline registry refresh is a maintainer action followed by
collector restart, not a live RF lookup. Stale plots indicate the latest stored
report is over 60 seconds old; filtered/deduplicated reports may not represent
all advertising activity. Missing/odd range estimates are not proof of a sensor
failure. Confirm calibration assumptions and read [ranging limits](BLE_RANGING.md).

## BLE hourly display versus retention

The BLE cards and advertiser list show a rolling last hour, not a counter that
resets at the top of the hour or when the collector restarts. An advertiser can
leave this view after an hour without a new retained report while its raw
history remains in SQLite. The latest retained reports are still available for
inspection. Configured BLE retention and record caps continue independently.
Wi-Fi/shared daily summaries and legacy daily BLE API fields remain unchanged.
Reload the browser after upgrading to load the new hourly labels and API reads.

## Host and database inspection

Open **System** for CPU, memory, uptime, storage, database sizes/counts, retention and vendor-cache information, or request `GET /api/system`. This does not run maintenance. Read the [System operations and API guide](SYSTEM.md) for sampling limits and troubleshooting.

## One-time historical purge

Use **System → Purge** to select historical data categories and retention ages, preview exact UTC cutoffs/counts, then confirm with the configuration key. Back up first; committed deletions are permanent. Closing does not stop the job and deleting rows may not shrink files. See [Purge operations, cancellation and backup](PURGE.md).
