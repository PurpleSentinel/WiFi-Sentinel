# BLE advertiser explorer and identification

Implemented for issues #28/#29 and included in Release 1.3.0. These enhancements were not in the original v1.2.0 source archive. The existing C6 firmware is sufficient: this
is a collector/dashboard update and does not change radio or Pi network settings.

## Layout and investigation workflow

Open **BLE**, to the right of Devices. The summary shows retained advertisements
and advertiser identities in the last hour, freshness of stored reports, and
scan state. An identity is **sensor ID + address + address type**, not a physical
device. Private address rotation and different sensors can produce multiple rows.
The **Scan status** button opens the existing Status dialog.

Search names, operator aliases/notes, addresses, sensors, company names/IDs and
service names/UUIDs. Filter public/random address types and identities associated
with a retained BLE alert; sort by recent observation, strongest RSSI, or
name/alias (with address fallback). Filters apply before the 200-row UI limit.
The API supports up to 500 results. The total-identity count is the unfiltered
one-hour population, not the number matching the current search. Matching results
can be capped; the view reports when more exist.

Select a row's label or the sensor/address/type selector to open its workspace:

- Advertisement evidence and label provenance.
- Protected operator alias/notes controls.
- The [approximate RSSI distance curve](BLE_RANGING.md).
- Expandable raw observations, including malformed AD flags and original bytes.

Clicking an address opens the BLE detail dialog for that sensor/address/type.
The secondary **Recent advertisements** section is collapsed initially and
contains up to 100 latest reports across advertisers. Detailed/ranging samples
are limited to the latest 100 retained reports for the selected identity only.

Only the active tab refreshes every five seconds. Pause freezes observations;
model controls can still recompute from frozen samples without fetching new
ones. Selecting a different identity while paused clears the previous identity's
samples and asks for Refresh/Resume. Search/filter changes while paused wait
for Refresh. Failed refreshes explicitly warn that previous evidence may be stale.

## How labels are chosen

| Priority | Source | What it means |
|---|---|---|
| 1 | Operator alias | A human label for this exact observation identity |
| 2 | Advertised local name | Most recently retained nonempty name; not authenticated |
| 3 | Known advertised standard service | Service name followed by “advertisement” |
| 4 | Known company identifier | Assigned organization followed by “advertisement” |
| 5 | Address fallback | “Unnamed advertiser” and the address suffix |

List name evidence is from the last hour. Detailed inspection may use the
last nonempty name from retained history. Company/service badges describe the
latest advertisement; a missing field in that packet is not proof that the device
never advertised it. The raw observations preserve earlier evidence.

A known standard service produces a category such as “Battery advertised”, not
an invented model. Otherwise the category remains unknown. Confidence is always
an explicit **unverified advertisement** statement, not a probability or proof
of manufacturer, owner or identity. Multiple devices can share identical names.

Bluetooth company identifiers refer to the namespace of manufacturer data. They
can describe an ecosystem/format rather than the hardware maker. MAC-prefix
registration is separate. Private/random BLE addresses never initiate MAC vendor
lookup from this UI, even when their prefix bits resemble a public allocation.
Unknown identifiers remain visible numerically; custom UUIDs are not guessed.

## Offline registry and maintenance

Readable names come from `collector/wids/data/ble-assigned-numbers.json`, a
snapshot of official [Bluetooth SIG Assigned Numbers](https://www.bluetooth.com/specifications/assigned-numbers/).
The initial snapshot contains **4,057 company IDs** and **76 standard service
UUIDs**; source URLs, retrieval UTC and raw-source SHA256 digests are embedded.
No observations are sent to the SIG. The collector needs no YAML package or
network lookup to decode these names.

Registry facts, trademarks and names retain upstream attribution/notices and
are not relicensed by the source-code MIT license. See [data provenance](../collector/wids/data/README.md).
To refresh in a maintenance environment:

```bash
python -m pip install PyYAML
python scripts/update-ble-assigned-numbers.py
```

The script downloads only fixed official URLs with 30-second timeouts and 2 MB
limits, validates numeric/name records, and atomically replaces the snapshot.
Review changes, refresh SHA256SUMS and restart the collector to reload its cached
registry. Failed downloads/validation leave the old snapshot. Unavailable local
registry data falls back to explicit unknown identifiers and address/name labels.

## Operator aliases and notes

Use the existing configuration key to save an alias (up to 80 printable
characters) and notes (up to 1,000 characters, allowing newlines/tabs). Writes
require the same-origin check used by Configuration. The key is cleared after a
save attempt or when leaving the BLE view and is never stored in browser storage.
Operator content is rendered as text.

Records live in SQLite `ble_labels`, keyed by sensor/address/type. They survive
restart and observation retention, with a maximum of 1,024 labelled identities.
Clear both fields to delete a record. `GET /api/ble/labels` lists retained labels,
including identities no longer in the one-hour table; protected
`POST /api/ble/label` can clear one by its original tuple. Labels and notes are
included in backups and exposed by the same unauthenticated read boundary as
other observation details.

Aliases never follow a rotating address automatically and never transfer between
sensors or address types. An address can be reused/spoofed, so a persisted alias
is still an operator annotation, not a verified persistent physical identity.
Red address links continue to mean retained alert-source association, not guilt.

## Wide and narrow displays

The advertiser table and selected workspace use the available page width with
18–36px side gutters. Evidence and the RSSI plot stay side by side on desktop,
with the plot receiving the larger share of width. On narrow screens panels
stack and tables scroll internally. Readable explanatory text widths do not
constrain the table/chart area. See [dashboard layout](DASHBOARD.md#full-width-responsive-layout).

## Unique devices metric

The BLE summary adds **Unique devices**, styled like **Capture Freshness**. Its
one-hour value counts distinct **MAC addresses only** across all retained
observations, sensors and address types. Repeated reports of the same MAC count
once, including sightings from different sensors or as both public and random. It is independent of table search, filtering, sorting and the 200-row
visible cap.

This differs from **Advertiser identities**, which counts sensor/address/type
combinations. The two values can legitimately match when every MAC has only one
sensor/type combination in the retained window. Both are observation metrics, not exact physical-device counts:
private addresses rotate, addresses can be reused/spoofed, and capture can miss
reports. No names, aliases, company IDs or RSSI are used to merge addresses.
The card's footer and tooltip make these limits explicit.

The card refreshes with the BLE view, freezes with Pause and preserves its last
value with the normal stale/error notice if refresh fails. An empty one-hour
observation window produces 0. Four cards fit wide screens, two columns are used
on intermediate screens and one column on small mobile displays.
