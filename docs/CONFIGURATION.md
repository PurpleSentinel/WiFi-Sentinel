# Dashboard configuration and status

Use **Configuration** next to **Pause updates** to inspect collector settings and
the connected sensor's effective configuration. Use **Status** to see sensor IDs,
last-seen UTC timestamps, channels, uptime and dropped reports. BLE-capable
firmware also reports passive scan state, BLE report/drop counts, free heap and
stack/controller error (0 means clear). Status refreshes
every five seconds while open unless updates are paused; opening it always
performs a one-time refresh. Monitoring continues when either dialog is closed.

## Permission to save

Reading the dashboard remains unauthenticated. Configuration writes require a
configuration key and a same-origin browser request. The collector generates a
private key file next to the database on first startup. For the default database,
the Pi administrator can retrieve it with:

```bash
cat collector/sentinel.config-key
```

Enter that key in the Configuration dialog. The dialog clears it when closed;
it is not stored in browser storage or returned through the API. Key and saved
settings files are created with mode 0600. Protect the key like an administrator
password. For remote access across an untrusted network, use an authenticated
TLS proxy or SSH tunnel: plain HTTP does not protect the key in transit.

## Collector settings

The following controls apply immediately and are saved atomically on the Pi:

| Setting | Environment equivalent | Allowed values |
|---|---|---|
| Detection window | `WIDS_WINDOW_SECONDS` | 1–3600 seconds |
| Deauthentication threshold | `WIDS_DEAUTH_THRESHOLD` | 1–1,000,000 frames |
| Disassociation threshold | `WIDS_DISASSOC_THRESHOLD` | 1–1,000,000 frames |
| Authentication threshold | `WIDS_AUTH_THRESHOLD` | 1–1,000,000 frames |
| Failed authentication threshold | `WIDS_FAILED_AUTH_THRESHOLD` | 1–1,000,000 frames |
| Alert cooldown | `WIDS_COOLDOWN_SECONDS` | 1–86,400 seconds |
| Retention | `WIDS_RETENTION_DAYS` | 1–3650 days |
| Monitored BSSIDs | `WIDS_MONITORED_BSSIDS` | One MAC per line; empty monitors all |
| Protected SSIDs | `WIDS_PROTECTED_SSIDS` | One SSID per line; empty disables this rule |
| Trusted BSSIDs | `WIDS_TRUSTED_BSSIDS` | One MAC per line |
| BLE retention | `WIDS_BLE_RETENTION_DAYS` | 1–3650 days; default 7 |
| BLE identical-report suppression | `WIDS_BLE_DUPLICATE_SECONDS` | 0–3600 seconds; default 10; 0 disables |
| BLE maximum records | `WIDS_BLE_MAX_RECORDS` | 100–1,000,000 per BLE table; default 100,000 |
| BLE observation filters | `WIDS_BLE_FILTERS` | Up to 256 exact rules; empty accepts all |
| BLE alert rules | `WIDS_BLE_ALERT_RULES` | Up to 256 exact rules; empty disables alerts |

BLE filters and alert rules use `name:My beacon`, `address:aa:bb:cc:dd:ee:ff`,
`service:180f` or `company:004c`. Enter one rule per line in the dialog, or comma
separated in the environment. Rules are ORed; names match case insensitively.
Company IDs are Bluetooth identifiers, not MAC-prefix registrations. See
[BLE rule semantics and limits](BLE.md).

Saving starts fresh detector windows and BLE duplicate/cooldown caches. Shortening retention immediately removes
expired records. SSID matching currently remains case-insensitive, and firmware
now preserves the original SSID bytes, including non-ASCII names. Protected
names retain their entered case in configuration; ordinary UTF-8 matching remains
case-insensitive as before. SSIDs are limited to 32 bytes, not 32 characters.

For unusual byte sequences, use `hex:` followed by 1–32 exact bytes encoded as
hex pairs: `hex:4100ff` matches bytes `41 00 ff` exactly, including case-sensitive
ASCII bytes. A plain name such as `Café` matches its UTF-8 encoding. Prefixes
`hex:` and `utf8:` are reserved; use `utf8:hex:4100ff` to match a literal SSID
named `hex:4100ff`, or `utf8:utf8:Office` for one named `utf8:Office`.
Raw SSID hex is available in new frame API records and the MAC details popup.
Use hex for control bytes, leading/trailing spaces, invalid UTF-8, or names that
cannot be expressed conveniently in the line/comma-separated configuration.
Hidden zero-length SSIDs are not treated as protected named networks. Older
stored/sanitized SSIDs cannot be reconstructed retroactively.

While the web service is running, a dedicated worker attempts retention cleanup
every 60 seconds even without sensor traffic. See [Operations](OPERATIONS.md)
for timing, failure handling and shutdown behavior.

Saved values live beside the database, using the database stem with suffix
`.settings.json` (default `sentinel.settings.json`). They override environment
values for the editable detection/retention settings on subsequent startups.
To return to environment settings, stop the collector, move aside that saved
file, and restart. The database path determines which saved file is loaded.

Database path (`WIDS_DATABASE`), bind address (`WIDS_HOST`), dashboard port
(`WIDS_PORT`), serial device (`WIDS_SERIAL_PORT`), and baud (`WIDS_BAUD`) appear
read-only in the dialog. Change them in `collector/.env` and restart the collector
service. The default dashboard port is 8181. These changes do not modify the Pi's
Wi-Fi or Ethernet configuration. Continue using the sensor's stable USB by-ID
path so another ESP device is not selected accidentally.

