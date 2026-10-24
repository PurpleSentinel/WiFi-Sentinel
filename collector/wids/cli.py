"""CLI: serve, replay, demo, and health/check operation."""
import argparse
import logging
from pathlib import Path

from .config import Settings
from .engine import Engine
from .webapp import create_app


def _frame(kind: str, i: int, *, sensor: str = "demo-c5", bssid: str = "02:11:22:33:44:55",
           sa: str = "02:aa:bb:cc:dd:01", channel: int = 6, status: int = -1, ssid=None) -> dict:
    return {"v": 1, "kind": "frame", "sensor_id": sensor, "channel": channel,
            "subtype": kind, "sa": sa, "da": "ff:ff:ff:ff:ff:ff", "bssid": bssid,
            "rssi": -40 - (i % 20), "protected": False, "reason_code": 7 if kind == "deauth" else -1,
            "status_code": status, "ssid": ssid, "uptime_ms": i * 10}


def demo(engine: Engine) -> int:
    """Inject synthetic events ONLY into local SQLite, never over RF."""
    count = 0
    events = [_frame("beacon", 0, ssid="ExampleLab"),
              _frame("beacon", 1, bssid="02:de:ad:be:ef:01", ssid="ExampleLab")]
    events += [_frame("auth", i, sa=f"02:aa:bb:cc:{i // 256:02x}:{i % 256:02x}") for i in range(75)]
    events += [_frame("deauth", i) for i in range(45)]
    events += [_frame("disassoc", i) for i in range(27)]
    events += [_frame("auth", i, status=1) for i in range(18)]
    for event in events:
        engine.ingest(event)
        count += 1
    print(f"Wrote {count} synthetic frames to {engine.settings.database}")
    print("These are simulations; no Wi-Fi transmissions occurred.")
    return count


def replay(engine: Engine, filename: Path) -> int:
    count = 0
    with filename.open(encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, start=1):
            if not line.strip() or line.startswith("#"):
                continue
            try:
                if not line.startswith("WIDS "):
                    line = "WIDS " + line
                if engine.ingest_line(line):
                    count += 1
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid event on line {lineno}: {exc}") from exc
    print(f"Imported {count} events from {filename}")
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="WiFi Sentinel passive Wi-Fi IDS")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("serve", help="Start the local dashboard and optional USB serial receiver")
    subs.add_parser("demo", help="Generate synthetic event data in SQLite")
    p_replay = subs.add_parser("replay", help="Import NDJSON events from a file")
    p_replay.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Settings.from_env()
    if args.command == "serve":
        import uvicorn
        uvicorn.run(create_app(config), host=config.host, port=config.port, log_level="info")
        return
    engine = Engine(config)
    try:
        if args.command == "demo":
            demo(engine)
        else:
            replay(engine, args.file)
    finally:
        engine.store.close()


if __name__ == "__main__":
    main()
