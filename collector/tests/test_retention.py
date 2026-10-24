import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from wids.engine import RETENTION_INTERVAL_SECONDS, Engine, retention_loop
from wids.webapp import create_app


def test_idle_server_expires_frames_and_alerts_on_timer(settings, frame, monkeypatch):
    clock = [datetime.now(timezone.utc)]
    class Clock:
        @staticmethod
        def now(tz):
            return clock[0].astimezone(tz)
    monkeypatch.setattr('wids.storage.datetime', Clock)
    engine = Engine(replace(settings, deauth_threshold=1))
    engine.ingest(frame)
    tick = threading.Event()
    cleaned = threading.Event()
    waits = []
    cleanup = engine.store.cleanup
    def tracked_cleanup():
        cleanup()
        cleaned.set()
    monkeypatch.setattr(engine.store, 'cleanup', tracked_cleanup)
    def controlled_timer(core, stop):
        class Timer:
            def wait(self, interval):
                waits.append(interval)
                # Test ticks advance simulated time; this short wait only lets
                # server shutdown wake the fake timer, without a 60-second sleep.
                while not stop.is_set():
                    if tick.wait(0.01):
                        tick.clear()
                        return False
                return True
        retention_loop(core, Timer())
    monkeypatch.setattr('wids.webapp.retention_loop', controlled_timer)
    with TestClient(create_app(settings, engine)) as client:
        assert len(client.get('/api/frames').json()) == 1
        assert len(client.get('/api/alerts').json()) == 1
        clock[0] += timedelta(days=8)
        tick.set()
        assert cleaned.wait(timeout=2)
        assert client.get('/api/frames').json() == []
        assert client.get('/api/alerts').json() == []
        assert len(client.get('/api/sensors').json()) == 1
        assert engine.processed == 1  # No heartbeat or extra ingestion triggered expiry.
        assert set(waits) == {RETENTION_INTERVAL_SECONDS}


def test_cleanup_failure_is_logged_and_retried(settings, monkeypatch, caplog):
    engine = Engine(settings)
    calls = []
    waits = []
    def cleanup():
        calls.append(True)
        if len(calls) == 1:
            raise sqlite3.OperationalError('Temporary database contention')
    class Stop:
        def wait(self, interval):
            waits.append(interval)
            return len(waits) > 2
    monkeypatch.setattr(engine.store, 'cleanup', cleanup)
    retention_loop(engine, Stop())
    assert len(calls) == 2
    assert waits == [60, 60, 60]
    assert 'Scheduled retention cleanup failed' in caplog.text
    engine.store.close()


def test_shutdown_joins_retention_worker_before_closing_database(settings, monkeypatch):
    engine = Engine(settings)
    started = threading.Event()
    stopped = threading.Event()
    def worker(core, stop):
        started.set()
        stop.wait()
        # Accessing SQLite here must still be safe during shutdown.
        core.store.rows('SELECT COUNT(*) FROM frames')
        stopped.set()
    close = engine.store.close
    def checked_close():
        assert stopped.is_set()
        close()
    monkeypatch.setattr('wids.webapp.retention_loop', worker)
    monkeypatch.setattr(engine.store, 'close', checked_close)
    with pytest.raises(RuntimeError, match='Exit the request context'):
        with TestClient(create_app(settings, engine)) as client:
            assert started.wait(timeout=2)
            assert client.get('/api/health').status_code == 200
            raise RuntimeError('Exit the request context')
    assert stopped.is_set()
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        engine.store.rows('SELECT 1')
