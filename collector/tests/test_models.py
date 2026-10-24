import json
import pytest
from wids.models import Frame, parse_wire_line


def test_valid_frame_round_trip(frame):
    parsed = Frame.from_json(frame)
    assert parsed.subtype == "deauth"
    assert parsed.reason_code == 7
    assert parsed.status_code is None
    assert parse_wire_line("WIDS " + json.dumps(frame)) == frame


def test_ignores_boot_log_and_bad_version(frame):
    assert parse_wire_line("I (1) boot: ESP32-C5") is None
    frame["v"] = 99
    assert parse_wire_line("WIDS " + json.dumps(frame)) is None


@pytest.mark.parametrize("field,value", [
    ("sensor_id", "sensor with spaces"), ("sa", "not-a-mac"),
    ("channel", 0), ("subtype", "unknown"), ("ssid", "\n"),
    ("protected", "false"), ("rssi", 999),
])
def test_invalid_frame_rejected(frame, field, value):
    frame[field] = value
    with pytest.raises(ValueError):
        Frame.from_json(frame)


def test_unicode_ssid_is_accepted(frame):
    frame["subtype"] = "beacon"
    frame["ssid"] = "Café"
    assert Frame.from_json(frame).ssid == "Café"


def test_malformed_wire_json():
    assert parse_wire_line('WIDS {bad json') is None
    assert parse_wire_line('WIDS [1,2]') is None
