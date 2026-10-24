from dataclasses import replace
import json
from fastapi.testclient import TestClient

from wids.engine import Engine
from wids.webapp import create_app


def test_database_ingestion_and_api(settings, frame):
    settings = replace(settings, deauth_threshold=3)
    engine = Engine(settings)
    for _ in range(4):
        assert engine.ingest(frame)
    heartbeat = {"v": 1, "kind": "heartbeat", "sensor_id": "sensor-1", "channel": 6,
                 "uptime_ms": 300, "dropped": 2}
    assert engine.ingest_line('WIDS ' + json.dumps(heartbeat))
    with TestClient(create_app(settings, engine)) as client:
        summary = client.get("/api/summary").json()
        assert summary["frames_24h"] == 4
        assert summary["alerts_24h"] == 1
        assert summary["sensors"] == 1
        assert client.get("/api/alerts").json()[0]["rule"] == "deauth_flood"
        assert client.get("/api/sensors").json()[0]["dropped"] == 2
        assert client.get("/api/channels").json()[0]["channel"] == 6
        assert "WiFi Sentinel" in client.get("/").text
        assert client.get("/api/frames?limit=999").status_code == 400
        assert client.get("/api/health").json()["serial_enabled"] is False


def test_demodata_produces_alerts(settings):
    from wids.cli import demo
    engine = Engine(settings)
    assert demo(engine) > 100
    assert engine.store.summary()["alerts_24h"] >= 3
    engine.store.close()


def test_wireline_rejects_invalid_json(settings):
    engine = Engine(settings)
    assert engine.ingest_line("I (123) wifi: init") is False
    assert engine.ingest_line("WIDS bad") is False
    engine.store.close()
