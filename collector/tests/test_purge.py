import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from wids.engine import Engine
from wids.purge import PurgeManager, TABLES, validate_ages
from wids.webapp import create_app
from wids.runtime import configuration_key


def populate(engine, frame, count=3):
    for _ in range(count):
        engine.ingest(frame)
    with engine.store.lock, engine.store.db:
        engine.store.db.execute("UPDATE frames SET timestamp='2026-01-01T00:00:00+00:00'")


def test_preview_boundaries_scope_and_no_writes(settings, frame):
    engine = Engine(settings)
    populate(engine, frame)
    instant = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    cutoff = (instant - timedelta(hours=1)).isoformat(timespec='seconds')
    with engine.store.lock, engine.store.db:
        engine.store.db.execute('UPDATE frames SET timestamp=? WHERE id=2', (cutoff,))
        engine.store.db.execute('UPDATE frames SET timestamp=? WHERE id=3', (instant.isoformat(),))
    monitor = PurgeManager(engine, lambda: None)
    before = engine.store.db.total_changes
    files = [settings.database, settings.database.with_name(settings.database.name + '-wal')]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()}
    with patch('wids.purge.datetime') as clock:
        clock.now.return_value = instant
        preview = monitor.preview({'frames': 1})
    assert preview['counts'] == {'frames': {'eligible': 1, 'remaining': 2, 'total': 3}}
    assert preview['cutoffs']['frames'] == cutoff
    assert engine.store.db.total_changes == before
    assert hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()}
    job = monitor.start(preview['token'], 'PURGE')
    monitor.worker.join(5)
    assert monitor.status()['state'] == 'completed'
    assert monitor.status()['deleted'] == {'frames': 1}
    assert monitor.start(preview['token'], 'PURGE')['id'] == job['id']
    assert engine.store.rows('SELECT timestamp FROM frames ORDER BY id') == [{'timestamp': cutoff}, {'timestamp': instant.isoformat()}]
    monitor.close()
    engine.store.close()


@pytest.mark.parametrize('ages', [{}, {'sensors': 1}, {'frames': 0}, {'frames': -1}, {'frames': True}, {'frames': '24'}, {'frames': float('nan')}, {'frames': float('inf')}, {'frames': 876001}, []])
def test_invalid_ages(ages):
    with pytest.raises(ValueError):
        validate_ages(ages)


def test_expired_empty_and_bounded_previews(settings):
    engine = Engine(settings)
    monitor = PurgeManager(engine, lambda: None)
    preview = monitor.preview({'frames': 1})
    with pytest.raises(ValueError, match='No matching'):
        monitor.start(preview['token'], 'PURGE')
    monitor.previews[preview['token']]['monotonic'] -= 601
    with pytest.raises(ValueError, match='expired'):
        monitor.start(preview['token'], 'PURGE')
    for _ in range(35):
        monitor.preview({'ble_alerts': 1})
    assert len(monitor.previews) == 32
    engine.store.close()


def test_partial_failure_and_cancellation(settings, frame):
    engine = Engine(settings)
    populate(engine, frame, 4)
    invalidations = []
    monitor = PurgeManager(engine, lambda: invalidations.append(True))
    preview = monitor.preview({'frames': 1})
    original = monitor._batch
    def fail_second(db, table, cutoff):
        if monitor.status()['deleted']['frames']:
            raise sqlite3.OperationalError('test busy')
        return original(db, table, cutoff)
    with patch('wids.purge.BATCH_ROWS', 2), patch.object(monitor, '_batch', side_effect=fail_second):
        monitor.start(preview['token'], 'PURGE')
        monitor.worker.join(5)
    assert monitor.status()['state'] == 'failed'
    assert monitor.status()['deleted']['frames'] == 2
    assert invalidations == [True]
    preview = monitor.preview({'frames': 1})
    def cancel_after_batch(db, table, cutoff):
        result = original(db, table, cutoff)
        monitor.cancel(monitor.status()['id'])
        return result
    with patch('wids.purge.BATCH_ROWS', 1), patch.object(monitor, '_batch', side_effect=cancel_after_batch):
        monitor.start(preview['token'], 'PURGE')
        monitor.worker.join(5)
    assert monitor.status()['state'] == 'cancelled'
    assert monitor.status()['deleted']['frames'] == 1
    engine.store.close()


