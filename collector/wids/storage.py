"""SQLite storage for Wi-Fi metadata and bounded BLE advertising data."""
import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .detection import Alert
from .device_roles import EVIDENCE_LABELS, ROLE_QUERY, classification
from .models import Frame
from .ble_identity import identify


class Store:
    def __init__(self, filename: Path, retention_days: int = 7,
                 ble_retention_days: int = 7, ble_max_records: int = 100000,
                 retention_hours: int | None = None, ble_retention_hours: int | None = None,
                 automatic_age_deletion: bool = True):
        self.lock = threading.RLock()
        filename.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(filename), check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA busy_timeout=15000")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS ble_observations (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    address TEXT NOT NULL, address_type TEXT NOT NULL, rssi INTEGER NOT NULL,
                    payload_hex TEXT NOT NULL, event_type INTEGER NOT NULL, uptime_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_ble_ts ON ble_observations(timestamp);
                CREATE INDEX IF NOT EXISTS ix_ble_address ON ble_observations(address,address_type,timestamp);
                CREATE INDEX IF NOT EXISTS ix_ble_identity ON ble_observations(sensor_id,address,address_type,id DESC);
                CREATE TABLE IF NOT EXISTS ble_labels (
                    sensor_id TEXT NOT NULL,address TEXT NOT NULL,address_type TEXT NOT NULL,
                    alias TEXT NOT NULL,notes TEXT NOT NULL,updated_at TEXT NOT NULL,
                    PRIMARY KEY(sensor_id,address,address_type));
                CREATE TABLE IF NOT EXISTS ble_alerts (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    address TEXT NOT NULL, address_type TEXT NOT NULL, expression TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_ble_alert_ts ON ble_alerts(timestamp);
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    channel INTEGER NOT NULL, subtype TEXT NOT NULL, sa TEXT NOT NULL,
                    da TEXT NOT NULL, bssid TEXT NOT NULL, rssi INTEGER NOT NULL,
                    protected INTEGER NOT NULL, reason_code INTEGER, status_code INTEGER,
                    ssid TEXT, uptime_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_frames_ts ON frames(timestamp);
                CREATE INDEX IF NOT EXISTS ix_frames_rule ON frames(subtype, timestamp);
                CREATE INDEX IF NOT EXISTS ix_frames_sa ON frames(sa,timestamp);
                CREATE INDEX IF NOT EXISTS ix_frames_da ON frames(da,timestamp);
                CREATE INDEX IF NOT EXISTS ix_frames_bssid ON frames(bssid,timestamp);
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    rule TEXT NOT NULL, severity TEXT NOT NULL, bssid TEXT NOT NULL,
                    channel INTEGER NOT NULL, frame_count INTEGER NOT NULL, details TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_alerts_ts ON alerts(timestamp);
                CREATE TABLE IF NOT EXISTS sensors (
                    sensor_id TEXT PRIMARY KEY, last_seen TEXT NOT NULL, channel INTEGER,
                    uptime_ms INTEGER, dropped INTEGER DEFAULT 0, notes TEXT DEFAULT '');
            """)
            ble_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(ble_observations)')}
            if 'local_name' not in ble_columns:
                from .ble import decode_ad
                self.db.execute('ALTER TABLE ble_observations ADD COLUMN local_name TEXT')
                # One-time migration. Stream existing observations without copying the DB into memory.
                cursor = self.db.execute('SELECT id,payload_hex FROM ble_observations')
                while batch := cursor.fetchmany(500):
                    self.db.executemany('UPDATE ble_observations SET local_name=? WHERE id=?',
                        [(decode_ad(bytes.fromhex(row['payload_hex']))['local_name'], row['id']) for row in batch])
            self.db.execute("CREATE INDEX IF NOT EXISTS ix_ble_named ON ble_observations(sensor_id,address,address_type,id DESC) WHERE local_name IS NOT NULL AND local_name != ''")
            columns = {row['name'] for row in self.db.execute('PRAGMA table_info(alerts)')}
            if 'source_macs' not in columns:
                self.db.execute('ALTER TABLE alerts ADD COLUMN source_macs TEXT')
            frame_columns = {row['name'] for row in self.db.execute('PRAGMA table_info(frames)')}
            if 'ssid_hex' not in frame_columns:
                self.db.execute('ALTER TABLE frames ADD COLUMN ssid_hex TEXT')
            self.db.commit()
        self.ble_retention_days = ble_retention_days
        self.ble_max_records = ble_max_records
        self.retention_days = retention_days
        self.retention_hours = retention_hours
        self.ble_retention_hours = ble_retention_hours
        self.automatic_age_deletion = automatic_age_deletion
        self.ble_counts = {table: self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                           for table in ('ble_observations', 'ble_alerts')}
        self.startup_cleanup = self.cleanup()

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def add_frame(self, frame: Frame, alerts: list[Alert]) -> None:
        ts = self.timestamp()
        with self.lock, self.db:
            self.db.execute("""INSERT INTO frames
                (timestamp,sensor_id,channel,subtype,sa,da,bssid,rssi,protected,reason_code,status_code,ssid,uptime_ms,ssid_hex)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                ts, frame.sensor_id, frame.channel, frame.subtype, frame.sa, frame.da,
                frame.bssid, frame.rssi, int(frame.protected), frame.reason_code,
                frame.status_code, frame.ssid, frame.uptime_ms, frame.ssid_hex,
            ))
            for a in alerts:
                values = asdict(a)
                values['source_macs'] = json.dumps(a.source_macs) if a.source_macs is not None else None
                self.db.execute("""INSERT INTO alerts
                    (timestamp,sensor_id,rule,severity,bssid,channel,frame_count,details,source_macs)
                    VALUES (:timestamp,:sensor_id,:rule,:severity,:bssid,:channel,:frame_count,:details,:source_macs)""", values)
            self.db.execute("""INSERT INTO sensors (sensor_id,last_seen,channel,uptime_ms)
                VALUES (?,?,?,?) ON CONFLICT(sensor_id) DO UPDATE SET
                last_seen=excluded.last_seen,channel=excluded.channel,uptime_ms=excluded.uptime_ms""",
                (frame.sensor_id, ts, frame.channel, frame.uptime_ms))

    def heartbeat(self, sensor_id: str, channel: int, uptime_ms: int, dropped: int) -> None:
        with self.lock, self.db:
            self.db.execute("""INSERT INTO sensors (sensor_id,last_seen,channel,uptime_ms,dropped)
                VALUES (?,?,?,?,?) ON CONFLICT(sensor_id) DO UPDATE SET
                last_seen=excluded.last_seen,channel=excluded.channel,
                uptime_ms=excluded.uptime_ms,dropped=excluded.dropped""",
                (sensor_id, self.timestamp(), channel, uptime_ms, dropped))

    def rows(self, query: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            rows = [dict(row) for row in self.db.execute(query, params).fetchall()]
        for row in rows:
            if row.get('source_macs') is not None:
                row['source_macs'] = json.loads(row['source_macs'])
        return rows

    def alert_sources(self) -> dict:
        after = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat(timespec='seconds')
        rows = self.rows('''SELECT DISTINCT value AS mac FROM alerts,json_each(alerts.source_macs)
                            WHERE timestamp >= ? ORDER BY mac''', (after,))
        unknown = self.rows('SELECT COUNT(*) AS count FROM alerts WHERE timestamp >= ? AND source_macs IS NULL', (after,))[0]['count']
        ble_after = (datetime.now(timezone.utc) - timedelta(days=self.ble_retention_days)).isoformat(timespec='seconds')
        ble = self.rows('SELECT DISTINCT address AS mac FROM ble_alerts WHERE timestamp >= ?', (ble_after,))
        return {'macs': sorted({row['mac'] for row in rows + ble}), 'legacy_alerts_without_sources': unknown}

    def mac_details(self, mac: str) -> dict:
        after = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat(timespec='seconds')
        observed = self.rows('''SELECT COUNT(*) AS frame_count,MIN(timestamp) AS first_seen,
            MAX(timestamp) AS last_seen,MAX(sa=?) AS is_source,MAX(da=?) AS is_destination,
            MAX(bssid=?) AS is_bssid,
            json_group_array(DISTINCT CASE WHEN bssid=? AND subtype IN ('beacon','probe_resp')
                THEN ssid END) AS ssids,
            json_group_array(DISTINCT CASE WHEN bssid=? AND subtype IN ('beacon','probe_resp')
                THEN ssid_hex END) AS ssid_hex_values,
            json_group_array(DISTINCT bssid) AS bssids,
            json_group_array(DISTINCT channel) AS channels,
            json_group_array(DISTINCT sensor_id) AS sensor_ids
            FROM frames WHERE timestamp >= ? AND (sa=? OR da=? OR bssid=?)''',
            (mac, mac, mac, mac, mac, after, mac, mac, mac))[0]
        roles = [label for key, label in [('is_source', 'Source'), ('is_destination', 'Destination'),
                                         ('is_bssid', 'BSSID')] if observed.pop(key)]
        for name in ('ssids', 'ssid_hex_values', 'bssids', 'channels', 'sensor_ids'):
            observed[name] = sorted(value for value in json.loads(observed[name]) if value is not None and value != '')
        alerts = self.rows('''SELECT * FROM alerts WHERE timestamp >= ? AND
                            (bssid=? OR EXISTS (SELECT 1 FROM json_each(alerts.source_macs) WHERE value=?))
                            ORDER BY id DESC LIMIT 100''', (after, mac, mac))
        for alert in alerts:
            alert['association'] = 'Contributing source' if mac in (alert['source_macs'] or []) else 'BSSID context'
        recent = self._classified_devices(1, 'all', mac)
        return {**observed, 'roles': roles, 'alerts': alerts,
                'classification': {key: recent[0][key] for key in ('role_code', 'role', 'evidence', 'evidence_counts', 'window_hours')} if recent else classification()}

    def summary(self) -> dict:
        after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
        with self.lock:
            frames = self.db.execute("SELECT COUNT(*) FROM frames WHERE timestamp >= ?", (after,)).fetchone()[0]
            alerts = self.db.execute("SELECT COUNT(*) FROM alerts WHERE timestamp >= ?", (after,)).fetchone()[0]
            sensors = self.db.execute("SELECT COUNT(*) FROM sensors").fetchone()[0]
            by_subtype = [dict(r) for r in self.db.execute(
                "SELECT subtype,COUNT(*) count FROM frames WHERE timestamp >= ? GROUP BY subtype ORDER BY count DESC", (after,))]
        ble = self.rows('SELECT COUNT(*) AS count FROM ble_observations WHERE timestamp >= ?', (after,))[0]['count']
        ble_alerts = self.rows('SELECT COUNT(*) AS count FROM ble_alerts WHERE timestamp >= ?', (after,))[0]['count']
        unique_ble = self.rows('SELECT COUNT(DISTINCT address) AS count FROM ble_observations WHERE timestamp >= ?', (after,))[0]['count']
        hour_after = self.ble_window_start()
        hour = self.rows('SELECT COUNT(*) AS observations,COUNT(DISTINCT address) AS addresses FROM ble_observations WHERE timestamp >= ?', (hour_after,))[0]
        return {"frames_24h": frames, "alerts_24h": alerts + ble_alerts, "sensors": sensors,
                "by_subtype": by_subtype, 'ble_observations_24h': ble, 'ble_unique_addresses_24h': unique_ble,
                'ble_observations_1h': hour['observations'], 'ble_unique_addresses_1h': hour['addresses']}

    def age_cutoffs(self) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        wifi = now - timedelta(hours=self.retention_hours) if self.retention_hours is not None else now - timedelta(days=self.retention_days)
        ble = now - timedelta(hours=self.ble_retention_hours) if self.ble_retention_hours is not None else now - timedelta(days=self.ble_retention_days)
        return wifi.isoformat(timespec='seconds'), ble.isoformat(timespec='seconds')

    def cleanup(self) -> dict[str, int]:
        """Full startup/manual cleanup; scheduled work uses cleanup_batch instead."""
        before, ble_before = self.age_cutoffs()
        deleted = {}
        with self.lock, self.db:
            if self.automatic_age_deletion:
                for table, cutoff in [('ble_observations', ble_before), ('ble_alerts', ble_before),
                                      ('frames', before), ('alerts', before)]:
                    deleted[table] = self.db.execute(f'DELETE FROM {table} WHERE timestamp < ?', (cutoff,)).rowcount
            self.ble_counts = {table: self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                               for table in self.ble_counts}
            before_cap = dict(self.ble_counts)
            self._trim_ble()
            for table in before_cap:
                deleted[table] = deleted.get(table, 0) + before_cap[table] - self.ble_counts[table]
        return deleted

    def cleanup_batch(self, limit: int = 500) -> dict[str, int]:
        """One bounded pass through age and BLE count policies, then release SQLite."""
        before, ble_before = self.age_cutoffs()
        deleted = {table: 0 for table in ('frames', 'alerts', 'ble_observations', 'ble_alerts')}
        with self.lock, self.db:
            if self.automatic_age_deletion:
                for table, cutoff in [('ble_observations', ble_before), ('ble_alerts', ble_before),
                                      ('frames', before), ('alerts', before)]:
                    deleted[table] += self.db.execute(
                        f'DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE timestamp < ? ORDER BY timestamp LIMIT ?)',
                        (cutoff, limit)).rowcount
            for table in ('ble_observations', 'ble_alerts'):
                count = self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                excess = max(0, count - self.ble_max_records)
                if excess:
                    deleted[table] += self.db.execute(
                        f'DELETE FROM {table} WHERE id IN (SELECT id FROM {table} ORDER BY id LIMIT ?)',
                        (min(limit, excess),)).rowcount
                self.ble_counts[table] = count - min(limit, excess)
        return deleted

    def _classified_devices(self, limit: int, role: str, mac: str | None = None) -> list[dict]:
        after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
        rows = self.rows(ROLE_QUERY, (after, mac, mac, mac, mac, role, role, mac, mac, limit + 1))
        for row in rows:
            evidence = classification(row)
            row['observed_roles'] = [label for name, label in [('is_source', 'Source'),
                ('is_destination', 'Destination'), ('is_bssid', 'BSSID')] if row.pop(name)]
            row.pop('last_id')
            for name in EVIDENCE_LABELS:
                row.pop(name)
            row.update(evidence)
            for name in ('ssids', 'bssids', 'channels', 'sensor_ids'):
                row[name] = sorted(value for value in json.loads(row[name]) if value is not None and value != '')
        return rows

    def devices(self, limit: int = 200, role: str = 'all') -> dict:
        """Classify observed unicast roles by recent subtype/address evidence."""
        rows = self._classified_devices(limit, role)
        return {'window_hours': 24, 'limit': limit, 'role': role, 'has_more': len(rows) > limit,
                'devices': rows[:limit]}

    def _trim_ble(self):
        # Indexed primary-key cutoff bounds both tables, even under address churn.
        for table in ('ble_observations', 'ble_alerts'):
            if self.ble_counts[table] <= self.ble_max_records:
                continue
            # Trim a batch to avoid scanning 100k keys on every advertisement.
            target = self.ble_max_records - max(1, self.ble_max_records // 10)
            self.db.execute(f'DELETE FROM {table} WHERE id <= (SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?)',
                            (target,))
            self.ble_counts[table] = self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def add_ble(self, ad, accept, matches):
        ts = self.timestamp()
        with self.lock, self.db:
            if accept:
                self.db.execute('INSERT INTO ble_observations (timestamp,sensor_id,address,address_type,rssi,payload_hex,event_type,uptime_ms,local_name) VALUES (?,?,?,?,?,?,?,?,?)',
                                (ts, ad.sensor_id, ad.address, ad.address_type, ad.rssi, ad.payload_hex, ad.event_type, ad.uptime_ms, ad.decoded()['local_name']))
                self.ble_counts['ble_observations'] += 1
            for expression in matches:
                self.db.execute('INSERT INTO ble_alerts (timestamp,sensor_id,address,address_type,expression) VALUES (?,?,?,?,?)',
                                (ts, ad.sensor_id, ad.address, ad.address_type, expression))
                self.ble_counts['ble_alerts'] += 1
            self._trim_ble()

    @staticmethod
    def decode_ble(row):
        from .ble import decode_ad
        row.update(decode_ad(bytes.fromhex(row['payload_hex'])))
        return row

    def ble_observations(self, limit=100, address=None, address_type=None, sensor_id=None):
        return [self.decode_ble(row) for row in self.rows(
            'SELECT * FROM ble_observations WHERE (? IS NULL OR address=?) AND (? IS NULL OR address_type=?) AND (? IS NULL OR sensor_id=?) ORDER BY id DESC LIMIT ?',
            (address, address, address_type, address_type, sensor_id, sensor_id, limit))]

    @staticmethod
    def ble_window_start():
        return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec='seconds')

    def ble_devices(self, limit=200, query='', address_type='all', alert_only=False, sort='recent'):
        after = self.ble_window_start()
        alert_after = (datetime.now(timezone.utc) - timedelta(days=self.ble_retention_days)).isoformat(timespec='seconds')
        order = {'recent': 'o.id DESC', 'rssi': 'o.rssi DESC,o.id DESC',
                 'name': "COALESCE(NULLIF(l.alias,''),observed_name,o.address) COLLATE NOCASE,o.id DESC"}[sort]
        sql = '''WITH groups AS (SELECT sensor_id,address,address_type,COUNT(*) observation_count,
            MIN(timestamp) first_seen,MAX(timestamp) last_seen,MAX(id) latest_id
            FROM ble_observations WHERE timestamp >= ? GROUP BY sensor_id,address,address_type)
            SELECT o.*,g.observation_count,g.first_seen,g.last_seen,l.alias,l.notes,l.updated_at label_updated_at,
            (SELECT n.local_name FROM ble_observations n WHERE n.sensor_id=o.sensor_id AND n.address=o.address
             AND n.address_type=o.address_type AND n.timestamp>=? AND n.local_name IS NOT NULL AND n.local_name!=''
             ORDER BY n.id DESC LIMIT 1) observed_name,
            EXISTS(SELECT 1 FROM ble_alerts a WHERE a.sensor_id=o.sensor_id AND a.address=o.address
                AND a.address_type=o.address_type AND a.timestamp>=?) alert_associated
            FROM groups g JOIN ble_observations o ON o.id=g.latest_id
            LEFT JOIN ble_labels l ON l.sensor_id=o.sensor_id AND l.address=o.address AND l.address_type=o.address_type
            WHERE (?='all' OR o.address_type=?) AND (?=0 OR EXISTS(SELECT 1 FROM ble_alerts a
                WHERE a.sensor_id=o.sensor_id AND a.address=o.address AND a.address_type=o.address_type AND a.timestamp>=?))
            ORDER BY ''' + order
        result = []
        with self.lock:
            total = self.db.execute('SELECT COUNT(*) FROM (SELECT 1 FROM ble_observations WHERE timestamp>=? GROUP BY sensor_id,address,address_type)', (after,)).fetchone()[0]
            cursor = self.db.execute(sql, (after, after, alert_after, address_type, address_type, int(alert_only), alert_after))
            # Stream candidates; filters apply before the result cap, without unbounded result memory.
            for record in cursor:
                row = identify(self.decode_ble(dict(record)))
                searchable = ' '.join(str(row.get(key) or '') for key in
                    ('display_label','alias','notes','address','sensor_id','advertised_name','address_type','address_subtype','category'))
                searchable += ' ' + json.dumps(row['company_details'] + row['service_details'], ensure_ascii=False)
                if query.casefold() not in searchable.casefold():
                    continue
                result.append(row)
                if len(result) > limit:
                    break
        return {'devices': result[:limit], 'has_more': len(result)>limit, 'window_hours': 1,
                'total_identities': total, 'limit': limit, 'query': query,
                'note': 'Sensor/address/type identities, not unique physical devices; private addresses rotate.'}

    def ble_label(self, sensor_id, address, address_type):
        rows = self.rows('SELECT * FROM ble_labels WHERE sensor_id=? AND address=? AND address_type=?',
                         (sensor_id,address,address_type))
        return rows[0] if rows else {'alias':'','notes':''}

    def save_ble_label(self, sensor_id, address, address_type, alias, notes):
        with self.lock, self.db:
            if not alias and not notes:
                self.db.execute('DELETE FROM ble_labels WHERE sensor_id=? AND address=? AND address_type=?',
                                (sensor_id,address,address_type))
            else:
                exists = self.db.execute('SELECT 1 FROM ble_labels WHERE sensor_id=? AND address=? AND address_type=?',
                                         (sensor_id,address,address_type)).fetchone()
                if not exists and self.db.execute('SELECT COUNT(*) FROM ble_labels').fetchone()[0] >= 1024:
                    raise ValueError('Maximum 1024 BLE labels; clear an unused label first')
                self.db.execute('''INSERT INTO ble_labels VALUES (?,?,?,?,?,?) ON CONFLICT(sensor_id,address,address_type)
                    DO UPDATE SET alias=excluded.alias,notes=excluded.notes,updated_at=excluded.updated_at''',
                    (sensor_id,address,address_type,alias,notes,self.timestamp()))
        return self.ble_label(sensor_id,address,address_type)

    def all_alerts(self, limit=100):
        return self.rows('''SELECT id,timestamp,sensor_id,rule,severity,bssid,channel,frame_count,details,source_macs,
            'wifi' protocol,NULL address_type FROM alerts UNION ALL
            SELECT id,timestamp,sensor_id,'ble_match' rule,'medium' severity,NULL bssid,NULL channel,1 frame_count,
            'BLE advertisement matched ' || expression details,json_array(address) source_macs,'ble' protocol,address_type
            FROM ble_alerts ORDER BY timestamp DESC,id DESC LIMIT ?''', (limit,))

    def close(self) -> None:
        with self.lock:
            self.db.close()
