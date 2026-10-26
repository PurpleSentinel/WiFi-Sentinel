import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from wids.engine import Engine
from wids.webapp import create_app
from wids.system_metrics import SystemMetrics, cpu_percent, cpu_ticks, memory_metrics, inspect_database, file_metrics


def test_host_calculations():
    memory = memory_metrics('MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 200 kB\nSwapFree: 50 kB')
    assert memory['used_bytes'] == 750 * 1024
    assert memory['used_percent'] == 75
    assert memory['swap_used_bytes'] == 150 * 1024
    assert memory_metrics(None)['used_bytes'] is None
    assert cpu_ticks('cpu 10 0 10 70 10 0 0 0 5 0') == (100, 80)
    assert cpu_percent((100, 80), (200, 130)) == 50
    assert cpu_percent(None, (200, 130)) is None
    assert cpu_percent((200, 130), (100, 80)) is None


def test_database_read_only_missing_and_partial(tmp_path):
    path = tmp_path / 'capture.sqlite3'
    assert inspect_database(path)['error']
    assert not path.exists()
    assert file_metrics(Path(str(path) + '-wal')) == {'path': str(path) + '-wal', 'present': False, 'bytes': 0, 'error': None}
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE frames(timestamp TEXT)')
        db.executemany('INSERT INTO frames VALUES (?)', [('2026-01-01',), ('2026-01-02',)])
    before = hashlib.sha256(path.read_bytes()).digest()
    snapshot = inspect_database(path)
    row = snapshot['tables'][0]
    assert row['row_count'] == 2
    assert row['oldest_timestamp'] == '2026-01-01'
    assert row['newest_timestamp'] == '2026-01-02'
    assert snapshot['application_schema_version'] is None
    assert snapshot['free_page_bytes'] == snapshot['free_pages'] * snapshot['page_size']
    assert snapshot['tables'][1]['present'] is False
    assert inspect_database(path, budget=-1)['error']
    assert hashlib.sha256(path.read_bytes()).digest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['capture.sqlite3']
    with patch.object(Path, 'stat', side_effect=PermissionError('restricted')):
        assert file_metrics(path)['bytes'] is None
        assert 'PermissionError' in inspect_database(path)['error']


def test_system_api_and_cache(settings, frame, monkeypatch):
    engine = Engine(settings)
    engine.ingest(frame)
    app = create_app(settings, engine)
    with TestClient(app) as client:
        # A system request must not call retention, create a Store or touch the sensor.
        monkeypatch.setattr(engine.store, 'cleanup', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('maintenance')))
        response = client.get('/api/system')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        data = response.json()
        assert data['collector']['serial_enabled'] is False
        assert data['databases']['capture']['tables'][0]['row_count'] == 1
        tables = {table['name']: table for table in data['databases']['capture']['tables']}
        assert tables['ble_labels']['row_count'] == 0
        assert tables['ble_labels']['oldest_timestamp'] is None
        assert data['databases']['capture']['error'] is None
        assert data['policy']['ble_display_window_hours'] == 1
        assert data['host']['application_version']
        assert client.get('/api/system').json()['database_cache']['reused'] is True
        assert 'configuration_key' not in response.text
        assert 'payload_hex' not in str(data['host'])


def test_cache_expiry_busy_and_unavailable(settings):
    monitor = SystemMetrics()
    with patch('wids.system_metrics.read_text', return_value=None), patch('wids.system_metrics.inspect_database', wraps=inspect_database) as inspect:
        first = monitor.snapshot(settings, {'connected': False})
        assert first['host']['hardware_model'] is None
        assert first['host']['memory']['total_bytes'] is None
        assert first['host']['temperature']['celsius'] is None
        monitor.snapshot(settings, {'connected': False})
        assert inspect.call_count == 2
        monitor.database_sample_time -= 16
        monitor.snapshot(settings, {'connected': False})
        assert inspect.call_count == 4
        monitor.lock.acquire()
        try:
            import pytest
            with pytest.raises(RuntimeError):
                monitor.snapshot(settings, {'connected': False})
        finally:
            monitor.lock.release()
