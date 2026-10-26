# System health and database information

Choose **System**, between **Configuration** and **Status**, from any dashboard tab.
The dialog reads once on opening, offers **Refresh system**, and refreshes every
15 seconds while open and updates are running. Pause freezes automatic refreshes;
opening the dialog or choosing its refresh button still requests one snapshot.
Closing cancels outstanding browser requests and restores keyboard focus. Escape
also closes it. **Open sensor status** takes you to the existing sensor dialog.

## Host health

The host section reports hostname, actual hardware model, OS, kernel, architecture,
CPU model and logical cores, CPU utilization, 1/5/15-minute load averages,
CPU/SoC temperature, and host uptime. Hardware model comes from device-tree or DMI;
a hostname such as `pi5` does not identify the board. The deployed board remains a
Raspberry Pi 4 Model B Rev 1.2.

Memory shows total, used and available RAM and total/used/free swap. RAM used is
`MemTotal - MemAvailable`; Linux page cache is not treated as entirely unavailable.
Collector information includes application version, application-start UTC time,
application uptime, resident process memory, threads, process CPU, USB collection
enabled, and current sensor connection state. Connection alone does not prove RF
capture is healthy; inspect **Status** and capture freshness as well.

CPU readings are deltas since the previous System sample, with no blocking sleep.
The first sample and samples less than half a second apart show **Unavailable**.
Host CPU ranges from 0 to 100% over all cores; process CPU uses 100% for one logical
core and can exceed 100%. The application start is the creation of this collector
web application, not a separately measured operating-system process start time.
Unsupported or permission-restricted readings show **Unavailable**, rather than a
misleading zero. Probes use unprivileged `/proc`, device-tree, DMI and thermal
files; no extra package, root access or sensor command is required.

## Database and storage

The filesystem section describes the volume containing the configured capture
database: total, used, free and used percentage. Capture database and MAC vendor
cache have separate sections, each showing:

- Resolved path, SQLite version, journal mode and SQL snapshot UTC time.
- Main, WAL and SHM file sizes, presence, and combined footprint.
- Page size/count, free pages, allocated bytes and reusable page space.
- SQLite schema change counter and application schema version when tracked.
- Per-table row count, oldest/newest timestamp, and expandable column definitions.

The capture section covers `frames`, `alerts`, `ble_observations`, `ble_alerts`,
`sensors`, and `ble_labels`. Vendor cache covers `vendors`. Empty tables have zero
rows and unavailable time bounds; absent tables are marked absent. Capture times
are collector/host-received UTC; `sensors.last_seen` is the latest heartbeat,
`ble_labels.updated_at` is an operator update, and `vendors.checked_at` is a lookup
check. These are different semantics, not sensor wall-clock measurements.

`PRAGMA schema_version` is SQLite's schema change counter, not a product migration
version. The collector currently does not track an application schema version
(`user_version = 0`). Reusable SQLite pages remain inside the database file and
are different from free disk space. WAL can temporarily increase total footprint.
File sizes and SQL metadata are separate snapshots and may differ during writes.

Retention shows effective Wi-Fi and BLE days, the BLE record cap per table, the
one-hour BLE dashboard window, and the 60-second cleanup interval. The display
window does not delete retained history. Record caps and cleanup cadence mean
retention is a policy rather than a promise that exactly that many days remain.

## API, cost and access

`GET /api/system` returns `collected_at`, `host`, `collector`, `databases`,
`database_cache`, `policy`, and explanatory `notes`. Units are named in JSON keys:
bytes, seconds, Celsius and percentages. Missing readings are JSON `null`.
Database `error` values describe partial/unavailable SQL metrics. A concurrent
collection returns HTTP 503; retry later. Responses use `Cache-Control: no-store`.

Host readings are collected on demand. SQL snapshots are shared across requests
for 15 seconds; manual refresh also respects this cache. Cache age and SQL sample
time are returned. Main dashboard polling does not call this endpoint. A separate
SQLite `mode=ro`, `query_only` connection runs a short read transaction; capture
queries have a 0.3-second execution budget, vendor queries 0.1 second, with lock
waits limited to at most 0.1 second. A progress handler interrupts expensive SQL;
partial results and an error are returned. File/probe reads and connection setup
are outside SQL execution budgets. Table counts use SQLite counts, time bounds
use available timestamp indexes; row payloads are never returned. A nonblocking
collection lock prevents overlapping probes. Reads never instantiate another
Store or run migration, cleanup, checkpoint, VACUUM or configuration writes.

This endpoint has the same unauthenticated read boundary as other dashboard APIs.
It exposes hostname, hardware/OS, resolved database paths, storage and table
metadata to anyone who can reach the dashboard. It does not return configuration
keys, environment contents, captured row payloads or host credentials. Keep the
dashboard on a trusted LAN or protect it through an authenticated TLS proxy;
configuration write keys do not protect read endpoints.

If a read fails, retry and check host permissions and storage through your normal
administration tools. Metrics refresh has no maintenance side effects. A separate **Purge** button opens
the explicitly confirmed [Data purge](PURGE.md) workflow; it makes no Wi-Fi or
USB configuration changes. First CPU sample being unavailable is expected.

## Purge historical data

Choose **Purge** to open the separate retention-age workflow. [Data purge](PURGE.md) describes preview, authorization, permanent deletion, cancellation and backup requirements. Metrics reads remain read-only.
