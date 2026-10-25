# MAC details and alert sources

Click a Wi-Fi MAC address in Overview, Alerts, Reporting, Devices, or a dialog
to open its Wi-Fi/vendor details. BLE advertiser links use their own dialog. The popup shows a 24-hour device classification and supporting evidence, separately from retained header roles, directly advertised SSIDs,
BSSID contexts, channels, monitoring sensors, first/last seen, frame count and up
to 100 associated alerts. Empty observations remain explicitly unknown.
Configuration inputs remain editable; separate address lookup buttons appear
under BSSID lists and read-only connection fields containing a MAC address.
Popup content uses text rendering, including untrusted SSIDs and vendor text.

For new firmware captures the popup also shows advertised SSID byte hex, suitable
for an exact `hex:` protected-name rule. Printable UTF-8 names are displayed
normally; invalid/non-printable bytes are escaped and literal backslashes are
doubled. See [SSID matching syntax](CONFIGURATION.md). Legacy sanitized names
retain their original stored text and have no recoverable raw-byte metadata.

Wi-Fi Reporting includes both source and destination MACs. Wi-Fi links use the
shared rendering helper, including addresses embedded in alert descriptions or
displayed as BSSIDs. Close/Escape restores focus, including when lookup opens
above the Configuration dialog. Mobile layouts scroll tables inside the popup.

## Red source addresses

Every new Wi-Fi alert records the actual distinct source MACs contributing to
its triggering window. BLE match alerts record the advertiser address and its
BLE address type; they have no Wi-Fi BSSID or channel. A protected-SSID alert records the observed beacon/probe
response source. BSSID and source MAC are separate fields and need not match.

Addresses recorded as contributing sources for retained, unexpired alerts are
red wherever they appear, regardless of their displayed role. A warning symbol
and accessible label accompany the colour. This means association with an alert,
not proof that a device is malicious or that the source address is authentic.
Highlighting is refreshed with dashboard data; Pause updates freezes that view.

Existing databases are migrated by adding a nullable `source_macs` JSON column to
alerts. **Older alerts have unknown source identities**: their BSSID is not
silently treated as a source, and the dashboard displays a legacy-data notice.
The popup distinguishes contributing-source association from BSSID-only context.
Sources stop being highlighted when no unexpired retained alert references them.
The general timer-driven database cleanup timing remains documented separately
in [Operations](OPERATIONS.md).

## Vendor registry and privacy

A bundled MACLookup snapshot contains 59,170 assignment prefixes retrieved on
2026-10-24. It preserves all supplied record fields: prefix, organization,
assignment type, private-registration flag and record update date. Longest-prefix
matching prefers 36-bit and 28-bit assignments over a broad 24-bit allocation.
Assignment start/end and address count are computed from that matched prefix.
Snapshot provenance is in `collector/wids/data/vendors-meta.json`.

For 24-bit assignments, the server also requests additional public details from
MACLookup with a three-second socket timeout and a bounded response size. **Only
the six vendor-prefix hex digits are sent**, never the observed device suffix,
SSID or alert. All returned fields are shown, including organization address,
country, range, update date and provider flags where supplied. Raw provider block
size is labelled separately because providers may report range span rather than
inclusive address count. A registration date is not fabricated if unavailable.

The provider resolves only 24-bit prefixes. For a more specific 28-/36-bit
assignment the popup uses the correct local record and explicitly explains why
the broader online lookup is not used. This avoids attributing a subassignment
to its parent organization incorrectly.

Additional details are cached beside the capture database, using suffix
`.vendors.sqlite3`, for 30 days, with at most 4096 entries. Concurrent enrichment
requests are bounded and new requests are limited to one per second. Retry /
refresh requests bypass the normal cache freshness check but retain rate limits.
The popup shows lookup time, registry retrieval time, cache/stale status and
errors. If the service is offline, local vendor and observation details remain
available; a cached enrichment result can still be shown. A corrupt/unwritable
vendor cache does not prevent capture startup.

Locally administered addresses can be private/randomized and are not assigned a
hardware vendor from their prefix. Multicast/broadcast, all-zero, unregistered,
malformed, and unavailable-registry cases are explicit. Prefix registration
identifies an organization, not an exact device model, current owner or verified
sender. Source attribution and provider terms are in [References](REFERENCES.md)
and the data directory's README.

Maintainers can refresh the bundled snapshot with:

```bash
python3 scripts/update-vendors.py
```

This downloads only the fixed public database URL with size/timeout limits and
validation; it never uploads observations. Restart the collector after updating
and refresh the affected SHA256SUMS entries before committing.

## API

- `GET /api/alert-sources`: contributing addresses and count of legacy alerts
  lacking sources.
- `GET /api/mac/{address}`: normalized address, retained local observations,
  associated alerts and current source-highlighting metadata.
- `GET /api/mac/{address}/vendor`: local registration and cached prefix-only
  enrichment. `?refresh=true` retries additional details.

Normalization accepts complete colon, hyphen, dotted or twelve-hex-digit MACs.
Invalid addresses return HTTP 400. No caller-supplied fetch URL is accepted.
Vendor requests are independent of capture and are made on demand, not by the
five-second dashboard poll.

## BLE advertiser details

The **BLE** tab after Devices provides address links in both advertiser summaries
and recent advertisements; BLE source links in Alerts open the same BLE dialog.
It shows raw advertisement bytes, names, services, company IDs/data, RSSI and
sensor timestamps. Red highlighting still means a retained source association.

BLE `address_type` is authoritative for privacy handling. A random address never
initiates MAC registration lookup from this dialog, regardless of its prefix
bits. A public BLE address may use the existing prefix-only lookup. Bluetooth
company IDs identify the namespace of advertised manufacturer data; this MAC
snapshot is not a Bluetooth company registry. No device model, ownership or
persistent physical identity is inferred. See [BLE interpretation](BLE.md).

## Readable BLE identification

The [explorer](BLE_EXPLORER.md) supplements BLE evidence with an independent
offline Bluetooth SIG company/service registry. It does not reuse the MAC-prefix
snapshot for these identifiers. Display-label priority is operator alias,
advertised name, known service, known company and explicit unnamed fallback.
Every label has provenance; model/owner identity remains unverified. Random
address subtypes describe their format, not a hardware vendor. Ranging inputs
are scoped to the same sensor/address/type and never imply identity continuity.
