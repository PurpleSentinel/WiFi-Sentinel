# Security & privacy

> **Experimental project:** WiFi Sentinel exists to explore and understand the ESP32-C6 and its Wi-Fi/BLE capabilities. It is not a production-capable security solution and does not conform to expected secure design practices. Do not rely on it as your sole security monitor or expose its dashboard/API to untrusted networks. The known limitations below are part of this experimental scope.

## Intended use

WiFi Sentinel is a **passive security observation** prototype for wireless networks the operator is authorised to monitor. It performs no injection, disconnection, cracking, association or active network interference. It should not be positioned as a professional validated WIDS without independent hardware/field testing.

## Threat model

**Assets:** RF observations, sensor identifiers, local workstation/Pi, MAC/BSSID and BLE advertiser identifiers, SSIDs, BLE names/services/manufacturer
data, raw advertising bytes, timestamps, alerts, analyst decisions.

**Trust boundaries:** untrusted Wi-Fi/BLE air interfaces -> ESP receive driver
and advertisement parser -> USB device/serial event stream -> collector validator
-> SQLite -> web API/browser. Attackers may forge management frames or BLE advertisements, impersonate
addresses/names/services, rotate BLE addresses, flood capture queues, tamper with
hardware, or cause serial corruption.

**Controls implemented:** bounded Wi-Fi and BLE queues, management-only Wi-Fi
selection, up to 31 raw BLE advertising-data bytes, strict event validation,
parameterized event queries, loopback web binding by default, default 7-day
observation/alert retention, independent BLE record caps and bounded caches,
passive-only radio paths, and synthetic test mode.

**Limitations / residual risk:** physical USB ports are untrusted input; telemetry is **not cryptographically authenticated**; valid-looking malicious events could mislead analysts. Dashboard has **no login/role-based access controls or TLS**. Database unencrypted by app (rely on encrypted host storage/permissions). No signed firmware/secure boot configuration supplied. No authenticated OTA updates. The app is intended for a trusted single-user machine, not an internet-facing service.

## Deployment policy

The Configuration dialog adds authenticated write endpoints. A private
configuration key (stored beside the database) and same-origin requests are
required to change settings. Read endpoints remain unauthenticated. Use TLS or
SSH forwarding when the network is not trusted; see
[configuration access](docs/CONFIGURATION.md). The key does not encrypt HTTP.

- Do not expose the HTTP listener to public interfaces. Bind to 127.0.0.1 and use an SSH tunnel for remote browsing, or deploy an authenticated TLS proxy after security review.
- Restrict local OS read/write access to the sensor serial port, `.env`, SQLite DB and backup files.
- Do not set `WIDS_HOST=0.0.0.0` without adding authentication, network isolation and transport security.
- Keep the Pi and ESP-IDF/toolchains updated from trusted sources and review dependency changes.
- Protect the UI/host from a malicious USB device; only attach trusted hardware and monitor operating-system logs.
- Retain minimal identifiable data; Wi-Fi/BLE addresses, names, service/manufacturer data and times may identify
  people, locations or devices. Establish a lawful basis and privacy notice if relevant.
- Review false-positive and false-negative cases. Deauthentication reason codes and MAC addresses are not authenticated proof of an actor.
- No active containment is included; route alerts to human investigation.

## Vulnerability reporting

Open a private security advisory in your own GitHub fork/repository or contact the maintainer privately; do not post exploit details with hardware/network identifiers in public issues.

## Dependencies and supply chain

Vendor lookup uses an attributed local prefix snapshot plus bounded, cached
MACLookup requests containing only a 24-bit vendor prefix. No observed full MAC,
SSID or alert is uploaded. Local/administered addresses are not queried as
hardware-vendor identities. Random BLE addresses never trigger a vendor request
from the BLE dialog, even if their prefix bits resemble a registered MAC.
Bluetooth company IDs are not resolved using the MAC registry. See [lookup privacy and limitations](docs/MAC_LOOKUP.md).

The Python package uses broad compatible semver ranges rather than a lockfile in this prototype. For deployment, lock vetted dependency versions, record SHA256 hashes, enable dependabot/renovate only with code review, and scan SBOMs. Firmware toolchain needs installation from official Espressif channels. Recent PRs reported no configured GitHub CI checks; run collector/browser tests
locally and compile firmware separately.

## BLE-specific privacy and coverage

Passive scanning does not pair, connect, advertise or transmit scan requests.
Legacy advertisements can still contain persistent identifiers, names and
manufacturer/service data; the retained raw bytes are exposed by unauthenticated
read endpoints and included in backups. Apply the BLE retention/record limits,
restrict dashboard access and redact exported observations before sharing.
BLE private addresses rotate and public addresses can be spoofed; neither a rule
match nor a company identifier proves a device's owner or identity. The C6 shared
radio can miss Wi-Fi and BLE traffic. See [BLE monitoring](docs/BLE.md).

## BLE explorer annotations and approximate range

Aliases/notes are persistent local annotations protected by the configuration key
and same-origin checks for writes. They remain after observation expiry, so erase
unneeded annotations explicitly. They are exposed to unauthenticated readers and
included in database backups. Untrusted names/notes/registry strings are rendered
as text. Labels are not transferred between sensors or address types; address
reuse/spoofing can still mislead an operator annotation.

Readable company/service assignments use an offline SIG snapshot; no observations
are uploaded. An assignment is not proof of hardware manufacture or ownership.
RSSI-derived distance is an illustrative model without verified calibration or
physical accuracy; do not interpret it as precise location or identity evidence.
See [BLE explorer](docs/BLE_EXPLORER.md) and [ranging](docs/BLE_RANGING.md).

The unauthenticated `GET /api/system` read endpoint also exposes host identity, OS/kernel, resolved database paths, resource use and table metadata. It excludes credentials and captured row contents. Restrict dashboard reachability or use an authenticated TLS proxy. See [System](docs/SYSTEM.md).

Historical data purge writes (`POST /api/purge/start` and `/api/purge/cancel`) require the existing configuration key and same-origin Origin check. Preview is read-only and unauthenticated; job summaries/counts also share the read boundary. Scope/cutoffs are server-held and confirmation is required. See [Purge access and lifecycle](docs/PURGE.md).

Automatic retention previews/status are unauthenticated metadata reads. Applying a policy requires the configuration key and same-origin request; shorter ages, enabling age deletion or lowering the BLE cap also require a matching recent preview and typed confirmation. See [Retention security and API](docs/RETENTION.md#api-and-access).
