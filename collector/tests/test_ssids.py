import json
import shutil
import sqlite3
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wids.config import Settings
from wids.engine import Engine
from wids.models import Frame, parse_wire_line
from wids.runtime import validate_collector
from wids.ssids import display_ssid, matches_protected, protected_name
from wids.webapp import create_app


@pytest.fixture(scope='module')
def firmware_codec(tmp_path_factory):
    compiler = shutil.which('cc')
    if not compiler:
        pytest.skip('Host C compiler required for firmware SSID codec integration')
    root = Path(__file__).resolve().parents[2]
    binary = tmp_path_factory.mktemp('ssid-codec') / 'codec'
    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root / 'firmware/main'), str(root / 'firmware/tests/ssid_codec.c'),
                    '-o', str(binary)], check=True, capture_output=True)
    def encode(raw, extra_ies=b''):
        beacon = bytes(36) + extra_ies + bytes([0, len(raw)]) + raw
        return subprocess.check_output([str(binary), beacon.hex()])
    return binary, encode


def test_firmware_to_collector_unicode_alert_and_database(settings, firmware_codec):
    _, encode = firmware_codec
    line = encode('Café'.encode(), extra_ies=b'\x01\x02\x82\x84')
    wire = json.loads(line[5:])
    assert wire['ssid'] is None
    assert wire['ssid_hex'] == '436166c3a9'
    engine = Engine(replace(settings, protected_ssids=('café',)))
    assert engine.ingest_line(line)
    with TestClient(create_app(settings, engine)) as client:
        frame = client.get('/api/frames').json()[0]
        assert frame['ssid'] == 'Café'
        assert frame['ssid_hex'] == '436166c3a9'
        alert = client.get('/api/alerts').json()[0]
        assert alert['rule'] == 'protected_ssid_untrusted_bssid'
        assert 'Café' in alert['details']
        device = client.get('/api/devices').json()['devices'][0]
        assert device['ssids'] == ['Café']


@pytest.mark.parametrize('raw', [
    b'Office', '日本語'.encode(), 'é'.encode() * 16,
    b'raw\xff\xfe\x00\n\r\x1b"\\', b'\xff', b'\\xff', b'_',
    b'\x00', b'\\x00', bytes(range(32)), b'quote"\\end',
])
def test_raw_bytes_round_trip_and_safe_wire(firmware_codec, raw):
    _, encode = firmware_codec
    line = encode(raw)
    assert line.count(b'\n') == 1
    line.decode('ascii')  # No raw control/invalid UTF-8 enters the JSON transport.
    obj = parse_wire_line(line)
    frame = Frame.from_json(obj)
    assert frame.ssid_bytes == raw
    assert frame.ssid_hex == raw.hex()
    assert frame.ssid == display_ssid(raw)
    assert frame.ssid is None or all(character.isprintable() for character in frame.ssid)


def test_different_raw_names_do_not_collapse(firmware_codec):
    _, encode = firmware_codec
    values = [b'\xff', b'\\xff', b'_', b'\x00', b'\\x00', b'\\', b'\\\\', 'Café'.encode()]
    displays = [Frame.from_json(parse_wire_line(encode(raw))).ssid for raw in values]
    assert len(set(displays)) == len(values)


def test_hidden_missing_truncated_and_oversized_ssid(firmware_codec):
    binary, encode = firmware_codec
    hidden = Frame.from_json(parse_wire_line(encode(b'')))
    assert hidden.ssid is None and hidden.ssid_hex == '' and hidden.ssid_bytes == b''
    for beacon in [bytes(20), bytes(36), bytes(36) + b'\x00\x05abc',
                   bytes(36) + b'\x00\x21' + b'x' * 33,
                   bytes(36) + b'\x01\x08abc']:
        line = subprocess.check_output([str(binary), beacon.hex()])
        frame = Frame.from_json(parse_wire_line(line))
        assert frame.ssid is None and frame.ssid_hex is None


