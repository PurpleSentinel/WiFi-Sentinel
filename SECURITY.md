# Security & privacy

## Intended use

WiFi Sentinel is a **passive security observation** prototype for wireless networks the operator is authorised to monitor. It performs no injection, disconnection, cracking, association or active network interference. It should not be positioned as a professional validated WIDS without independent hardware/field testing.

## Threat model

**Assets:** RF observations, sensor identifiers, local workstation/Pi, MAC/BSSID identifiers, SSIDs, timestamps, alerts, analyst decisions.

**Trust boundaries:** untrusted 802.11 air interface -> ESP RX driver/parser -> USB device/serial event stream -> collector validator -> SQLite -> web API/browser. Attackers may forge management frames, impersonate BSSIDs/SSIDs, flood capture queues, tamper with hardware, or cause serial corruption.

**Controls implemented:** bounded on-device queue, mgmt-only frame selection, no captured raw data packets, explicit validation of incoming events, no SQL string interpolation for event content, local-only web binding, default 7-day frame/alert retention, passive-only code path, synthetic test mode.

**Limitations / residual risk:** physical USB ports are untrusted input; telemetry is **not cryptographically authenticated**; valid-looking malicious events could mislead analysts. Dashboard has **no login/role-based access controls or TLS**. Database unencrypted by app (rely on encrypted host storage/permissions). No signed firmware/secure boot configuration supplied. No authenticated OTA updates. The app is intended for a trusted single-user machine, not an internet-facing service.

## Deployment policy

- Do not expose the HTTP listener to public interfaces. Bind to 127.0.0.1 and use an SSH tunnel for remote browsing, or deploy an authenticated TLS proxy after security review.
- Restrict local OS read/write access to the sensor serial port, `.env`, SQLite DB and backup files.
- Do not set `WIDS_HOST=0.0.0.0` without adding authentication, network isolation and transport security.
- Keep the Pi and ESP-IDF/toolchains updated from trusted sources and review dependency changes.
- Protect the UI/host from a malicious USB device; only attach trusted hardware and monitor operating-system logs.
- Retain minimal identifiable data; MAC addresses, SSIDs and times may identify people/locations/devices. Establish a lawful basis and privacy notice if relevant.
- Review false-positive and false-negative cases. Deauthentication reason codes and MAC addresses are not authenticated proof of an actor.
- No active containment is included; route alerts to human investigation.

## Vulnerability reporting

Open a private security advisory in your own GitHub fork/repository or contact the maintainer privately; do not post exploit details with hardware/network identifiers in public issues.

## Dependencies and supply chain

The Python package uses broad compatible semver ranges rather than a lockfile in this prototype. For deployment, lock vetted dependency versions, record SHA256 hashes, enable dependabot/renovate only with code review, and scan SBOMs. Firmware toolchain needs installation from official Espressif channels. GitHub Actions checks Python behavior only, not firmware binary compilation.
