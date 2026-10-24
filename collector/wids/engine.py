"""One serialized ingestion pipeline for serial, demo and replay."""
import logging
import threading
from typing import Any

from .config import Settings
from .detection import Detector
from .models import Frame, parse_wire_line
from .storage import Store

LOG = logging.getLogger(__name__)


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.database, settings.retention_days)
        self.detector = Detector(settings)
        self.lock = threading.Lock()
        self.processed = 0

    def ingest(self, event: dict[str, Any]) -> bool:
        with self.lock:
            if event.get("kind") == "frame":
                frame = Frame.from_json(event)
                self.store.add_frame(frame, self.detector.observe(frame))
            elif event.get("kind") == "heartbeat":
                self.store.heartbeat(str(event["sensor_id"]), int(event.get("channel", 0)),
                                     int(event.get("uptime_ms", 0)), int(event.get("dropped", 0)))
            else:
                return False
            self.processed += 1
            if self.processed % 1000 == 0:
                self.store.cleanup()
        return True

    def ingest_line(self, line: bytes | str) -> bool:
        obj = parse_wire_line(line)
        if obj is None:
            return False
        return self.ingest(obj)


def serial_loop(engine: Engine, stop: threading.Event) -> None:
    """Reconnect on USB disconnect. Ignored boot/log lines do not stop ingestion."""
    import serial
    assert engine.settings.serial_port
    while not stop.is_set():
        try:
            LOG.info("Connecting to %s at %d baud", engine.settings.serial_port, engine.settings.baud)
            with serial.Serial(engine.settings.serial_port, engine.settings.baud, timeout=1) as device:
                while not stop.is_set():
                    line = device.readline()
                    if not line:
                        continue
                    try:
                        engine.ingest_line(line)
                    except (ValueError, KeyError, TypeError, OverflowError) as exc:
                        LOG.warning("Rejected malformed sensor event: %s", exc)
        except (serial.SerialException, OSError) as exc:
            LOG.warning("Serial disconnected/unavailable: %s", exc)
            stop.wait(3)
