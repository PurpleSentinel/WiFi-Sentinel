"""Explicit, environment-driven collector configuration; no runtime secrets."""
from dataclasses import dataclass
import os
from pathlib import Path


def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip())


def _integer(name: str, default: int, low: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < low:
        raise ValueError(f"{name} must be >= {low}")
    return value


@dataclass(frozen=True)
class Settings:
    database: Path
    host: str
    port: int
    serial_port: str | None
    baud: int
    window_seconds: int
    deauth_threshold: int
    disassoc_threshold: int
    auth_threshold: int
    failed_auth_threshold: int
    cooldown_seconds: int
    retention_days: int
    monitored_bssids: tuple[str, ...]
    protected_ssids: tuple[str, ...]
    trusted_bssids: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        raw_serial = os.getenv("WIDS_SERIAL_PORT", "").strip()
        return cls(
            database=Path(os.getenv("WIDS_DATABASE", "./sentinel.sqlite3")).expanduser(),
            host=os.getenv("WIDS_HOST", "127.0.0.1"),
            port=_integer("WIDS_PORT", 8080),
            serial_port=raw_serial or None,
            baud=_integer("WIDS_BAUD", 115200),
            window_seconds=_integer("WIDS_WINDOW_SECONDS", 10),
            deauth_threshold=_integer("WIDS_DEAUTH_THRESHOLD", 20),
            disassoc_threshold=_integer("WIDS_DISASSOC_THRESHOLD", 20),
            auth_threshold=_integer("WIDS_AUTH_THRESHOLD", 40),
            failed_auth_threshold=_integer("WIDS_FAILED_AUTH_THRESHOLD", 12),
            cooldown_seconds=_integer("WIDS_COOLDOWN_SECONDS", 60),
            retention_days=_integer("WIDS_RETENTION_DAYS", 7),
            monitored_bssids=_csv_env("WIDS_MONITORED_BSSIDS"),
            protected_ssids=_csv_env("WIDS_PROTECTED_SSIDS"),
            trusted_bssids=_csv_env("WIDS_TRUSTED_BSSIDS"),
        )
