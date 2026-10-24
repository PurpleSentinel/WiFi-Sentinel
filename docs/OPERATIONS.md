# Operations runbook

The tested deployment is a Raspberry Pi 4 with a USB ESP32-C6. Use its verified by-ID path; another ESP currently occupies `/dev/ttyACM0`. See [Hardware](HARDWARE.md).

## Start/stop

```bash
cd wifi-sentinel/collector
source .venv/bin/activate
wifi-sentinel serve
# Ctrl+C stops collector
```

For systematic boot start, see `docs/RASPBERRY_PI.md` for the user service template.

## Health

```bash
curl -s http://127.0.0.1:8181/api/health
curl -s http://127.0.0.1:8181/api/summary
curl -s 'http://127.0.0.1:8181/api/alerts?limit=10'
```

`/api/health` means only that the web service is reachable; it does not assert an active USB or healthy RF receive path. `/api/sensors` gives last-seen UTC and queue drop count; check it too.

## Common problems

| Symptom | Checks |
|---|---|
| `idf.py: command not found` | Source ESP-IDF `export.sh`, confirm correct virtual env/toolchain |
| Unknown target `esp32c6` | ESP-IDF too old; use v5.5.2+ |
| Flash port not found | Check actual PCB USB data path/cable, `lsusb`, `dmesg`, `/dev/serial/by-id` |
| Permission denied on `/dev/tty*` | User group and active session; stop any other serial terminal |
| No `WIDS` lines | Wrong console selected, firmware not flashed, capture quiet; heartbeat should still appear |
| Only heartbeat but no frames | Wrong channel/band, RF placement/antenna, receive configuration; reduce beacon sampling temporarily |
| Frame channel 0 or unexpected | Verify ESP-IDF promiscuous RX metadata on the actual C6 revision (or separately qualified C5) |
| `dropped` increasing | Reduce beacon telemetry, shorten USB path/avoid overloaded Pi, check host logs |
| All rules quiet while frames arrive | Threshold too high, wrong BSSID filters, no relevant subtype |
| Many rogue-SSID alerts | Complete list of legitimate multi-BSSID APs and extenders/mesh nodes |
| UI unreachable remotely | Expected: default binding is 127.0.0.1; use SSH forward, not public exposure |
| Wrong timestamps | Pi host clock not synced, USB ingestion delay, data uses host UTC receive time |

## Retention

Expired frames and alerts are deleted at collector startup, immediately when a
retention setting is saved, and by a dedicated worker while `serve` is running.
The worker waits **60 seconds between cleanup attempts**, independently of event
counts, serial connectivity, dashboard requests or paused display updates. This
also runs when no serial port is configured. Under normal operation, expiry is
enforced within one scheduling interval plus cleanup/lock execution time.

The startup log reports the interval. SQLite/filesystem failures are logged and
retried on the next interval; investigate errors if cleanup cannot complete.
Cleanup shares the ingestion/configuration lock and SQLite lock, so it uses the
current retention policy and cannot race with a policy update. Shutdown wakes
waiting workers and joins them before closing the database. Sensor registration
and last-seen rows are not automatically deleted. CLI demo/replay operations
retain startup cleanup; the recurring worker belongs to the running web service.

## Backup / incident preservation

- Stop collector before copying the database, or use SQLite's backup API rather than copying a live WAL-mode DB file alone.
- Preserve DB provenance (hostname, UTC time, collection channel, detector config, SHA256 digest) and avoid altering the original.
- Export only minimum data necessary, encrypted at rest if transferred.
- Deleting SQLite database and WAL/SHM files resets the local store (stop application first).
- Frames do **not** contain raw 802.11 packet bytes. This is not a replacement for a full forensic capture tool.

## Updating

Back up SQLite, check `git diff` and release notes, run Python tests and repeat firmware smoke tests for changed IDF versions. Avoid auto-upgrading firmware without a verified rollback process. There is no general migration framework; this release adds the nullable alert source-identity column compatibly on startup. Legacy alert sources remain unknown. See [MAC details](MAC_LOOKUP.md).
