"""Explicit, key-authorized age purges; previews never write capture data."""
import copy
import logging
import math
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timedelta, timezone

TABLES = ('frames', 'alerts', 'ble_observations', 'ble_alerts')
LOG = logging.getLogger(__name__)
PREVIEW_SECONDS = 600
BATCH_ROWS = 500


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_ages(ages):
    if not isinstance(ages, dict) or not ages or set(ages) - set(TABLES):
        raise ValueError('Select one or more supported historical data categories')
    values = {}
    for table, age in ages.items():
        if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or not 0 < age <= 876000:
            raise ValueError('Retention ages must be positive hours, at most 36,500 days')
        values[table] = float(age)
    return values


class PurgeManager:
    def __init__(self, engine, invalidate):
        self.engine, self.invalidate = engine, invalidate
        self.lock = threading.RLock()
        self.previews = OrderedDict()
        self.jobs = OrderedDict()
        self.worker = None
        self.stop = threading.Event()

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join()

    def status(self):
        with self.lock:
            return copy.deepcopy(next(reversed(self.jobs.values()), None))

    def preview(self, ages):
        ages = validate_ages(ages)
        now = datetime.now(timezone.utc)
        cutoffs = {table: (now - timedelta(hours=age)).isoformat(timespec='seconds') for table, age in ages.items()}
        counts = {}
        path = self.engine.settings.database.resolve()
        # No Store construction: no cleanup, migrations or writes on preview.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.1)) as db:
            deadline = time.monotonic() + 1
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for table, cutoff in cutoffs.items():
                eligible = db.execute(f'SELECT COUNT(*) FROM {table} WHERE timestamp < ?', (cutoff,)).fetchone()[0]
                total = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                counts[table] = {'eligible': eligible, 'remaining': total - eligible, 'total': total}
        preview = {'token': secrets.token_urlsafe(24), 'created_at': utc_now(), 'ages_hours': ages,
                   'cutoffs': cutoffs, 'counts': counts, 'expires_in_seconds': PREVIEW_SECONDS}
        with self.lock:
            for token, item in list(self.previews.items()):
                if time.monotonic() - item['monotonic'] > PREVIEW_SECONDS:
                    del self.previews[token]
            self.previews[preview['token']] = {'preview': preview, 'monotonic': time.monotonic(), 'job': None}
            while len(self.previews) > 32:
                self.previews.popitem(last=False)
        return copy.deepcopy(preview)

    def start(self, token, confirmation):
        if confirmation != 'PURGE' or not isinstance(token, str):
            raise ValueError('Type PURGE and supply a valid preview token')
        with self.lock:
            item = self.previews.get(token)
            if item is None or time.monotonic() - item['monotonic'] > PREVIEW_SECONDS:
                raise ValueError('Preview expired or unavailable; preview again')
            if item['job']:
                if item['job'] not in self.jobs:
                    raise ValueError('Operation summary expired; preview again')
                return copy.deepcopy(self.jobs[item['job']])
            if self.worker and self.worker.is_alive():
                raise RuntimeError('Another purge is running')
            preview = item['preview']
            if not any(row['eligible'] for row in preview['counts'].values()):
                raise ValueError('No matching records; nothing to purge')
            job = {'id': secrets.token_urlsafe(18), 'state': 'running', 'started_at': utc_now(),
                   'finished_at': None, 'cutoffs': copy.deepcopy(preview['cutoffs']),
                   'preview_counts': copy.deepcopy(preview['counts']),
                   'deleted': {table: 0 for table in preview['cutoffs']}, 'error': None,
                   'cancel_requested': False}
            self.jobs[job['id']] = job
            item['job'] = job['id']
            while len(self.jobs) > 20:
                self.jobs.popitem(last=False)
            self.worker = threading.Thread(target=self._run, args=(job,), name='wids-purge', daemon=True)
            self.worker.start()
            return copy.deepcopy(job)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise ValueError('Unknown purge operation')
            if job['state'] == 'running':
                job['cancel_requested'] = True
            return copy.deepcopy(job)

    def _batch(self, db, table, cutoff):
        # Share pipeline ordering and update the Store's BLE cap accounting atomically.
        if not self.engine.lock.acquire(timeout=0.5):
            raise RuntimeError('Collector busy; retry with a new preview')
        try:
            if not self.engine.store.lock.acquire(timeout=0.5):
                raise RuntimeError('Database busy; retry with a new preview')
            try:
                deadline = time.monotonic() + 0.2
                db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                with db:
                    count = db.execute(f'DELETE FROM {table} WHERE id IN '
                                       f'(SELECT id FROM {table} WHERE timestamp < ? ORDER BY timestamp LIMIT ?)',
                                       (cutoff, BATCH_ROWS)).rowcount
                if table in self.engine.store.ble_counts:
                    self.engine.store.ble_counts[table] = max(0, self.engine.store.ble_counts[table] - count)
                return count
            finally:
                self.engine.store.lock.release()
        finally:
            self.engine.lock.release()

    def _run(self, job):
        db = None
        try:
            db = sqlite3.connect(self.engine.settings.database.resolve().as_uri() + '?mode=rw', uri=True, timeout=0.1)
            for table, cutoff in job['cutoffs'].items():
                while True:
                    with self.lock:
                        cancelled = job['cancel_requested'] or self.stop.is_set()
                    if cancelled:
                        with self.lock:
                            job['state'] = 'cancelled'
                        return
                    count = self._batch(db, table, cutoff)
                    with self.lock:
                        job['deleted'][table] += count
                    if count < BATCH_ROWS:
                        break
                    self.stop.wait(0.02)  # Yield between committed batches for ingestion/retention.
            with self.lock:
                job['state'] = 'completed'
        except (sqlite3.Error, OSError, RuntimeError) as exc:
            with self.lock:
                job['state'] = 'failed'
                job['error'] = f'{type(exc).__name__}: {str(exc)[:180]}; committed batches remain deleted'
        finally:
            if db is not None:
                db.close()
            self.invalidate()
            with self.lock:
                job['finished_at'] = utc_now()
                summary = {key: copy.deepcopy(job[key]) for key in ('id', 'state', 'cutoffs', 'deleted', 'started_at', 'finished_at', 'error')}
            LOG.info('Data purge summary: %s', summary)
