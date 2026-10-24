"""Single-process, thread-safe SQLite storage. No raw payloads or PCAPs."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import threading

from .detection import Alert
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
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    rule TEXT NOT NULL, severity TEXT NOT NULL, bssid TEXT NOT NULL,
                    channel INTEGER NOT NULL, frame_count INTEGER NOT NULL, details TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS ix_alerts_ts ON alerts(timestamp);
                CREATE TABLE IF NOT EXISTS sensors (
                    sensor_id TEXT PRIMARY KEY, last_seen TEXT NOT NULL, channel INTEGER,
                    uptime_ms INTEGER, dropped INTEGER DEFAULT 0, notes TEXT DEFAULT '');
            """)
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
                self.db.execute("""INSERT INTO alerts
                    (timestamp,sensor_id,rule,severity,bssid,channel,frame_count,details)
                    VALUES (:timestamp,:sensor_id,:rule,:severity,:bssid,:channel,:frame_count,:details)""", asdict(a))
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
            return [dict(row) for row in self.db.execute(query, params).fetchall()]

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

    def close(self) -> None:
        with self.lock:
            self.db.close()
