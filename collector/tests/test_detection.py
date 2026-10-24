from dataclasses import replace
from wids.detection import Detector
from wids.models import Frame


def test_deauth_flood_and_cooldown(settings, frame):
    config = replace(settings, deauth_threshold=3, cooldown_seconds=30)
    detector = Detector(config)
    events = []
    for t in [10, 11, 12, 13, 14]:
        events += detector.observe(Frame.from_json(frame), now=t)
    assert len(events) == 1
    assert events[0].rule == "deauth_flood"
    assert events[0].frame_count == 3
    assert events[0].severity == "high"


def test_window_expires(settings, frame):
    detector = Detector(replace(settings, deauth_threshold=3, window_seconds=5))
    assert detector.observe(Frame.from_json(frame), now=0) == []
    assert detector.observe(Frame.from_json(frame), now=10) == []
    assert detector.observe(Frame.from_json(frame), now=20) == []


def test_monitored_bssid_filter(settings, frame):
    detector = Detector(replace(settings, monitored_bssids=("02:00:00:00:00:01",), deauth_threshold=1))
    assert detector.observe(Frame.from_json(frame), now=1) == []


def test_failed_authentication_status(settings, frame):
    detector = Detector(replace(settings, failed_auth_threshold=2, auth_threshold=99))
    frame["subtype"] = "auth"
    frame["status_code"] = 1
    assert detector.observe(Frame.from_json(frame), now=1) == []
    found = detector.observe(Frame.from_json(frame), now=2)
    assert len(found) == 1 and found[0].rule == "failed_auth_burst"


def test_protected_ssid_unknown_bssid(settings, frame):
    config = replace(settings, protected_ssids=("examplelab",), trusted_bssids=("02:00:00:00:00:01",))
    detector = Detector(config)
    frame.update(subtype="beacon", ssid="ExampleLab")
    seen = detector.observe(Frame.from_json(frame), now=1)
    assert len(seen) == 1 and seen[0].rule == "protected_ssid_untrusted_bssid"
    assert detector.observe(Frame.from_json(frame), now=2) == []


def test_trusted_bssid_no_alert(settings, frame):
    detector = Detector(replace(settings, protected_ssids=("examplelab",), trusted_bssids=(frame["bssid"],)))
    frame.update(subtype="beacon", ssid="ExampleLab")
    assert detector.observe(Frame.from_json(frame), now=1) == []


def test_protected_management_reason_not_interpreted(frame):
    frame["protected"] = True
    frame["reason_code"] = -1
    assert Frame.from_json(frame).reason_code is None
