"""Automatic retention policy, migration and authorization on isolated databases."""
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from wids.config import Settings
from wids.engine import Engine, retention_loop
from wids.purge import PurgeManager
from wids.retention import RetentionManager, destructive_change, policy_from, validate_policy
from wids.runtime import configuration_key, settings_path
from wids.webapp import create_app


def old_frame(engine, frame, timestamp='2026-01-01T00:00:00+00:00'):
    engine.ingest(frame)
    with engine.store.lock, engine.store.db:
        engine.store.db.execute('UPDATE frames SET timestamp=? WHERE id=(SELECT MAX(id) FROM frames)', (timestamp,))


def test_legacy_days_source_and_policy_validation(settings, monkeypatch):
    engine = Engine(replace(settings, retention_days=2, ble_retention_days=3))
    assert policy_from(engine.settings)['wifi_age_hours'] == 48
    assert policy_from(engine.settings)['ble_age_hours'] == 72
    policy = policy_from(engine.settings)
    assert destructive_change(policy, {**policy, 'wifi_age_hours': 24})
    assert destructive_change(policy, {**policy, 'automatic_age_deletion': False, 'ble_max_records': 100})
    assert not destructive_change(policy, {**policy, 'automatic_age_deletion': False})
    for bad in ({}, {**policy, 'wifi_age_hours': 0}, {**policy, 'ble_age_hours': 87601},
                {**policy, 'automatic_age_deletion': 1}, {**policy, 'ble_max_records': 99},
                {**policy, 'cleanup_interval_seconds': 14}, {**policy, 'unknown': 1}):
        with pytest.raises(ValueError):
            validate_policy(bad)
    assert not settings_path(settings).exists()
    engine.store.close()
    monkeypatch.setenv('WIDS_AUTOMATIC_AGE_DELETION', 'false')
    monkeypatch.setenv('WIDS_RETENTION_HOURS', '36')
    configured = replace(Settings.from_env(), database=settings.database)
    assert configured.retention_hours == 36
    assert configured.automatic_age_deletion is False


def test_age_cutoff_exact_boundary_and_disabled_cleanup(settings, frame, monkeypatch):
    instant = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    class Clock:
        @staticmethod
        def now(tz):
            return instant.astimezone(tz)
    monkeypatch.setattr('wids.storage.datetime', Clock)
    engine = Engine(replace(settings, retention_hours=1, automatic_age_deletion=False, ble_max_records=100))
    cutoff = (instant - timedelta(hours=1)).isoformat(timespec='seconds')
    old_frame(engine, frame, '2026-01-01T00:00:00+00:00')
    old_frame(engine, frame, cutoff)
    # Disabled age cleanup retains both, including startup/manual cleanup.
    assert engine.store.cleanup().get('frames', 0) == 0
    assert len(engine.store.rows('SELECT * FROM frames')) == 2
    engine.store.automatic_age_deletion = True
    result = engine.store.cleanup_batch()
    assert result['frames'] == 1
    assert [row['timestamp'] for row in engine.store.rows('SELECT timestamp FROM frames')] == [cutoff]
    engine.store.close()


def test_disabled_policy_preserves_history_on_restart_and_cap_still_applies(settings, frame):
    engine = Engine(replace(settings, automatic_age_deletion=False, ble_max_records=100))
    old_frame(engine, frame)
    with engine.store.lock, engine.store.db:
        engine.store.db.executemany("INSERT INTO ble_observations(timestamp,sensor_id,address,address_type,rssi,payload_hex,event_type,uptime_ms) VALUES('2026-01-01','c6','aa','random',-50,'',0,0)", [() for _ in range(101)])
        engine.store.ble_counts['ble_observations'] = 101
    removed = engine.store.cleanup_batch()
    assert removed['frames'] == 0
    assert removed['ble_observations'] == 1
    assert len(engine.store.rows('SELECT * FROM frames')) == 1
    engine.store.close()
    restarted = Engine(replace(settings, automatic_age_deletion=False, ble_max_records=100))
    assert len(restarted.store.rows('SELECT * FROM frames')) == 1
    assert restarted.store.ble_counts['ble_observations'] == 100
    restarted.store.close()


