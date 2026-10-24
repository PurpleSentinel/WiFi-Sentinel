# Operations runbook

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
| Unknown target `esp32c5` | ESP-IDF too old; use v5.5.2+ |
| Flash port not found | Check actual PCB USB data path/cable, `lsusb`, `dmesg`, `/dev/serial/by-id` |
| Permission denied on `/dev/tty*` | User group and active session; stop any other serial terminal |
| No `WIDS` lines | Wrong console selected, firmware not flashed, capture quiet; heartbeat should still appear |
| Only heartbeat but no frames | Wrong channel/band, RF placement/antenna, receive configuration; reduce beacon sampling temporarily |
| Frame channel 0 or unexpected | Verify ESP-IDF promiscuous RX metadata on the actual C5 revision |
| `dropped` increasing | Reduce beacon telemetry, shorten USB path/avoid overloaded Pi, check host logs |
| All rules quiet while frames arrive | Threshold too high, wrong BSSID filters, no relevant subtype |
| Many rogue-SSID alerts | Complete list of legitimate multi-BSSID APs and extenders/mesh nodes |
| UI unreachable remotely | Expected: default binding is 127.0.0.1; use SSH forward, not public exposure |
| Wrong timestamps | Pi host clock not synced, USB ingestion delay, data uses host UTC receive time |

## Retention

Every collector startup and every 1000 accepted events triggers deletion of old frames and alerts. If no events arrive for days, existing data is not deleted until a restart or a new 1000-event checkpoint. Scheduled cleanup is a roadmap improvement. Sensor last-seen rows are not automatically deleted.

## Backup / incident preservation

- Stop collector before copying the database, or use SQLite's backup API rather than copying a live WAL-mode DB file alone.
- Preserve DB provenance (hostname, UTC time, collection channel, detector config, SHA256 digest) and avoid altering the original.
- Export only minimum data necessary, encrypted at rest if transferred.
- Deleting SQLite database and WAL/SHM files resets the local store (stop application first).
- Frames do **not** contain raw 802.11 packet bytes. This is not a replacement for a full forensic capture tool.

## Updating

Back up SQLite, check `git diff` and release notes, run Python tests and repeat firmware smoke tests for changed IDF versions. Avoid auto-upgrading firmware without a verified rollback process. Database schema has no migration framework yet; check schema compatibility before modifying.
