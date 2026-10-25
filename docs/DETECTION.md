# Detection methodology

Wi-Fi rules count **observed 802.11 management frames**; optional BLE rules match
passively received advertisement fields. It does not verify that frames are genuine, that authentication to a network succeeded, or that a flood disrupted anyone's connection. Physical layer jamming and WPA passphrase attacks cannot be reliably inferred from this firmware's metadata alone.

## Detection coverage

| Rule | Frames observed | Grouping | Default | Interpretation |
|---|---|---|---|---|
| `deauth_flood` | subtype 12 | sensor / BSSID / channel | >=20 in 10s | Unexpected disconnect-message burst |
| `disassoc_flood` | subtype 10 | sensor / BSSID / channel | >=20 in 10s | Unexpected disassociation burst |
| `auth_flood` | subtype 11 | sensor / BSSID / channel | >=40 in 10s | Elevated 802.11 authentication traffic |
| `failed_auth_burst` | auth/assoc-response with nonzero status | sensor / BSSID / channel | >=12 in 10s | Repeated unsuccessful 802.11 management exchanges |
| `protected_ssid_untrusted_bssid` | sampled beacon/probe-response with protected SSID and unknown BSSID | sensor / BSSID / channel / rule | First matching sighting, then next match after 60s cooldown | Needs allowlist review; possible spoofed SSID |

All counts include retransmissions and potentially spoofed MACs. A `deauth_flood` can be triggered by unusual but legitimate roaming/disconnect behaviour. A `failed_auth_burst` concerns 802.11 management responses, **not WPA/SAE wrong-passphrase results**; correlate with your access point logs for that use case.

Protected-SSID checks run on every sampled matching advertisement, without a
permanent first-sighting cache. Repeated matches within the configured cooldown
are suppressed; a match at or after expiry can alert again without restarting
the collector. A returning AP can therefore generate another alert even after
the previous database alert has expired. No alert is generated just because
time passes: another matching frame must be observed.

Wi-Fi cooldowns are per sensor/BSSID/channel/rule. Beacons, probe responses and different
protected names advertised by the same BSSID on the same channel share that rule
cooldown. A different channel or sensor has an independent cooldown; returning
to the original channel within its cooldown remains suppressed. Trusted BSSIDs
and unprotected names do not trigger this rule. The monitored-BSSID filter for
volume rules does not disable protected-SSID checks elsewhere.

## Protected Management Frames (PMF)

Management frame header's Protected bit is recorded. For protected frames reason/status bodies may not be readable to a passive observer. The firmware intentionally emits `reason_code=-1` for protected deauth/disassoc; the collector records this as null. PMF helps defend against certain spoofed deauth/disassoc frames on appropriately configured networks, but the sensor does not cryptographically authenticate transmitters or verify PMF integrity.

## Detection settings

Example for a network with legitimate BSSIDs:

```bash
export WIDS_MONITORED_BSSIDS='02:11:22:33:44:55,02:11:22:33:44:66'
export WIDS_PROTECTED_SSIDS='OfficeSecure,GuestSecure'
export WIDS_TRUSTED_BSSIDS='02:11:22:33:44:55,02:11:22:33:44:66'
export WIDS_WINDOW_SECONDS=10
export WIDS_DEAUTH_THRESHOLD=20
export WIDS_DISASSOC_THRESHOLD=20
export WIDS_AUTH_THRESHOLD=40
export WIDS_FAILED_AUTH_THRESHOLD=12
export WIDS_COOLDOWN_SECONDS=60
```

- `MONITORED_BSSIDS`: restrict volume/flood rules to listed BSSIDs; empty monitors all observed BSSIDs.
- `PROTECTED_SSIDS`: SSIDs for lookalike checks; empty means disabled.
- `TRUSTED_BSSIDS`: actual approved AP BSSIDs. A physical AP can advertise multiple BSSIDs and may rotate addresses; record all expected ones.
- Thresholds are **per sensor**, not de-duplicated across sensors.

## Tuning procedure

1. Observe a trusted network for 24–72 hours in normal operation.
2. Correlate with AP management logs/maintenance windows and confirm normal roaming rates.
3. Evaluate collection loss with sensor `dropped` counters and the number of expected beacons.
4. Adjust thresholds conservatively to avoid floods from legitimate infrastructure.
5. Test with **synthetic** events (`wifi-sentinel demo` or `replay`) before an authorised RF test.
6. Record timestamps, expected counts, sensor placements and known blind spots.
7. During incident review, preserve the SQLite file (plus WAL/shm where present) and document time-source uncertainty.

## Main blind spots

- A single radio cannot hear other channels while fixed to its current channel.
- Wi-Fi 6, PMF and chip driver behaviour should be tested on the actual hardware.
- Management headers can be forged; source MAC != authenticated identity.
- Sniffer access to auth frames does not reveal WPA/SAE authentication results.
- Beacon/probe sampling is per BSSID/channel/subtype, with an immediate first report for new state and subsequent one-in-N reports. Lowering N increases data volume; sampling remains non-exhaustive and cannot prevent capture/queue losses.
- Rates use collector processing time rather than high-resolution over-the-air timestamp.
- A determined malicious radio can overload the observer's receive queue.
- RF jamming requires PHY-level measurements not implemented here.

## BLE advertisement match rules

`ble_match` is a medium-severity observation alert, disabled until BLE alert rules
are configured. It matches exact advertised names (case insensitive), addresses,
service UUIDs or four-digit hexadecimal Bluetooth company IDs. Multiple rules
are ORed for filtering; a report can trigger several configured alert rules.
Observation filters run first, so excluded advertisements cannot alert.

The collector's cooldown applies per sensor and BLE rule across addresses;
address rotation cannot bypass it within retained cache state. Duplicate
suppression uses sensor/address/type/event type/raw payload. Both caches are
bounded to 1024 entries; eviction, policy changes or restart can permit earlier
re-reporting. No alert is generated by elapsed time alone.

BLE observations are not fed into Wi-Fi flood windows or AP/client roles. Alert
records include `protocol:ble`, the advertiser and address type, with null BSSID
and channel. The common Alerts view/export includes them; raw observations live
in **BLE** after Devices. A match is not proof of an attack, manufacturer or
physical-device identity. Tune observation filters, cooldown and retention using
[BLE settings](BLE.md), accounting for address rotation and shared-radio losses.

## Explorer evidence is distinct from alert evidence

Readable company/service labels, operator aliases and an RSSI model do not add
new detection rules. The BLE-alert filter refers to retained BLE matches for the
same sensor/address/type. Existing red source-address highlighting still applies
across views. An approximate distance, familiar name or known company identifier
must not be treated as proof of an actor or event. See [explorer](BLE_EXPLORER.md).