def test_all_tables_accounting_and_preserved_records(settings, frame):
    engine = Engine(settings)
    populate(engine, frame)
    with engine.store.lock, engine.store.db:
        engine.store.db.execute("INSERT INTO ble_observations(timestamp,sensor_id,address,address_type,rssi,payload_hex,event_type,uptime_ms) VALUES('2026-01-01','c6','aa','random',-50,'',0,0)")
        engine.store.db.execute("INSERT INTO ble_alerts(timestamp,sensor_id,address,address_type,expression) VALUES('2026-01-01','c6','aa','random','rule')")
        engine.store.db.execute("INSERT INTO alerts(timestamp,sensor_id,rule,severity,bssid,channel,frame_count,details) VALUES('2026-01-01','c6','rule','low','aa',6,1,'example')")
        engine.store.db.execute("INSERT INTO ble_labels VALUES('c6','aa','random','Lamp','Keep label','2026-01-01')")
        engine.store.db.execute("INSERT INTO sensors(sensor_id,last_seen) VALUES('c6','2026-01-01')")
        engine.store.ble_counts = {'ble_observations': 1, 'ble_alerts': 1}
    monitor = PurgeManager(engine, lambda: None)
    preview = monitor.preview(dict.fromkeys(TABLES, 1))
    monitor.start(preview['token'], 'PURGE')
    monitor.worker.join(5)
    assert monitor.status()['deleted'] == {'frames': 3, 'alerts': 1, 'ble_observations': 1, 'ble_alerts': 1}
    assert engine.store.ble_counts == {'ble_observations': 0, 'ble_alerts': 0}
    assert len(engine.store.rows('SELECT * FROM ble_labels')) == 1
    assert {row['sensor_id'] for row in engine.store.rows('SELECT * FROM sensors')} == {'c6', 'sensor-1'}
    engine.store.close()


def test_concurrent_pipeline_and_duplicate_job(settings, frame):
    engine = Engine(settings)
    populate(engine, frame, 5)
    monitor = PurgeManager(engine, lambda: None)
    preview = monitor.preview({'frames': 1})
    entered, release = threading.Event(), threading.Event()
    original = monitor._batch
    def wait_batch(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    with patch.object(monitor, '_batch', side_effect=wait_batch):
        job = monitor.start(preview['token'], 'PURGE')
        assert entered.wait(5)
        assert monitor.start(preview['token'], 'PURGE')['id'] == job['id']
        other = monitor.preview({'frames': 2})
        with pytest.raises(RuntimeError):
            monitor.start(other['token'], 'PURGE')
        engine.ingest(frame)  # Host receive now: must survive the frozen cutoff.
        with engine.lock:
            engine.store.cleanup()  # Cooperating retention may remove previewed rows first.
        release.set()
        monitor.worker.join(5)
    assert monitor.status()['state'] == 'completed'
    assert len(engine.store.rows('SELECT * FROM frames')) == 1
    engine.store.close()


def test_purge_api_authorization_and_preview_validation(settings, frame):
    engine = Engine(settings)
    populate(engine, frame)
    with TestClient(create_app(settings, engine)) as client:
        defaults = client.get('/api/purge').json()
        assert defaults['defaults_hours']['frames'] == settings.retention_days * 24
        assert client.post('/api/purge/preview', json={'ages_hours': {'frames': 0}}).status_code == 400
        preview = client.post('/api/purge/preview', json={'ages_hours': {'frames': 1}}).json()
        body = {'token': preview['token'], 'confirmation': 'PURGE'}
        assert client.post('/api/purge/start', json=body).status_code == 403
        headers = {'X-Configuration-Key': configuration_key(settings), 'Origin': 'http://evil.test'}
        assert client.post('/api/purge/start', headers=headers, json=body).status_code == 403
        headers['Origin'] = 'http://testserver'
        assert client.post('/api/purge/start', headers=headers, json={**body, 'ages_hours': {'alerts': 1}}).status_code == 400
        response = client.post('/api/purge/start', headers=headers, json=body)
        assert response.status_code == 200
        assert client.post('/api/purge/start', headers=headers, json=body).json()['id'] == response.json()['id']
        assert client.post('/api/purge/cancel', json={'id': response.json()['id']}).status_code == 403
        assert client.post('/api/purge/cancel', headers=headers, json={'id': response.json()['id']}).status_code == 200