def test_policy_preview_apply_persistence_and_busy_coordination(settings, frame):
    engine = Engine(settings)
    old_frame(engine, frame)
    purge = PurgeManager(engine, lambda: None)
    invalidated = []
    manager = RetentionManager(engine, purge, lambda: invalidated.append(True))
    policy = {**policy_from(engine.settings), 'wifi_age_hours': 1,
              'cleanup_interval_seconds': 15, 'ble_max_records': 100}
    preview = manager.preview(policy)
    assert preview['destructive'] is True
    assert preview['counts']['frames']['age_eligible'] == 1
    assert preview['counts']['alerts']['age_eligible'] == 0
    assert preview['cutoffs']['frames'].endswith('+00:00')
    assert len(engine.store.rows('SELECT * FROM frames')) == 1
    with pytest.raises(ValueError, match='preview'):
        manager.apply(policy, None, None)
    with pytest.raises(ValueError, match='preview'):
        manager.apply(policy, preview['token'], 'wrong')
    with pytest.raises(ValueError, match='Preview does not match'):
        manager.apply({**policy, 'ble_age_hours': 1}, preview['token'], 'RETENTION')
    release = threading.Event()
    with patch.object(purge, 'worker', threading.Thread(target=lambda: release.wait(5))):
        purge.worker.start()
        try:
            with pytest.raises(RuntimeError, match='Manual purge'):
                manager.apply(policy, preview['token'], 'RETENTION')
        finally:
            release.set()
            purge.worker.join()
    result = manager.apply(policy, preview['token'], 'RETENTION')
    assert result['policy']['wifi_age_hours'] == 1
    manager.worker.join(5)
    assert not manager.worker.is_alive()
    assert manager.status()['status']['last_deleted']['frames'] == 1
    assert invalidated == [True]
    assert engine.store.rows('SELECT * FROM frames') == []
    assert manager.apply(policy, preview['token'], 'RETENTION')['policy'] == policy
    assert settings_path(settings).exists()
    manager.close();engine.store.close()
    restarted = Engine(settings)
    assert policy_from(restarted.settings) == policy
    restarted.store.close()


def test_nondestructive_interval_save_and_policy_sources(settings, frame, monkeypatch):
    engine = Engine(settings)
    old_frame(engine, frame)
    purge = PurgeManager(engine, lambda: None)
    manager = RetentionManager(engine, purge, lambda: None)
    policy = {**policy_from(engine.settings), 'automatic_age_deletion': False,
              'cleanup_interval_seconds': 120}
    manager.apply(policy, None, None)
    manager.worker.join(5)
    assert len(engine.store.rows('SELECT * FROM frames')) == 1
    status = manager.status()
    assert status['sources']['automatic_age_deletion'] == 'saved runtime settings'
    assert status['status']['last_source'] == 'policy_save'
    assert status['policy']['cleanup_interval_seconds'] == 120
    # An unrelated collector change must not trigger immediate age deletion.
    monkeypatch.setattr(engine.store, 'cleanup', lambda: (_ for _ in ()).throw(AssertionError('unexpected purge')))
    engine.configure({'window_seconds': 20})
    assert len(engine.store.rows('SELECT * FROM frames')) == 1
    manager.close();engine.store.close()


def test_scheduled_interval_error_retry_and_status(settings, monkeypatch):
    engine = Engine(replace(settings, cleanup_interval_seconds=15))
    calls, waits = [], []
    def batch():
        calls.append(True)
        if len(calls) == 1:
            raise sqlite3.OperationalError('temporary busy')
        return {name: 0 for name in ('frames', 'alerts', 'ble_observations', 'ble_alerts')}
    monkeypatch.setattr(engine.store, 'cleanup_batch', batch)
    class Stop:
        def wait(self, seconds):
            waits.append(seconds)
            return len(waits) > 2
    retention_loop(engine, Stop())
    assert waits == [15, 15, 15]
    assert len(calls) == 2
    assert engine.retention_snapshot()['last_error'] is None
    assert engine.retention_snapshot()['last_source'] == 'scheduled'
    engine.store.close()


def test_api_authorization_stale_preview_no_data_mutation(settings, frame, monkeypatch):
    engine = Engine(settings)
    old_frame(engine, frame)
    with TestClient(create_app(settings, engine)) as client:
        policy = client.get('/api/retention').json()['policy']
        policy['wifi_age_hours'] = 1
        assert client.post('/api/retention/preview', json={**policy, 'wifi_age_hours': 0}).status_code == 400
        response = client.post('/api/retention/preview', json=policy)
        assert response.status_code == 200
        preview = response.json()
        assert preview['counts']['frames']['age_eligible'] == 1
        assert len(client.get('/api/frames').json()) == 1
        body = {'policy': policy, 'token': preview['token'], 'confirmation': 'RETENTION'}
        assert client.post('/api/retention/apply', json=body).status_code == 403
        headers = {'Origin': 'http://evil.test', 'X-Configuration-Key': configuration_key(settings)}
        assert client.post('/api/retention/apply', headers=headers, json=body).status_code == 403
        headers['Origin'] = 'http://testserver'
        assert client.post('/api/configuration/collector', headers=headers, json={'retention_days': 1}).status_code == 400
        assert client.post('/api/retention/apply', headers=headers, json={**body, 'policy': {**policy, 'ble_age_hours': 1}}).status_code == 400
        assert client.post('/api/retention/apply', headers=headers, json=body).status_code == 200
        assert client.get('/api/retention').json()['policy']['wifi_age_hours'] == 1
        assert 'config-key' not in client.get('/api/retention').text
