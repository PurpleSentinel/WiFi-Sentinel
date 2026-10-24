# Dashboard views

The main dashboard has four tabs. Switching views preserves the selected alert
filter and does not reload the page or change sensor monitoring.

| Tab | Content |
|---|---|
| Overview | 24-hour frame/alert metrics, sensor registration count, retained channels, activity charts and five latest alerts |
| Alerts | Latest 200 retained alerts, severity filter, full alert context and JSON export |
| Reporting | 24-hour subtype counts, retained channel counts and the latest 100 observed frames |
| Devices | Up to 200 most recently observed unicast MAC addresses from the last 24 hours, with observed roles, directly advertised SSIDs, BSSID contexts, channels, last-seen UTC, frame counts and sensors |

Only the active tab's data is requested on the five-second refresh cadence.
Switching tabs cancels obsolete dashboard requests. Pause updates freezes display
updates across tabs; opening another tab while paused does not fetch new detail
data. Refresh resumes updates for the selected tab. Collection continues in the
background regardless of which view is open or paused.

Configuration and Status remain available from every tab. See
[configuration and status dialogs](CONFIGURATION.md) for their behavior.

## Device observations

Devices summarizes source, destination and BSSID addresses from retained frames
in the last 24 hours. Broadcast, multicast and all-zero addresses are excluded.
Each frame is counted once per observed address, even when the same address
appears in multiple header fields. This is observed-frame volume, not unique
packet volume; retransmissions remain included.

“BSSID observed” means an address appeared in the BSSID field. Other addresses
are labelled “Client / other address”; this does not establish a device model,
authenticated identity, or successful client connection. BSSID contexts describe
headers observed with an address, not confirmed associations. An SSID appears
only against the BSSID that advertised it in a beacon/probe response. Unknown or
unadvertised SSIDs remain explicitly unknown. Multiple directly advertised SSIDs
are preserved without splitting names that contain commas.

The API `GET /api/devices?limit=200` accepts limits from 1 through 500 and returns
`window_hours`, `limit`, `has_more`, and `devices`. Each device includes `mac`,
`role`, `ssids`, `bssids`, `channels`, `sensor_ids`, `first_seen`, `last_seen`, and
`frame_count`. The dashboard indicates when the 200-address display limit is hit.

## Accessibility and animation

Tabs support mouse/touch and keyboard navigation: Left/Right cycle between tabs,
Home selects Overview, and End selects Devices. The selected tab and its panel
are labelled for assistive technology. Tables scroll within their panels on
narrow screens.

The decorative logo ring pulses gently using CSS. It remains static when the
browser/OS requests reduced motion. The pulse is branding and continues when
updates are paused; use the collector health display and Status dialog to check
monitoring activity.
