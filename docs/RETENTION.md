# Automatic retention

Choose **Configuration → Retention** from any dashboard tab. This window sets the
collector's ongoing deletion policy. **System → Purge** is a separate one-time
operation and does not change the policy.

## 1. Set the ongoing policy

Set the maximum stored age separately for Wi-Fi frames/alerts and BLE
observations/alerts. Presets are 1 hour, 24 hours, 7 days and 30 days. **Custom**
accepts whole hours or days, from 1 to 87,600 hours (3,650 days). The collector
uses its host-received UTC timestamp and deletes rows **strictly older** than the
cutoff; a row exactly at the cutoff remains. The browser and API show UTC cutoff
examples and a local-time equivalent.

**Automatic age deletion** controls startup, save-triggered and scheduled age
cleanup. It is on by default. When off, age limits remain configured but do not
delete rows. The **Maximum BLE records per table** cap remains active regardless:
BLE observations and BLE alerts each have a separate cap, and ingest may trim
older rows before the age limit. The cap accepts 100–1,000,000, default 100,000.
The scheduling interval accepts 15–86,400 seconds, default 60. A new interval
reschedules the next check as soon as the policy is saved.

Sensor rows, saved BLE aliases/notes, configuration and vendor cache are excluded.
The rolling one-hour BLE dashboard display window is independent of stored history.

## 2. Preview and 3. Save

**Preview policy** reads stored row counts and shows each selected table's total,
age-eligible rows, BLE count-cap excess and UTC cutoff. Age and cap estimates can
overlap; do not add them to infer unique deletions. Counts can change while data
arrives or another retention operation runs. Preview is read-only, expires after
10 minutes and is cleared in the browser when fields change. At most 32 previews
are retained in collector memory.

A shorter age, enabling automatic age deletion, or lowering the BLE count cap
requires a matching recent preview, the configuration key and the typed word
**RETENTION**. Longer ages, disabling age deletion and changing only the interval
still require a preview and key, but no typed destructive confirmation. The
server validates every field, rejects a stale/mismatched preview or concurrent
manual Purge/automatic cleanup, and persists accepted settings in the existing
`.settings.json` file. It never accepts client-supplied cutoffs for execution.

A saved policy takes effect immediately. The collector starts background cleanup
in batches of at most 500 rows per table, releasing its ingest/database lock
between batches. It records rows deleted so far, last completion/error and next
scheduled run in the status panel. A failed run exposes its error and retries on
the next interval. Ingest and scheduled work continue, so actual deletion counts
may differ from preview. The System metrics cache is invalidated after the save
cleanup completes. The dialog refreshes status every 5 seconds while open and
updates are running. Opening reads once even while Pause is active; Pause stops
automatic status refresh, not background deletion. Closing clears the key and
returns keyboard focus to the Retention button.

At collector startup, automatic age cleanup runs before serving data if enabled;
the BLE count cap is enforced even when it is off. CLI demo/replay construction
also applies startup policy. During service operation the configured schedule
runs independently of serial traffic and dashboard polling. Bounded scheduled
batches continue until the current backlog is handled, yielding between batches.
A running manual Purge prevents an automatic run from starting; the next schedule
retries. When the collector is stopped, neither scheduled nor save-triggered
cleanup runs. A normal shutdown wakes and joins the retention worker before SQLite
closes.

Deletion is permanent. Back up the database before shortening policy. Freed
SQLite pages are reusable inside the file; the database file may not shrink and
free filesystem space may not immediately rise. This feature does not force
VACUUM or checkpoints. It never changes radio, USB or network configuration.

## Compatibility and source precedence

Existing `WIDS_RETENTION_DAYS` and `WIDS_BLE_RETENTION_DAYS` still work (1–3,650
days, default 7). Optional `WIDS_RETENTION_HOURS` and
`WIDS_BLE_RETENTION_HOURS` have precedence when present. The new
`WIDS_AUTOMATIC_AGE_DELETION` accepts true/false, 1/0 or yes/no (default true);
`WIDS_CLEANUP_INTERVAL_SECONDS` accepts 15–86,400 (default 60).
`WIDS_BLE_MAX_RECORDS` continues to set the BLE cap.

The adjacent `.settings.json` file overrides corresponding environment values
on restart. Older saved files without the new fields retain their day-based
limits and 60-second enabled schedule. A new Retention save writes effective
hourly limits and the complete validated policy. The window labels each value
as a saved runtime setting, environment setting or default where known. If both
legacy days and new hours are present, hours win. A direct trusted Engine change
to a legacy day field clears its corresponding hourly override. The generic
collector Configuration API rejects retention fields; use the endpoints below.

## API and access

`GET /api/retention` returns effective `policy`, `sources`, status and scope rules.
`POST /api/retention/preview` accepts all five policy fields:

```json
{"wifi_age_hours":168,"ble_age_hours":168,"automatic_age_deletion":true,"cleanup_interval_seconds":60,"ble_max_records":100000}
```

It returns a token, UTC cutoffs, per-table counts, current/proposed policy and a
`destructive` flag. `POST /api/retention/apply` accepts:

```json
{"policy":{"wifi_age_hours":168,"ble_age_hours":168,"automatic_age_deletion":true,"cleanup_interval_seconds":60,"ble_max_records":100000},"token":"<preview token>","confirmation":"RETENTION"}
```

For nondestructive changes, `token` and `confirmation` may be `null` or empty;
the UI still previews. Applying requires `X-Configuration-Key` and a same-origin
`Origin` header. Invalid values/stale previews return 400; wrong key/origin 403;
concurrent cleanup or Purge 409; unavailable preview 503. Preview/status share
the existing unauthenticated read boundary and expose counts, paths indirectly
through other System APIs, and policy. Responses are `Cache-Control: no-store`.
The key is never returned. Keep the dashboard on a trusted LAN or behind an
authenticated TLS proxy.

Preview uses a separate read-only SQLite connection and a one-second SQL progress
budget with a 0.1-second lock timeout. Collector ingest and policy updates use
Engine/Store locks, and automatic deletion commits bounded batches. The SQL budget
does not bound connection setup or filesystem latency. Last/next run times and
errors are status information, not a realtime timing guarantee.
