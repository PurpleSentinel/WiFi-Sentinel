# Purge history

From any dashboard tab choose **System → Purge**. A separate dialog lets you
perform a one-time age-based purge. **Deletion is permanent: back up the capture
database before proceeding.** Preview and opening/closing the dialog do not
change captured records.

## 1. Choose data and age

Select any combination of Wi-Fi frames, Wi-Fi alerts, BLE observations and BLE
alerts. **Select all history** selects these four categories. Sensor records,
saved BLE aliases/notes, configuration and the separate vendor cache are always
preserved by this workflow.

Choose a preset (1 hour, 24 hours, 7 days or 30 days), or choose **Custom age**
to show the numeric age and hours/days controls. **Set a different age for each category** lets you set different ages
for selected categories, using the selected unit. **Use current retention
settings** fills Wi-Fi and BLE ages from the effective collector configuration.
Ages must be positive and at most 36,500 days; the browser accepts ages from
0.001 units. Fractional ages are supported. Cutoffs have one-second resolution.

These are one-time choices. Scheduled retention settings remain unchanged.
**Open Configuration** takes you to **Retention**, where ongoing automatic age deletion, schedule and BLE caps are managed. See [Automatic retention](RETENTION.md).

## 2. Review the impact and 3. Confirm deletion

Choose **Preview purge** to count matching and remaining rows in a consistent
read transaction. The preview shows a total deletion count and separate **Delete**, **Keep** and
**Total** figures for each category, plus exact UTC cutoffs and local-time
equivalents. A shared cutoff appears once; different cutoffs appear with their
categories. The confirmation section appears only after a preview finds matches. Only records with a host-received timestamp **strictly earlier than**
the cutoff qualify; records exactly at the cutoff remain. No matches means no
operation can start.

Review the scope, enter the existing configuration key, type **PURGE**, and choose
**Permanently delete previewed data**. The server uses the approved preview scope
and fixed cutoffs, rather than recalculating ages when the job starts. Editing
options clears the browser preview and key. Preview tokens expire after ten
minutes or when evicted from a maximum of 32 previews. Start a new preview if one
expires or the collector restarts.

Ingestion and scheduled cleanup continue, so preview and actual deletion counts
can differ. An older row removed by scheduled retention is not counted again by
this job. New records have collector receive timestamps newer than the fixed
cutoff and remain. Historical deletions can change dashboard totals, identity
lists, investigations and stored alerts; existing live detector windows are not
reset and may produce new alerts from their in-memory history.

## Progress, stop and recovery

The latest operation appears in its own section. Desktop uses a two-column
selection/review layout; narrow screens stack the steps and move focus to review
after preview. Advanced retention and storage details are expandable.

Progress shows state, start/finish UTC, actual committed deletion counts per
category, the preview count, cutoffs and errors. Reads refresh every two seconds
while the dialog is open and dashboard updates are running. Opening and **Refresh
progress** request a read even while paused. Pause freezes automatic display
updates, not deletion or collection.

**Stop after current batch** requires the configuration key and stops between
committed batches. The key stays only in the dialog while open, to allow stopping;
it is cleared when the dialog closes or options change. When reopening a running
operation, enter the key again to stop. Already committed deletions cannot be
restored. Closing the window or browser does not stop a running operation.
Escape or **Back to System** returns focus to Purge in System.

Only one purge runs per collector. Repeating start with the same valid preview
returns the same job rather than executing again. If a request response is lost,
refresh progress or retry the same preview. A failed job retains its actual
committed counts; correct the problem, then preview again for a new attempt.
Database busy/time-budget errors can leave partial completion. Do not assume a
failed or cancelled job deleted nothing.

The latest operation is accessible when reopening the dialog. The collector keeps
up to 20 summaries in memory and logs a bounded completion summary with scope,
cutoffs, times, counts and errors, without keys or captured contents. Jobs and
previews do not survive a collector restart. Graceful shutdown requests a stop
between batches; after a crash/restart, inspect the data and make a fresh preview.
Normal service-log retention determines how long logged summaries remain.

Completion invalidates the System metrics cache. Automatic dashboard refreshes
respect Pause; manual refresh remains available. System reads in flight before
completion may finish with an older snapshot; the next refresh reads the
invalidated cache. Counts remain subject to concurrent collection and retention.

## Storage, performance and backup

Deletion commits batches of at most 500 rows, yielding briefly between batches.
Each batch coordinates with the ingestion/retention locks, with bounded lock
acquisition, a 0.1-second SQLite busy timeout and a 0.2-second SQL execution
budget. The preview uses a separate read-only connection with a one-second SQL
budget and 0.1-second busy timeout. Connection setup, commit and filesystem I/O
are outside SQL progress-handler execution budgets. Busy operations report errors
rather than holding the collector lock indefinitely. This is not a realtime
latency guarantee; storage performance affects commits and responsiveness.

Freed SQLite pages become reusable **inside the file**. The main database may not
shrink and filesystem free space may not immediately rise. The workflow does not
run VACUUM or force checkpoints. Normal SQLite WAL behavior still applies.

Use a consistent SQLite backup through your normal administration process before
purging. See [Operations](OPERATIONS.md). Copying only a live main file while WAL
contains uncheckpointed data is not a reliable backup. No automatic backup or
restore is provided by this workflow. Firmware, Wi-Fi, USB configuration, sensor
records and saved aliases are not modified.

## HTTP API and access

- `GET /api/purge`: latest job (or null) and effective `defaults_hours` per category.
- `POST /api/purge/preview`: JSON `{"ages_hours":{"frames":24,"ble_observations":168}}`.
  Returns token, creation time, expiry duration, ages, UTC cutoffs and per-table
  eligible/remaining/total counts. Only the four fixed historical categories are
  accepted. This read-only operation shares the unauthenticated read boundary.
- `POST /api/purge/start`: JSON `{"token":"<preview>","confirmation":"PURGE"}`.
  Requires `X-Configuration-Key` and same-origin `Origin`. Returns the operation.
  Extra fields, arbitrary tables, client cutoffs and modified scope are rejected.
- `POST /api/purge/cancel`: JSON `{"id":"<operation-id>"}`, with the same key
  and same-origin requirements. A terminal operation is returned unchanged.

Job fields include `id`, `state` (`running`, `completed`, `cancelled`, `failed`),
`started_at`, `finished_at`, `cutoffs`, `preview_counts`, `deleted`, `error` and
`cancel_requested`. Validation failures return 400, authorization failures 403,
a different active purge 409, and an unavailable/budget-limited preview 503.
All responses use `Cache-Control: no-store`. Reads expose counts, cutoffs and
operation summaries to anyone who can reach the dashboard. Protect the service
with a trusted LAN or authenticated TLS proxy. The write key does not protect
reads. Do not put keys in URLs or logs.
