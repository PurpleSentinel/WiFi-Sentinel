# Dashboard views

The main dashboard has five tabs. Switching views preserves the selected alert
filter and does not reload the page or change sensor monitoring.

| Tab | Content |
|---|---|
| Overview | 24-hour frame/alert metrics, sensor registration count, retained channels, activity charts and five latest alerts |
| Alerts | Latest 200 retained alerts, severity filter, full alert context and JSON export |
| Reporting | 24-hour subtype counts, retained channel counts and the latest 100 observed frames |
| Devices | Up to 200 most recently observed unicast MAC addresses from the last 24 hours, with AP/client/unknown classifications, evidence, directly advertised SSIDs, BSSID contexts, channels, last-seen UTC, frame counts and sensors |
| BLE | Rolling one-hour summaries, searchable/filterable advertiser explorer, evidence-based labels, protected aliases/notes and approximate RSSI curve; raw reports in expandable sections |

Only the active tab's data is requested on the five-second refresh cadence.
Switching tabs cancels obsolete dashboard requests. Pause updates freezes display
updates across tabs; opening another tab while paused does not fetch new detail
data. Refresh resumes updates for the selected tab. Collection continues in the
background regardless of which view is open or paused.

Configuration and Status remain available from every tab. See
[configuration and status dialogs](CONFIGURATION.md) for their behavior.

## Wi-Fi device observations

Wi-Fi MAC addresses open the shared [vendor/local-details popup](MAC_LOOKUP.md).
BLE advertiser links use a separate BLE detail dialog, described below.
Recorded alert-source identities are red with a warning indicator across every
view. Historical alerts without source identities are marked unknown.

Devices summarizes source, destination and BSSID addresses from retained frames
in the last 24 hours. Broadcast, multicast and all-zero addresses are excluded.
Each frame is counted once per observed address, even when the same address
appears in multiple header fields. This is observed-frame volume, not unique
packet volume; retransmissions remain included.

### Device roles and evidence

The Devices filter separates **Access Points**, **Clients / Hosts**, **Mixed
(AP + Client)** and **Unknown**. Labels are accompanied by evidence counts rather
than inferred from a source, destination or BSSID header alone.

- **Access Point**: a beacon or probe response was observed with its source equal
  to the BSSID. A hidden/missing SSID does not negate this evidence.
- **Client / Host**: an association/reassociation request originated from this
  address, addressed to a different valid unicast BSSID; or an association/
  reassociation response from that BSSID was addressed to this address. Rejected
  responses still indicate a client role, not a successful connection.
- **Mixed (AP + Client)**: both advertisement and client-role evidence exist for
  the same address. Neither role silently takes precedence.
- **Unknown**: insufficient consistent evidence. Authentication, disconnection
  frames, BSSID-field presence, and advertisements with a source/BSSID mismatch
  do not by themselves establish a role.

Classification and evidence counts are recalculated from observations in the
last **24 hours** on each refresh. As evidence expires, a role can change or
become Unknown. No longer observing any frame for an address in that window
removes it from Devices. The MAC details popup uses the same classifier and
window; its separate header roles and local observations cover retained frames,
which can be older. This distinction is labelled in the popup.

These are observed roles, not authenticated identities or proof of connection.
Consistently forged management frames can produce apparently valid role
evidence. BSSID contexts remain observations, not confirmed associations. SSIDs
appear only against the matching BSSID/source that advertised them; unknown or
hidden SSIDs remain explicit. Names containing commas are preserved intact.

Role badges use text and colour; badge styling never overrides red alert-source
MAC links. Changing the role filter while running loads that role from all
24-hour observations. While paused it filters only the already loaded data and
says so; Refresh loads the selected role and resumes updates. Filters persist
across periodic refresh and tab switching.

### Devices API

`GET /api/devices?limit=200&role=all` accepts limits 1–500 and role values `all`,
`access_point`, `client`, `mixed`, `unknown`. Filtering happens **before** limiting
results, so a role is not hidden just because other devices fill the first page.
The response includes `window_hours`, `limit`, `role`, `has_more`, and `devices`.

Each device includes `mac`, `role_code`, `role`, `evidence`, `evidence_counts`,
`window_hours`, `observed_roles`, `ssids`, `bssids`, `channels`, `sensor_ids`,
`first_seen`, `last_seen`, and `frame_count`. `observed_roles` preserves the raw
source/destination/BSSID roles separately. Evidence counts distinguish beacons,
probe responses, association/reassociation requests sent, and association/
reassociation responses received. The dashboard reports when its 200-address
limit is reached for the selected filter.

## Accessibility and animation

Tabs support mouse/touch and keyboard navigation: Left/Right cycle between tabs,
Home selects Overview, and End selects BLE. The selected tab and its panel
are labelled for assistive technology. Tables scroll within their panels on
narrow screens.

The decorative logo ring pulses gently using CSS. It remains static when the
browser/OS requests reduced motion. The pulse is branding and continues when
updates are paused; use the collector health display and Status dialog to check
monitoring activity.

