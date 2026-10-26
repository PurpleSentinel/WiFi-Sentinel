"""Unprivileged host probes and bounded, read-only database inspection on demand."""
import copy
import os
import platform
import shutil
import socket
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

DATABASE_CACHE_SECONDS = 15
DATABASE_QUERY_SECONDS = 0.3
TABLE_TIMESTAMPS = {'frames': 'timestamp', 'alerts': 'timestamp',
                    'ble_observations': 'timestamp', 'ble_alerts': 'timestamp',
                    'sensors': 'last_seen', 'ble_labels': 'updated_at'}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_text(path, limit=65536):
    try:
        with Path(path).open(encoding='utf-8', errors='replace') as stream:
            return stream.read(limit)
    except (OSError, ValueError):
        return None


def keyed_bytes(text):
    result = {}
    for line in (text or '').splitlines():
        key, separator, value = line.partition(':')
        parts = value.split()
        if separator and parts and parts[0].isdigit():
            result[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1].lower() == 'kb' else 1)
    return result


def memory_metrics(text):
    values = keyed_bytes(text)
    total, available = values.get('MemTotal'), values.get('MemAvailable')
    swap, swap_free = values.get('SwapTotal'), values.get('SwapFree')
    used = max(0, total - available) if total is not None and available is not None else None
    return {'total_bytes': total, 'available_bytes': available, 'used_bytes': used,
            'used_percent': used / total * 100 if used is not None and total else None,
            'swap_total_bytes': swap, 'swap_free_bytes': swap_free,
            'swap_used_bytes': max(0, swap - swap_free) if swap is not None and swap_free is not None else None}


def cpu_ticks(text):
    try:
        parts = (text or '').splitlines()[0].split()
        if parts[0] != 'cpu' or len(parts) < 5:
            return None
        values = [int(value) for value in parts[1:9]]  # guest time is already included in user/nice.
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    except (IndexError, ValueError):
        return None


def cpu_percent(previous, current):
    if previous is None or current is None:
        return None
    total, idle = current[0] - previous[0], current[1] - previous[1]
    if total <= 0 or idle < 0:
        return None
    return max(0, min(100, 100 * (total - idle) / total))


def temperature_metrics():
    # Only CPU/SoC thermal zones, not arbitrary battery/peripheral temperatures.
    for index in range(16):
        zone = Path('/sys/class/thermal') / f'thermal_zone{index}'
        kind = (read_text(zone / 'type') or '').strip()
        if not any(token in kind.lower() for token in ('cpu', 'soc', 'package', 'x86_pkg')):
            continue
        try:
            value = float((read_text(zone / 'temp') or '').strip()) / 1000
            if -30 <= value <= 150:
                return {'celsius': value, 'source': kind}
        except ValueError:
            pass
    return {'celsius': None, 'source': None}


def file_metrics(path):
    try:
        stat = path.stat()
        return {'path': str(path), 'present': True, 'bytes': stat.st_size, 'error': None}
    except FileNotFoundError:
        return {'path': str(path), 'present': False, 'bytes': 0, 'error': None}
    except OSError as exc:
        return {'path': str(path), 'present': None, 'bytes': None, 'error': type(exc).__name__}


def database_files(path):
    files = {name: file_metrics(Path(str(path) + suffix)) for name, suffix in
             [('main', ''), ('wal', '-wal'), ('shm', '-shm')]}
    sizes = [info['bytes'] for info in files.values()]
    return {'files': files, 'total_bytes': sum(sizes) if all(value is not None for value in sizes) else None}


def inspect_database(path, tables=None, budget=DATABASE_QUERY_SECONDS):
    """Never uses the ingest connection, creates files, checkpoints or scans row payloads."""
    path = Path(path).resolve()
    result = {'path': str(path), 'sqlite_version': sqlite3.sqlite_version, 'collected_at': utc_now(),
              'read_only': True, 'query_budget_seconds': budget, 'tables': [], 'error': None,
              'journal_mode': None, 'page_size': None, 'page_count': None, 'free_pages': None,
              'allocated_bytes': None, 'free_page_bytes': None, 'schema_change_counter': None,
              'application_schema_version': None}
    connection = None
    try:
        if not path.is_file():
            raise FileNotFoundError('Database file is absent')
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=min(budget, 0.1))
        connection.row_factory = sqlite3.Row
        deadline = time.monotonic() + budget
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        for field, pragma in [('journal_mode', 'journal_mode'), ('page_size', 'page_size'),
                              ('page_count', 'page_count'), ('free_pages', 'freelist_count'),
                              ('schema_change_counter', 'schema_version'), ('application_schema_version', 'user_version')]:
            value = connection.execute('PRAGMA ' + pragma).fetchone()[0]
            result[field] = None if field == 'application_schema_version' and value == 0 else value
        result['allocated_bytes'] = result['page_size'] * result['page_count']
        result['free_page_bytes'] = result['page_size'] * result['free_pages']
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, timestamp in (tables if tables is not None else TABLE_TIMESTAMPS).items():
            if time.monotonic() >= deadline:
                raise sqlite3.OperationalError('interrupted')
            row = {'name': table, 'present': table in existing, 'row_count': None,
                   'oldest_timestamp': None, 'newest_timestamp': None, 'timestamp_field': timestamp, 'columns': []}
            result['tables'].append(row)
            if table not in existing:
                continue
            # Identifiers come only from the fixed internal table definitions above.
            row['columns'] = [{'name': item['name'], 'type': item['type'], 'primary_key': bool(item['pk'])}
                              for item in connection.execute(f'PRAGMA table_info("{table}")')]
            row['row_count'] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if timestamp in {item['name'] for item in row['columns']}:
                row['oldest_timestamp'] = connection.execute(f'SELECT MIN("{timestamp}") FROM "{table}"').fetchone()[0]
                row['newest_timestamp'] = connection.execute(f'SELECT MAX("{timestamp}") FROM "{table}"').fetchone()[0]
    except (OSError, sqlite3.Error) as exc:
        result['error'] = ('Database query time budget exceeded; partial metrics shown'
                           if isinstance(exc, sqlite3.OperationalError) and 'interrupted' in str(exc)
                           else f'{type(exc).__name__}: {str(exc)[:180]}')
    finally:
        if connection is not None:
            connection.close()  # End the read transaction; no checkpoint/maintenance commands.
    return result


