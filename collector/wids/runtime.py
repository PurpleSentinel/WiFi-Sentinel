"""Validated, persistent collector settings and the configuration write key."""
import json
import os
import secrets
from dataclasses import asdict, replace
from pathlib import Path

from .config import Settings
from .models import MAC
from .ssids import protected_name

LIMITS = {
    'window_seconds': (1, 3600), 'deauth_threshold': (1, 1000000),
    'disassoc_threshold': (1, 1000000), 'auth_threshold': (1, 1000000),
    'failed_auth_threshold': (1, 1000000), 'cooldown_seconds': (1, 86400),
    'retention_days': (1, 3650),
}
LISTS = ('monitored_bssids', 'protected_ssids', 'trusted_bssids')
RESTART_FIELDS = ('database', 'host', 'port', 'serial_port', 'baud')


def settings_path(settings: Settings) -> Path:
    return settings.database.with_suffix('.settings.json')


def validate_collector(values: dict) -> dict:
    if not isinstance(values, dict) or values.keys() - (LIMITS.keys() | set(LISTS)):
        raise ValueError('Unknown or restart-only collector setting')
    result = {}
    for name, value in values.items():
        if name in LIMITS:
            low, high = LIMITS[name]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{name} must be an integer in {low}..{high}')
        else:
            if not isinstance(value, list) or len(value) > 256:
                raise ValueError(f'{name} must be a list of up to 256 values')
            if any(not isinstance(v, str) for v in value):
                raise ValueError(f'{name} entries must be strings')
            if name == 'protected_ssids':
                for item in value:
                    protected_name(item)
            elif any(not MAC.fullmatch(v) for v in value):
                raise ValueError(f'{name} contains an invalid MAC address')
            value = tuple(v if name == 'protected_ssids' else v.lower() for v in value)
        result[name] = value
    return result


def load_settings(settings: Settings) -> Settings:
    path = settings_path(settings)
    if path.exists():
        return replace(settings, **validate_collector(json.loads(path.read_text())))
    return settings


def save_settings(settings: Settings) -> None:
    path = settings_path(settings)
    values = asdict(settings)
    data = {name: list(values[name]) if name in LISTS else values[name]
            for name in (*LIMITS, *LISTS)}
    validate_collector(data)
    # A unique temporary file avoids conflicting saves; replace is atomic.
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        with open(temp, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def configuration_key(settings: Settings) -> str:
    path = settings.database.with_suffix('.config-key')
    try:
        with open(path, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            key = secrets.token_urlsafe(32)
            stream.write(key + '\n')
    except FileExistsError:
        key = path.read_text().strip()
    if len(key) < 32:
        raise ValueError(f'Invalid configuration key file: {path}')
    return key
