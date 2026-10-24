"""Single-process, thread-safe SQLite storage. No raw payloads or PCAPs."""
import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .detection import Alert
from .device_roles import EVIDENCE_LABELS, ROLE_QUERY, classification
from .models import Frame


class Store:
    def __init__(self, filename: Path, retention_days: int = 7):
        self.lock = threading.RLock()
        filename.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(filename), check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA busy_timeout=15000")
            self.db.executescript("""
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
            columns = {row['name'] for row in self.db.execute('PRAGMA table_info(alerts)')}
            if 'source_macs' not in columns:
                self.db.execute('ALTER TABLE alerts ADD COLUMN source_macs TEXT')
            self.db.commit()
        self.retention_days = retention_days
        self.cleanup()

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def add_frame(self, frame: Frame, alerts: list[Alert]) -> None:
        ts = self.timestamp()
        with self.lock, self.db:
            self.db.execute("""INSERT INTO frames
                (timestamp,sensor_id,channel,subtype,sa,da,bssid,rssi,protected,reason_code,status_code,ssid,uptime_ms)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                ts, frame.sensor_id, frame.channel, frame.subtype, frame.sa, frame.da,
                frame.bssid, frame.rssi, int(frame.protected), frame.reason_code,
                frame.status_code, frame.ssid, frame.uptime_ms,
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
        return {'macs': [row['mac'] for row in rows], 'legacy_alerts_without_sources': unknown}

    def mac_details(self, mac: str) -> dict:
        after = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat(timespec='seconds')
        observed = self.rows('''SELECT COUNT(*) AS frame_count,MIN(timestamp) AS first_seen,
            MAX(timestamp) AS last_seen,MAX(sa=?) AS is_source,MAX(da=?) AS is_destination,
            MAX(bssid=?) AS is_bssid,
            json_group_array(DISTINCT CASE WHEN bssid=? AND subtype IN ('beacon','probe_resp')
                THEN ssid END) AS ssids,
            json_group_array(DISTINCT bssid) AS bssids,
            json_group_array(DISTINCT channel) AS channels,
            json_group_array(DISTINCT sensor_id) AS sensor_ids
            FROM frames WHERE timestamp >= ? AND (sa=? OR da=? OR bssid=?)''',
            (mac, mac, mac, mac, after, mac, mac, mac))[0]
        roles = [label for key, label in [('is_source', 'Source'), ('is_destination', 'Destination'),
                                         ('is_bssid', 'BSSID')] if observed.pop(key)]
        for name in ('ssids', 'bssids', 'channels', 'sensor_ids'):
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
        return {"frames_24h": frames, "alerts_24h": alerts, "sensors": sensors, "by_subtype": by_subtype}

    def cleanup(self) -> None:
        before = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat(timespec="seconds")
        with self.lock, self.db:
            self.db.execute("DELETE FROM frames WHERE timestamp < ?", (before,))
            self.db.execute("DELETE FROM alerts WHERE timestamp < ?", (before,))

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

    def close(self) -> None:
        with self.lock:
            self.db.close()