class SystemMetrics:
    def __init__(self):
        self.started_at = utc_now()
        self.started_monotonic = time.monotonic()
        self.previous_cpu = None
        self.database_cache = None
        self.database_sample_time = float('-inf')
        self.lock = threading.Lock()

    def invalidate(self):
        with self.lock:
            self.database_sample_time = float("-inf")

    def host(self, database):
        now, process_cpu = time.monotonic(), time.process_time()
        ticks = cpu_ticks(read_text('/proc/stat'))
        previous = self.previous_cpu
        elapsed = now - previous[0] if previous else None
        host_cpu = process_percent = None
        if elapsed is not None and elapsed >= 0.5:
            host_cpu = cpu_percent(previous[1], ticks)
            process_percent = max(0, (process_cpu - previous[2]) / elapsed * 100)
        if previous is None or elapsed >= 0.5:
            self.previous_cpu = (now, ticks, process_cpu)
        cpuinfo = read_text('/proc/cpuinfo') or ''
        cpu_model = next((line.partition(':')[2].strip() for line in cpuinfo.splitlines()
                          if line.partition(':')[0].strip().lower() == 'model name'), None)
        model = next((value.strip('\x00\n ') for value in
                      [read_text('/proc/device-tree/model'), read_text('/sys/firmware/devicetree/base/model'),
                       read_text('/sys/devices/virtual/dmi/id/product_name')] if value), None)
        os_values = {}
        for line in (read_text('/etc/os-release') or '').splitlines():
            key, separator, value = line.partition('=')
            if separator:
                os_values[key] = value.strip('"')
        try:
            load = list(os.getloadavg())
        except (AttributeError, OSError):
            load = None
        try:
            uptime = float((read_text('/proc/uptime') or '').split()[0])
        except (ValueError, IndexError):
            uptime = None
        process = keyed_bytes(read_text('/proc/self/status'))
        disk = {'path': str(database.parent), 'total_bytes': None, 'used_bytes': None, 'free_bytes': None,
                'used_percent': None, 'error': None}
        try:
            usage = shutil.disk_usage(database.parent)
            disk.update(total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free,
                        used_percent=usage.used / usage.total * 100 if usage.total else None)
        except OSError as exc:
            disk['error'] = type(exc).__name__
        return {'hostname': socket.gethostname(), 'hardware_model': model,
                'os': os_values.get('PRETTY_NAME') or platform.system(), 'kernel': platform.release(),
                'architecture': platform.machine(), 'cpu_model': cpu_model, 'logical_cpus': os.cpu_count(),
                'cpu_utilization_percent': host_cpu, 'cpu_sample_interval_seconds': elapsed,
                'cpu_note': 'Average since previous System sample; first/sub-0.5s sample unavailable',
                'load_averages_1_5_15_minutes': load, 'temperature': temperature_metrics(),
                'memory': memory_metrics(read_text('/proc/meminfo')), 'uptime_seconds': uptime,
                'collector_started_at': self.started_at, 'collector_uptime_seconds': max(0, now - self.started_monotonic),
                'application_version': __version__, 'process_rss_bytes': process.get('VmRSS'),
                'process_threads': process.get('Threads'), 'process_cpu_percent_one_core': process_percent,
                'disk': disk}

    def snapshot(self, settings, sensor):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('System metrics collection already in progress; retry shortly')
        try:
            path = settings.database.expanduser().resolve()
            now = time.monotonic()
            cached = self.database_cache is not None and now - self.database_sample_time < DATABASE_CACHE_SECONDS
            if not cached:
                self.database_cache = {
                    'capture': inspect_database(path),
                    'vendor_cache': inspect_database(path.with_suffix('.vendors.sqlite3'), {'vendors': 'checked_at'}, budget=0.1)}
                self.database_sample_time = time.monotonic()
            databases = copy.deepcopy(self.database_cache)
            for name, filename in [('capture', path), ('vendor_cache', path.with_suffix('.vendors.sqlite3'))]:
                databases[name].update(database_files(filename))
            return {'collected_at': utc_now(), 'host': self.host(path), 'databases': databases,
                    'database_cache': {'reused': cached, 'age_seconds': max(0, time.monotonic() - self.database_sample_time),
                                       'ttl_seconds': DATABASE_CACHE_SECONDS},
                    'policy': {'wifi_retention_days': settings.retention_days, 'ble_retention_days': settings.ble_retention_days,
                               'ble_max_records_per_table': settings.ble_max_records, 'ble_display_window_hours': 1,
                               'cleanup_interval_seconds': 60},
                    'collector': {'serial_enabled': bool(settings.serial_port), 'sensor_connected': sensor['connected']},
                    'notes': ['Read-only snapshots; no database maintenance or sensor commands.',
                              'Filesystem sizes and SQL metrics are sampled separately and may differ during writes.',
                              'Unavailable host probes are reported as null. Process CPU: 100% is one logical core.']}
        finally:
            self.lock.release()
