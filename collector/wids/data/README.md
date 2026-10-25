# MAC vendor snapshot

`vendors.json.gz` is a compressed copy of the public MACLookup JSON download:
https://maclookup.app/downloads/json-database/get-db

Source, retrieval timestamp, record count and field names are recorded in
`vendors-meta.json`. Original record fields are preserved. Lookup uses the
longest matching 36-, 28- or 24-bit prefix. Attribution: MACLookup
(https://maclookup.app/downloads/json-database), whose dataset draws on IEEE and
other public sources. Provider terms: https://maclookup.app/terms-and-conditions.
These registry facts are separate from the project's MIT source-code license.

The local snapshot includes prefix, vendor, assignment type, privacy flag and
record update date; it does not supply organization address/country or a
registration date. Optional cached MA-L enrichment adds every field actually
returned by the provider. Neither source establishes device ownership or model.

This dataset is a MAC-prefix registry, not a Bluetooth SIG company-identifier
registry. The BLE detail dialog may use it for public BLE addresses; it never
looks up random BLE addresses, even when their prefix bits look globally
registered. Advertised BLE company IDs remain distinct from MAC attribution.
See [BLE monitoring](../../../docs/BLE.md) and
[lookup behavior](../../../docs/MAC_LOOKUP.md).
