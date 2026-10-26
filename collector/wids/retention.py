"""Previewed, persistent automatic retention policy and run status."""
import copy
import json
import os
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timedelta, timezone

from .runtime import settings_path

FIELDS = ('wifi_age_hours', 'ble_age_hours', 'automatic_age_deletion',
          'cleanup_interval_seconds', 'ble_max_records')
TABLES = {'frames': 'wifi_age_hours', 'alerts': 'wifi_age_hours',
          'ble_observations': 'ble_age_hours', 'ble_alerts': 'ble_age_hours'}
EXPIRES_SECONDS = 600


def policy_from(settings):
    return {'wifi_age_hours': settings.retention_hours if settings.retention_hours is not None else settings.retention_days * 24,
            'ble_age_hours': settings.ble_retention_hours if settings.ble_retention_hours is not None else settings.ble_retention_days * 24,
            'automatic_age_deletion': settings.automatic_age_deletion,
            'cleanup_interval_seconds': settings.cleanup_interval_seconds,
            'ble_max_records': settings.ble_max_records}


def validate_policy(values):
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError('Supply all five automatic retention fields only')
    bounds = {'wifi_age_hours': (1, 87600), 'ble_age_hours': (1, 87600),
              'cleanup_interval_seconds': (15, 86400), 'ble_max_records': (100, 1000000)}
    for name, (low, high) in bounds.items():
        if type(values[name]) is not int or not low <= values[name] <= high:
            raise ValueError(f'{name} must be an integer in {low}..{high}')
    if type(values['automatic_age_deletion']) is not bool:
        raise ValueError('automatic_age_deletion must be true or false')
    return dict(values)


def destructive_change(old, new):
    age = new['automatic_age_deletion'] and (not old['automatic_age_deletion'] or
        new['wifi_age_hours'] < old['wifi_age_hours'] or new['ble_age_hours'] < old['ble_age_hours'])
    return age or new['ble_max_records'] < old['ble_max_records']


def sources(settings):
    try:
        saved = json.loads(settings_path(settings).read_text())
        if not isinstance(saved, dict):
            saved = {}
    except (OSError, ValueError):
        saved = {}
    def source(hour, day):
        if hour in saved and saved[hour] is not None or day in saved:
            return 'saved runtime settings'
        if os.getenv('WIDS_' + hour.upper()) or os.getenv('WIDS_' + day.upper()):
            return 'environment'
        return 'default'
    def simple(name):
        if name in saved:
            return 'saved runtime settings'
        if os.getenv('WIDS_' + name.upper()) is not None:
            return 'environment'
        return 'default'
    return {'wifi_age_hours': source('retention_hours', 'retention_days'),
            'ble_age_hours': source('ble_retention_hours', 'ble_retention_days'),
            'automatic_age_deletion': simple('automatic_age_deletion'),
            'cleanup_interval_seconds': simple('cleanup_interval_seconds'),
            'ble_max_records': simple('ble_max_records')}


class RetentionManager:
    def __init__(self, engine, purge, invalidate):
        self.engine, self.purge, self.invalidate = engine, purge, invalidate
        engine.retention_manager = self
        self.lock = threading.RLock()
        self.previews = OrderedDict()
        self.worker = None

    def status(self):
        policy = policy_from(self.engine.settings)
        return {'policy': policy, 'sources': sources(self.engine.settings),
                'status': self.engine.retention_snapshot(),
                'rules': {'age_deletion': 'startup, confirmed save, then scheduled runs when enabled',
                          'ble_count_cap': 'always active, including when age deletion is off',
                          'display_window_hours': 1,
                          'excluded': ['sensors', 'ble_labels', 'vendor cache', 'configuration']}}

    def preview(self, values):
        proposed = validate_policy(values)
        current = policy_from(self.engine.settings)
        now = datetime.now(timezone.utc)
        cutoffs = {table: (now - timedelta(hours=proposed[age])).isoformat(timespec='seconds')
                   for table, age in TABLES.items()}
        counts = {}
        path = self.engine.settings.database.resolve()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.1)) as db:
            deadline = time.monotonic() + 1
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for table, cutoff in cutoffs.items():
                total = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                age_count = db.execute(f'SELECT COUNT(*) FROM {table} WHERE timestamp < ?', (cutoff,)).fetchone()[0]
                cap_count = max(0, total - proposed['ble_max_records']) if table.startswith('ble_') else 0
                counts[table] = {'total': total, 'age_eligible': age_count if proposed['automatic_age_deletion'] else 0,
                                 'cap_excess': cap_count}
        payload = {'token': secrets.token_urlsafe(24), 'created_at': now.isoformat(timespec='seconds'),
                   'expires_in_seconds': EXPIRES_SECONDS, 'policy': proposed, 'current_policy': current,
                   'cutoffs': cutoffs, 'counts': counts, 'destructive': destructive_change(current, proposed)}
        with self.lock:
            self.previews[payload['token']] = {'payload': payload, 'at': time.monotonic(), 'applied': False}
            for token, item in list(self.previews.items()):
                if time.monotonic() - item['at'] > EXPIRES_SECONDS:
                    del self.previews[token]
            while len(self.previews) > 32:
                self.previews.popitem(last=False)
        return copy.deepcopy(payload)

    def apply(self, values, token=None, confirmation=None):
        proposed = validate_policy(values)
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise RuntimeError('Automatic retention cleanup is running; retry shortly')
            if self.engine.retention_lock.locked():
                raise RuntimeError('Scheduled retention cleanup is running; retry shortly')
            if self.purge.worker and self.purge.worker.is_alive():
                raise RuntimeError('Manual purge is running; retry when it finishes')
            current = policy_from(self.engine.settings)
            item = self.previews.get(token) if isinstance(token, str) else None
            if item and item['payload']['policy'] != proposed:
                raise ValueError('Preview does not match the proposed policy')
            if item and item['applied']:
                if item['payload']['policy'] == proposed and current == proposed:
                    return self.status()
                raise ValueError('Preview was already used for a different policy')
            if destructive_change(current, proposed):
                if confirmation != 'RETENTION' or not item or time.monotonic() - item['at'] > EXPIRES_SECONDS:
                    raise ValueError('A recent preview and typed RETENTION confirmation are required')
                preview = item['payload']
                if preview['policy'] != proposed or preview['current_policy'] != current:
                    raise ValueError('Policy changed since preview; preview again')
            if current == proposed:
                return self.status()
            self.engine.configure({'retention_hours': proposed['wifi_age_hours'],
                                   'ble_retention_hours': proposed['ble_age_hours'],
                                   'automatic_age_deletion': proposed['automatic_age_deletion'],
                                   'cleanup_interval_seconds': proposed['cleanup_interval_seconds'],
                                   'ble_max_records': proposed['ble_max_records']}, defer_cleanup=True)
            if item:
                item['applied'] = True
            self.worker = threading.Thread(target=self._run, name='wids-retention-apply', daemon=True)
            self.worker.start()
            return self.status()

    def _run(self):
        try:
            self.engine.run_retention('policy_save')
        except (sqlite3.Error, OSError):
            # The engine retains a bounded error and scheduled cleanup retries.
            pass
        finally:
            self.invalidate()

    def close(self):
        if self.worker:
            self.worker.join()