## Bluetooth Low Energy monitoring

The **BLE** tab sits immediately to the right of **Devices**. It contains the
one-hour retained observation count, up to 200 advertiser summaries grouped by
sensor/address/type, and the last 100 advertisements. Devices and Reporting
contain Wi-Fi data only; BLE API reads occur while the BLE tab is active.

Advertiser links open local names, service UUIDs, manufacturer/service data, raw
advertisement hex, RSSI and timestamps. Red links indicate retained alert-source
associations. Random BLE addresses never trigger a MAC vendor request, regardless
of their prefix bits. Public BLE addresses can show MAC registration; advertised
company IDs are separate identifiers and do not authenticate a device.

Counts reflect filtering, duplicate suppression, record/time retention and radio
loss. Private addresses can rotate, so advertiser counts are not unique physical
device counts. Empty tables can mean scanning is disabled, not that the area is
empty. Check Configuration and Status. See [BLE setup and limits](BLE.md).

### Advertiser explorer and curve

Post-v1.2 #28/#29 improvements add readable labels, offline company/service names,
public/random subtype indicators, search, address/alert filters and sorting.
Select a label or identity selector for evidence, operator labels and the
approximate distance-decay plot. Raw observations remain available in secondary
expandable areas. The plot is controlled by reference RSSI, exponent, positive
range bounds and median window; text mirrors the chart and marks uncalibrated,
stale, missing and out-of-range cases. See [explorer](BLE_EXPLORER.md) and
[ranging](BLE_RANGING.md) for identity, privacy and calibration limits.

## Full-width responsive layout

The dashboard uses the full available page width rather than a 1460px centred
container. Header, navigation and content share responsive side gutters of
18–36px. Tables, summary cards, charts and the BLE advertiser workspace expand
with the viewport; Wi-Fi role evidence and BLE label/evidence columns can use
more space on wide screens.

Long explanatory paragraphs retain local readable widths without limiting the
whole page. Existing responsive breakpoints stack panels on smaller screens;
table scrolling remains inside panels, and dialogs remain capped to usable
viewport-fitting widths. This changes presentation only: monitoring, filters,
configuration, refresh and pause behavior are unchanged.

The Alerts tab's **Recent security alerts** table expands vertically to show all
loaded matching rows (up to 200). Use normal page scrolling rather than a nested
vertical scrollbar; horizontal scrolling remains available on narrow screens.

## Compact BSSID contexts in Devices

The Devices table uses bounded, proportional columns instead of letting long
address lists determine its width. MAC links stay readable, other long values
wrap, and last-seen date/time appear on separate lines. Desktop table width
follows the panel; narrow screens retain a bounded, horizontally scrollable
1100px table instead of an ever-expanding row.

**BSSID contexts** previews the first two addresses vertically. Longer lists have
a **View all N** button opening a searchable dialog containing every observed
context. Addresses remain clickable and retained alert sources remain red. The
list is a snapshot of the selected row's 24-hour contexts, not verified connection
history. Closing the dialog restores focus to its action, or Devices if a live
refresh replaced that row. Search does not change monitoring or detector policy.

The Devices table also expands vertically for all loaded rows (up to 200), using
normal page scrolling rather than a height-constrained inner box. Narrow screens
retain horizontal table scrolling within the panel.

## Devices column sorting

Each Devices column heading has small up/down arrows. Select a heading to sort
ascending; select it again for descending. The active arrow is highlighted and
assistive technology receives the column's `aria-sort` state. Heading buttons
support keyboard activation. Sorting persists across refreshes, role filters and
tab changes, and works on frozen rows while updates are paused.

Frames sort numerically, last-seen values chronologically, BSSID contexts by
count, channels by numeric sequence, and other columns by their displayed text
or lists. Ties use MAC address for deterministic ordering. Sorting applies to the
currently loaded rows (up to the most recent 200 for the role filter), not every
retained database identity; the status line makes this scope explicit.

The BLE summary's **Unique devices** card matches Capture Freshness and counts
distinct advertiser MAC addresses across sensors and address types over the last hour. It uses all
retained observations, not the table cap or filters, and does not claim an exact
physical-device count. See [metric definition](BLE_EXPLORER.md#unique-devices-metric).

## Rolling-hour BLE view

BLE counts, advertiser summaries and selected-advertiser observation counts use
a rolling **last hour**. MAC counts are still addresses, not verified physical
devices; a shorter window reduces accumulated rotated addresses but does not
resolve them. No history is deleted or manually reset. Raw retained observations,
operator labels and configured retention remain intact; Wi-Fi reporting stays
on its existing 24-hour window. Reload the browser page after upgrading to see
the 1h labels.

## System dialog

The **System** button between Configuration and Status opens host health and read-only database metrics from every tab. See the [System guide](SYSTEM.md) for refresh/pause behavior, units and limitations.
