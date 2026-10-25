# Contributing

Contributions should preserve receive-only operation and privacy-by-default storage. Add tests for every new detection rule, mark unvalidated firmware behaviour clearly, and avoid claiming that spoofed MACs prove device identity. PR check: `cd collector && python -m pytest -q tests`.

Before adding radio or firmware features, reference official ESP-IDF APIs for the selected chip and specify which chip/PCB revisions were tested. The deployed sensor is C6; C5/5 GHz remains a separate unvalidated path. Submit hardware bring-up reports without private device identifiers or credentials.


## BLE changes and documentation

BLE code must remain passive: no active scan requests, advertising, pairing or
connections. Preserve bounded queues/caches/storage, raw advertisement bytes and
explicit address types. Never merge BLE random addresses into Wi-Fi identities
or infer a vendor from their prefix. Company identifiers and MAC registrations
are separate namespaces.

Run collector tests and the optional Playwright suite:

```bash
python -m unittest discover -s collector/tests -p 'browser_*.py' -v
```

The browser suite needs Playwright/Chromium; host C integration checks need a C
compiler. Record firmware build/flash and RF evidence separately from fixtures.
For BLE changes, cover malformed AD fields, address rotation, deduplication,
cooldowns, retention, record caps and the dedicated BLE tab after Devices.
Update [BLE documentation](docs/BLE.md), configuration/protocol docs and the
validation log when behavior changes. Refresh checksums for changed files while
preserving archive entries whose files are absent.

## BLE explorer and ranging checks

Maintain strict sensor/address/type separation for labels, samples and model
settings. Label edits use the existing configuration authorization; raw/unknown
identifiers and provenance must remain visible. Use the reviewed SIG refresh
script and keep upstream attribution. Browser checks cover exact log-distance
fixtures, medians, out-of-range/stale/missing data, aliases, filters, safe text,
pause and mobile behavior. Mathematical correctness is not RF distance validation.
Update [explorer](docs/BLE_EXPLORER.md), [ranging](docs/BLE_RANGING.md) and wiki
pages when UI or model semantics change.
