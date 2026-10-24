from dataclasses import replace
import pytest

from wids.config import Settings


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k in list(__import__('os').environ):
        if k.startswith('WIDS_'):
            monkeypatch.delenv(k)
    return replace(Settings.from_env(), database=tmp_path / 'test.sqlite3')


@pytest.fixture
def frame():
    return {"v": 1, "kind": "frame", "sensor_id": "sensor-1", "channel": 6,
            "subtype": "deauth", "sa": "02:aa:bb:cc:dd:ee", "da": "ff:ff:ff:ff:ff:ff",
            "bssid": "02:11:22:33:44:55", "rssi": -51, "protected": False,
            "reason_code": 7, "status_code": -1, "ssid": None, "uptime_ms": 200}
