# Release 1.3.1

Release 1.3.1 clarifies WiFi Sentinel's experimental purpose and security scope.
The project exists to explore and understand the ESP32-C6, not to provide a
production-capable security solution. It does not conform to expected secure
design practices. Do not rely on it as your sole security monitor or expose its
dashboard/API to untrusted networks. See [Security & privacy](../SECURITY.md)
for known limitations.

## Changes since v1.3.0

- Added this notice to the repository README and security guidance, and to the
  [product wiki](https://github.com/PurpleSentinel/WiFi-Sentinel/wiki/Home).
- Updated collector package, application and API version metadata to 1.3.1.
  Collection, detection, storage, dashboard behavior and configuration are
  unchanged.

The ESP32-C6 firmware remains v1.2.0. No firmware binary is attached and no
reflash is needed. Existing 1.3.0 collector installations do not need a restart
for a functional change; install 1.3.1 only if you want the updated version
metadata. Publishing this release does not restart an existing installation.

## Validation

All 152 collector tests passed. A local 1.3.1 wheel built successfully; its
version metadata and bundled dashboard asset were checked. No radio or firmware
behavior changed in this patch release.

[Full changes since v1.3.0](https://github.com/PurpleSentinel/WiFi-Sentinel/compare/v1.3.0...v1.3.1)
