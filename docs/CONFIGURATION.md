# Dashboard configuration and status

Use **Configuration** next to **Pause updates** to inspect collector settings and
the connected sensor's effective configuration. Use **Status** to see sensor IDs,
last-seen UTC timestamps, channels, uptime and dropped reports. Status refreshes
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

Saving starts fresh detector windows. Shortening retention immediately removes
expired records. SSID matching currently remains case-insensitive, and firmware
still sanitizes non-ASCII SSIDs (tracked in issue #5).

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
check the actual state before retrying. Old firmware remains usable for telemetry
but its runtime controls are unavailable until upgraded.

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