@pytest.mark.parametrize('value', ['0', 'gg', '00 11', 'ff' * 33, 12, []])
def test_invalid_wire_hex_is_rejected(frame, value):
    with pytest.raises(ValueError):
        Frame.from_json({**frame, 'ssid_hex': value})


def test_conflicting_text_and_raw_ssid_and_legacy_limits(frame):
    with pytest.raises(ValueError, match='disagree'):
        Frame.from_json({**frame, 'ssid': 'Other', 'ssid_hex': '436166c3a9'})
    with pytest.raises(ValueError):
        Frame.from_json({**frame, 'ssid': 'é' * 17})
    old = Frame.from_json({**frame, 'ssid': 'Café'})
    assert old.ssid == 'Café' and old.ssid_hex is None
    assert old.ssid_bytes == 'Café'.encode()


def test_exact_byte_rules_and_literal_prefix_names(settings, firmware_codec):
    _, encode = firmware_codec
    assert matches_protected('Café'.encode(), ('CAFÉ',))
    assert matches_protected(b'A\x00\xff', ('hex:4100ff',))
    assert not matches_protected(b'a\x00\xff', ('hex:4100ff',))
    assert matches_protected(b'hex:4100ff', ('utf8:hex:4100ff',))
    assert not matches_protected(b'hex:4100ff', ('hex:4100ff',))
    engine = Engine(replace(settings, protected_ssids=('hex:4100ff',)))
    assert engine.ingest_line(encode(b'A\x00\xff'))
    assert engine.store.rows('SELECT * FROM alerts')[0]['rule'] == 'protected_ssid_untrusted_bssid'
    engine.store.close()
    assert validate_collector({'protected_ssids': ['hex:4100ff', 'utf8:hex:4100ff']})
    for value in ('hex:', 'hex:g0', 'hex:' + 'ff' * 33, 'utf8:', 'é' * 17):
        with pytest.raises(ValueError):
            protected_name(value)


def test_environment_supports_raw_rules(monkeypatch):
    monkeypatch.setenv('WIDS_PROTECTED_SSIDS', 'Café,hex:4100FF,utf8:hex:4100ff')
    assert Settings.from_env().protected_ssids == ('Café', 'hex:4100FF', 'utf8:hex:4100ff')
    monkeypatch.setenv('WIDS_PROTECTED_SSIDS', 'hex:bad')
    with pytest.raises(ValueError):
        Settings.from_env()


def test_maximum_length_case_expanding_unicode_setting_is_preserved(monkeypatch):
    name = 'İ' * 16  # 32 input UTF-8 bytes; lowercasing expands the comparison key.
    monkeypatch.setenv('WIDS_PROTECTED_SSIDS', name)
    assert Settings.from_env().protected_ssids == (name,)
    assert validate_collector({'protected_ssids': [name]})['protected_ssids'] == (name,)
    assert matches_protected(name.encode(), (name,))


def test_existing_frame_migration_preserves_legacy_text(settings, frame):
    with sqlite3.connect(settings.database) as db:
        db.execute('''CREATE TABLE frames (
            id INTEGER PRIMARY KEY,timestamp TEXT,sensor_id TEXT,channel INTEGER,
            subtype TEXT,sa TEXT,da TEXT,bssid TEXT,rssi INTEGER,protected INTEGER,
            reason_code INTEGER,status_code INTEGER,ssid TEXT,uptime_ms INTEGER)''')
        db.execute('INSERT INTO frames VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            datetime.now(timezone.utc).isoformat(timespec='seconds'), 'old-sensor', 6,
            'beacon', frame['sa'], frame['da'], frame['bssid'], -40, 0, None, None, 'Caf__', 1))
    engine = Engine(settings)
    old = engine.store.rows('SELECT * FROM frames')[0]
    assert old['ssid'] == 'Caf__'
    assert old['ssid_hex'] is None
    engine.ingest({**frame, 'subtype': 'beacon', 'ssid_hex': '436166c3a9'})
    new = engine.store.rows('SELECT * FROM frames ORDER BY id DESC')[0]
    assert new['ssid'] == 'Café'
    assert new['ssid_hex'] == '436166c3a9'
    engine.store.close()
