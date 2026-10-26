"""One serialized ingestion pipeline for serial, demo and replay."""
import logging
from datetime import datetime, timedelta, timezone
import sqlite3
import threading
import time
from dataclasses import replace
from typing import Any

from .config import Settings
from .ble import Advertisement, BLEPolicy
from .detection import Detector
from .models import Frame, parse_wire_line
from .runtime import load_settings, save_settings, validate_collector
from .sensor import SensorControl
from .storage import Store

LOG = logging.getLogger(__name__)
RETENTION_INTERVAL_SECONDS = 60


class Engine:
    def __init__(self, settings: Settings):
        settings = load_settings(settings)
        self.settings = settings
        self.store = Store(settings.database, settings.retention_days,
                           settings.ble_retention_days, settings.ble_max_records,
                           settings.retention_hours, settings.ble_retention_hours,
                           settings.automatic_age_deletion)
        self.ble = BLEPolicy()
        self.detector = Detector(settings)
        self.lock = threading.Lock()
        self.retention_lock = threading.Lock()
        self.retention_status_lock = threading.Lock()
        self.retention_wakeup = threading.Event()
        self.retention_status = {"running": False, "last_run_at": None, "last_source": None,
                                 "last_deleted": self.store.startup_cleanup, "current_deleted": None,
                                 "last_error": None, "started_at": None,
                                 "next_run_at": None, "startup_deleted": self.store.startup_cleanup}
        self.processed = 0
        self.sensor = SensorControl()

    def configure(self, values: dict, defer_cleanup: bool = False) -> None:
        values = validate_collector(values)
        with self.lock:
            if 'retention_days' in values and 'retention_hours' not in values:
                values['retention_hours'] = None
            if 'ble_retention_days' in values and 'ble_retention_hours' not in values:
                values['ble_retention_hours'] = None
            settings = replace(self.settings, **values)
            policy_changed = any(getattr(settings, name) != getattr(self.settings, name) for name in
                ('retention_days', 'ble_retention_days', 'retention_hours', 'ble_retention_hours',
                 'automatic_age_deletion', 'cleanup_interval_seconds', 'ble_max_records'))
            save_settings(settings)
            self.settings = settings
            # A retention-only save leaves live detection windows intact.
            if any(name not in ('retention_days', 'ble_retention_days', 'retention_hours',
                                'ble_retention_hours', 'automatic_age_deletion',
                                'cleanup_interval_seconds', 'ble_max_records') for name in values):
                self.detector = Detector(settings)
            self.store.retention_days = settings.retention_days
            self.store.ble_retention_days = settings.ble_retention_days
            self.store.ble_max_records = settings.ble_max_records
            self.store.retention_hours = settings.retention_hours
            self.store.ble_retention_hours = settings.ble_retention_hours
            self.store.automatic_age_deletion = settings.automatic_age_deletion
            if any(name.startswith('ble_') and name not in ('ble_retention_days', 'ble_retention_hours', 'ble_max_records') for name in values):
                self.ble = BLEPolicy()
            if policy_changed:
                self.retention_wakeup.set()
                if not defer_cleanup:
                    self.store.cleanup()

    def retention_snapshot(self) -> dict:
        with self.retention_status_lock:
            return dict(self.retention_status)

    def run_retention(self, source: str, stop: threading.Event | None = None) -> dict | None:
        purge = getattr(self, 'purge_manager', None)
        if purge is not None and purge.worker is not None and purge.worker.is_alive():
            return None
        if not self.retention_lock.acquire(blocking=False):
            return None
        totals = {name: 0 for name in ('frames', 'alerts', 'ble_observations', 'ble_alerts')}
        with self.retention_status_lock:
            self.retention_status.update(running=True, last_source=source, last_error=None,
                                         started_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                         current_deleted=dict(totals))
        try:
            while True:
                if stop is not None and stop.is_set():
                    break
                with self.lock:
                    deleted = self.store.cleanup_batch()
                for table, count in deleted.items():
                    totals[table] += count
                with self.retention_status_lock:
                    self.retention_status['current_deleted'] = dict(totals)
                if all(count < 500 for count in deleted.values()):
                    break
                if stop is not None and stop.wait(0.02):
                    break
                if stop is None:
                    time.sleep(0.02)
            with self.retention_status_lock:
                self.retention_status.update(last_run_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                             last_deleted=totals)
            return totals
        except (sqlite3.Error, OSError) as exc:
            with self.retention_status_lock:
                self.retention_status.update(last_error=f'{type(exc).__name__}: {str(exc)[:180]}',
                                             last_run_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                             last_deleted=totals)
            raise
        finally:
            with self.retention_status_lock:
                self.retention_status['running'] = False
                self.retention_status['current_deleted'] = None
            self.retention_lock.release()

    def ingest(self, event: dict[str, Any]) -> bool:
        with self.lock:
            if event.get("kind") == "frame":
                frame = Frame.from_json(event)
                self.store.add_frame(frame, self.detector.observe(frame))
            elif event.get('kind') == 'ble':
                ad = Advertisement.from_json(event)
                accept, matches = self.ble.observe(ad, self.settings, time.monotonic())
                self.store.add_ble(ad, accept, matches)
            elif event.get("kind") == "heartbeat":
                self.store.heartbeat(str(event["sensor_id"]), int(event.get("channel", 0)),
                                     int(event.get("uptime_ms", 0)), int(event.get("dropped", 0)))
            else:
                return False
            self.processed += 1
        return True

    def ingest_line(self, line: bytes | str) -> bool:
        obj = parse_wire_line(line)
        if obj is None:
            return False
        if self.sensor.receive(obj):
            return True
        return self.ingest(obj)


def retention_loop(engine: Engine, stop: threading.Event,
                   interval: float | None = None) -> None:
    """Reschedule on policy edits; complete age/cap backlog in short batches."""
    LOG.info('Scheduled retention cleanup worker started')
    while True:
        seconds = interval if interval is not None else engine.settings.cleanup_interval_seconds
        with engine.retention_status_lock:
            engine.retention_status['next_run_at'] = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec='seconds')
        if isinstance(stop, threading.Event):
            awakened = engine.retention_wakeup.wait(seconds)
            engine.retention_wakeup.clear()
            if stop.is_set():
                break
            if awakened:
                continue
        elif stop.wait(seconds):
            break
        try:
            engine.run_retention('scheduled', stop if isinstance(stop, threading.Event) else None)
        except (sqlite3.Error, OSError):
            LOG.exception('Scheduled retention cleanup failed; retrying on the next interval')
    with engine.retention_status_lock:
        engine.retention_status['next_run_at'] = None


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
