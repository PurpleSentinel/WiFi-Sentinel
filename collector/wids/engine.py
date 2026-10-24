"""One serialized ingestion pipeline for serial, demo and replay."""
import logging
import threading
import time
from dataclasses import replace
from typing import Any

from .config import Settings
from .detection import Detector
from .models import Frame, parse_wire_line
from .runtime import load_settings, save_settings, validate_collector
from .sensor import SensorControl
from .storage import Store

LOG = logging.getLogger(__name__)


class Engine:
    def __init__(self, settings: Settings):
        settings = load_settings(settings)
        self.settings = settings
        self.store = Store(settings.database, settings.retention_days)
        self.detector = Detector(settings)
        self.lock = threading.Lock()
        self.processed = 0
        self.sensor = SensorControl()

    def configure(self, values: dict) -> None:
        values = validate_collector(values)
        with self.lock:
            settings = replace(self.settings, **values)
            save_settings(settings)
            self.settings = settings
            # Existing windows have the old policy; start new windows on apply.
            self.detector = Detector(settings)
            self.store.retention_days = settings.retention_days
            self.store.cleanup()

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
        if self.sensor.receive(obj):
            return True
        return self.ingest(obj)


def serial_loop(engine: Engine, stop: threading.Event) -> None:
    """Own serial telemetry and configuration commands; reconnect on disconnect."""
    import serial
    assert engine.settings.serial_port
    while not stop.is_set():
        try:
            LOG.info("Connecting to %s at %d baud", engine.settings.serial_port, engine.settings.baud)
            with serial.Serial(engine.settings.serial_port, engine.settings.baud, timeout=0.2, write_timeout=1) as device:
                engine.sensor.connect()
                device.write(engine.sensor.wire('refresh', 'get_config'))
                next_refresh = time.monotonic() + 5
                buffer = bytearray()
                oversized = False
                while not stop.is_set():
                    if time.monotonic() >= next_refresh:
                        device.write(engine.sensor.wire('refresh', 'get_config'))
                        next_refresh = time.monotonic() + 5
                    engine.sensor.send_queued(device)
                    # Preserve partial lines across timeouts; bound input memory.
                    data = device.read(min(max(device.in_waiting, 1), 2048))
                    for byte in data:
                        if byte == 10:
                            if not oversized:
                                try:
                                    engine.ingest_line(bytes(buffer))
                                except (ValueError, KeyError, TypeError, OverflowError) as exc:
                                    LOG.warning("Rejected malformed sensor event: %s", exc)
                            buffer.clear()
                            oversized = False
                        elif not oversized:
                            buffer.append(byte)
                            if len(buffer) > 2048:
                                buffer.clear()
                                oversized = True
        except (serial.SerialException, OSError) as exc:
            LOG.warning("Serial disconnected/unavailable: %s", exc)
            stop.wait(3)
        finally:
            engine.sensor.disconnect()