## Sensor settings

Current runtime-capable firmware supports:

| Setting | Firmware default | Allowed values |
|---|---|---|
| Sensor ID | `WIDS_SENSOR_ID` | 1–40 letters, digits, dots, dashes, underscores |
| Band | `WIDS_BAND` | Reported by the connected chip |
| Channel | `WIDS_CHANNEL` | Reported supported channels for the selected band |
| Beacon/probe sample factor | `WIDS_BEACON_SAMPLE_N` | One in N, 1–1000 |
| Heartbeat interval | `WIDS_HEARTBEAT_SECONDS` | 1–300 seconds |
| BLE enabled | Disabled without saved BLE NVS settings | Boolean, on BLE-capable firmware |
| BLE scan interval | 100 ms | 10–10240 ms |
| BLE scan window | 20 ms | 10 ms up to the scan interval |

On upgraded firmware the sample factor applies independently to each BSSID,
channel and advertisement subtype. New entries/types are reported immediately,
then after every N further observations; N=1 reports all advertisements. Beacon
and probe-response traffic cannot consume one another's sampling quota. The
fixed table holds 64 BSSID/channel entries, with FIFO eviction; evicted entries
are treated as new when seen again. This bounds state but can increase export
volume under churn. Non-advertisement management subtypes remain unsampled.
An observed change to the factor resets that entry's counters. The dialog shows
the sensor-reported sampling mode; older firmware may report no mode.

The C6 offers only 2.4 GHz. Two-GHz channels follow the driver's current country
profile. The C5 additionally offers a conservative non-DFS 5 GHz subset
(36, 40, 44, 48); the driver can reject tuning under regulatory restrictions.
The dialog shows the reported regulatory profile. Country selection remains a
firmware/deployment responsibility, not a setting inferred from the browser.
Sensor chip and console transport are displayed read-only; changing console
transport requires rebuilding/flashing firmware.

**Apply sensor settings** sends a bounded JSON command over the existing USB
connection. Firmware validates the whole settings group, tunes the radio and
saves the settings in NVS before acknowledging success. On failure it restores
the previous settings. Only an acknowledged response updates the displayed
effective configuration. A timeout reports uncertainty; reload Configuration to
check the actual state before retrying. Telemetry-only legacy firmware remains usable for Wi-Fi telemetry but has no
runtime controls. Wi-Fi runtime-capable firmware without BLE retains its Wi-Fi
controls and reports BLE unavailable until upgraded.

Saved sensor settings survive reboots and override compiled defaults. Apply new
values through the dialog to replace them; reflashing the app alone does not
erase NVS. Changing channel does not add simultaneous channel coverage. Commands
configure passive capture only; they do not change the Pi's networking or send
Wi-Fi attack frames.

Collector and sensor saves are separate operations with separate confirmation
messages. USB Serial/JTAG runtime control has been exercised on the connected C6;
the C5/5 GHz and UART console paths still require hardware validation.

## API

- `GET /api/configuration`: effective settings, editable ranges, restart-only
  fields, connection state and acknowledged sensor capabilities. Never returns
  the configuration key.
- `POST /api/configuration/collector`: partial object of editable collector values.
- `POST /api/configuration/sensor`: partial object of editable sensor values.

POST requests require `X-Configuration-Key`, a matching `Origin`, and JSON. The
collector owns the USB port; web requests never open another serial connection.

## Optional browser checks

Install Playwright and its Chromium browser into a development environment, then
run `python -m unittest discover -s collector/tests -p 'browser_*.py' -v`.
These tests mock network responses and never reconfigure an attached sensor.

## Bluetooth Low Energy monitoring

Apply BLE enable/interval/window with **Apply sensor settings**; these values
persist on the C6, while BLE filters/alerts/retention persist on the Pi. Older
firmware keeps Wi-Fi controls but shows BLE unavailable. An enabled scan is
passive legacy LE 1M only. Increasing the scan window competes with Wi-Fi
reception on the shared radio. Check **Status** for the effective scan state,
then **BLE** after Devices for observations. See [BLE monitoring](BLE.md).

## BLE operator labels and model controls

The selected advertiser's alias/notes use the existing configuration key and
same-origin write checks. They are stored in `ble_labels`, separate from
`.settings.json`, and remain until explicitly cleared. Bounds: alias 80 printable
characters, notes 1000 characters, at most 1024 identities. Read endpoints expose
these annotations; protect access and backups. See [explorer](BLE_EXPLORER.md).

RSSI reference/exponent, plot range, median window and calibration assertion are
per-identity browser-session model inputs, not radio or collector policy settings.
They require no key and disappear on reload. They do not affect Wi-Fi/BLE capture
or make range estimates physically accurate. See [ranging controls](BLE_RANGING.md).

## BLE display window

BLE summary and advertiser-list numbers use a rolling one-hour reporting window.
This is separate from `WIDS_BLE_RETENTION_DAYS`: shortening the displayed window
does not delete stored observations or reset sensor counters, aliases or notes.
Wi-Fi views retain their 24-hour reporting window. This update adds no new
configuration setting and does not change the existing retention controls.

The **System** dialog reports effective retention and BLE caps alongside resource/database information; it has no configuration controls. See [System](SYSTEM.md).
