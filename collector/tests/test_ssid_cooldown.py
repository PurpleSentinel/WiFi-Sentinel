from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from wids.detection import Detector
from wids.engine import Engine
from wids.models import Frame
from wids.webapp import create_app


@pytest.mark.parametrize('subtype', ['beacon', 'probe_resp'])
def test_protected_ssid_repeats_at_cooldown_boundary(settings, frame, subtype):
    detector = Detector(replace(settings, protected_ssids=('Café',), cooldown_seconds=17))
    observed = Frame.from_json({**frame, 'subtype': subtype, 'ssid_hex': '436166c3a9'})
    assert len(detector.observe(observed, now=0)) == 1
    assert detector.observe(observed, now=0.1) == []
    assert detector.observe(observed, now=16.999) == []
    repeated = detector.observe(observed, now=17)
    assert len(repeated) == 1
    assert repeated[0].rule == 'protected_ssid_untrusted_bssid'
    assert repeated[0].source_macs == (observed.sa,)
    assert len(detector.observe(observed, now=34)) == 1


def test_probe_beacon_and_protected_names_share_documented_bssid_cooldown(settings, frame):
    detector = Detector(replace(settings, protected_ssids=('Office', 'Guest')))
    beacon = Frame.from_json({**frame, 'subtype': 'beacon', 'ssid': 'Office'})
    assert len(detector.observe(beacon, now=0)) == 1
    assert detector.observe(replace(beacon, subtype='probe_resp', ssid='Guest'), now=10) == []
    repeated = detector.observe(replace(beacon, subtype='probe_resp', ssid='Guest'), now=60)
    assert len(repeated) == 1
    assert 'Guest' in repeated[0].details


def test_channel_and_sensor_cooldowns_are_independent(settings, frame):
    detector = Detector(replace(settings, protected_ssids=('Office',)))
    beacon = Frame.from_json({**frame, 'subtype': 'beacon', 'ssid': 'Office'})
    assert len(detector.observe(beacon, now=0)) == 1
    assert len(detector.observe(replace(beacon, channel=11), now=1)) == 1
    assert len(detector.observe(replace(beacon, sensor_id='other'), now=2)) == 1
    assert detector.observe(beacon, now=3) == []  # Returning to channel 6 retains its cooldown.
    assert len(detector.observe(beacon, now=60)) == 1


def test_returning_ap_can_alert_after_long_absence_and_pruning(settings, frame):
    detector = Detector(replace(settings, protected_ssids=('Office',)))
    beacon = Frame.from_json({**frame, 'subtype': 'beacon', 'ssid': 'Office'})
    assert len(detector.observe(beacon, now=0)) == 1
    detector._prune(4000)
    assert len(detector.observe(beacon, now=4001)) == 1


def test_repeat_alerts_persist_without_process_restart_or_monitored_bssid_match(settings, frame):
    config = replace(settings, protected_ssids=('Office',), monitored_bssids=('00:00:00:00:00:01',))
    engine = Engine(config)
    clock = [0]
    observe = engine.detector.observe
    engine.detector.observe = lambda observed: observe(observed, now=clock[0])
    beacon = {**frame, 'subtype': 'beacon', 'ssid': 'Office'}
    engine.ingest(beacon)
    clock[0] = 30
    engine.ingest(beacon)
    clock[0] = 120
    engine.ingest(beacon)
    with TestClient(create_app(config, engine)) as client:
        alerts = client.get('/api/alerts').json()
        assert len(alerts) == 2
        assert all(alert['rule'] == 'protected_ssid_untrusted_bssid' for alert in alerts)
        assert all(alert['source_macs'] == [frame['sa']] for alert in alerts)
        with engine.store.db:
            engine.store.db.execute("UPDATE alerts SET timestamp='2000-01-01T00:00:00+00:00'")
        engine.store.cleanup()
        assert client.get('/api/alerts').json() == []
        clock[0] = 4001
        engine.ingest(beacon)
        assert len(client.get('/api/alerts').json()) == 1


def test_repeat_detection_still_excludes_trusted_and_unprotected_ssids(settings, frame):
    detector = Detector(replace(settings, protected_ssids=('Office',), trusted_bssids=(frame['bssid'],)))
    trusted = Frame.from_json({**frame, 'subtype': 'beacon', 'ssid': 'Office'})
    other_name = replace(trusted, bssid='00:11:22:33:44:66', ssid='Unprotected')
    for timestamp in (0, 60, 120, 4001):
        assert detector.observe(trusted, now=timestamp) == []
        assert detector.observe(other_name, now=timestamp) == []
    assert detector.last_alert == {}
