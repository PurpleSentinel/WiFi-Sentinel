import json
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from wids.engine import Engine, serial_loop
from wids.runtime import configuration_key, settings_path
from wids.sensor import SensorControl
from wids.webapp import create_app


def sensor_info(channel=6):
    return {'v': 1, 'kind': 'config_ack', 'id': 'refresh', 'ok': True,
            'config': {'sensor_id': 'c6', 'band': '2.4', 'channel': channel,
                       'beacon_sample_n': 20, 'heartbeat_seconds': 15},
            'capabilities': {'chip': 'esp32c6', 'bands': ['2.4'],
                             'channels': {'2.4': list(range(1, 12))},
                             'console': 'USB Serial/JTAG'}}


def headers(settings):
    return {'Origin': 'http://testserver', 'X-Configuration-Key': configuration_key(settings)}


def test_configuration_authentication_and_origin(settings):
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        endpoint = '/api/configuration/collector'
        assert client.post(endpoint, json={'window_seconds': 20}).status_code == 403
        auth = headers(settings)
        assert client.post(endpoint, headers={**auth, 'Origin': 'http://evil.example'},
                           json={'window_seconds': 20}).status_code == 403
        assert client.post(endpoint, headers={'X-Configuration-Key': auth['X-Configuration-Key']},
                           json={'window_seconds': 20}).status_code == 403
        assert engine.settings.window_seconds == 10
        assert not settings_path(settings).exists()
        assert client.get('/api/configuration').headers['cache-control'] == 'no-store'
        assert 'config-key' not in client.get('/api/configuration').text


def test_collector_validation_atomic_save_and_restart(settings):
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        auth = headers(settings)
        endpoint = '/api/configuration/collector'
        for values in ({'window_seconds': 0}, {'window_seconds': True},
                       {'port': 9999}, {'trusted_bssids': ['invalid']},
                       {'window_seconds': 20, 'retention_days': -1}):
            assert client.post(endpoint, headers=auth, json=values).status_code == 400
        assert engine.settings.window_seconds == 10
        assert not settings_path(settings).exists()
        response = client.post(endpoint, headers=auth, json={
            'window_seconds': 20, 'protected_ssids': ['Office'],
            'trusted_bssids': ['AA:BB:CC:DD:EE:FF']})
        assert response.status_code == 200
        assert engine.settings.window_seconds == 20
        assert engine.detector.settings.protected_ssids == ('Office',)
        assert engine.detector.settings.trusted_bssids == ('aa:bb:cc:dd:ee:ff',)
        assert settings_path(settings).stat().st_mode & 0o777 == 0o600
    restarted = Engine(replace(settings, window_seconds=99))
    assert restarted.settings.window_seconds == 20
    assert restarted.settings.host == settings.host
    restarted.store.close()


def test_sensor_rejects_unsupported_capabilities(settings):
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        endpoint = '/api/configuration/sensor'
        auth = headers(settings)
        assert client.post(endpoint, headers=auth, json={'channel': 11}).status_code == 503
        engine.sensor.connect()
        assert client.post(endpoint, headers=auth, json={'channel': 11}).status_code == 503
        engine.ingest_line('WIDS ' + json.dumps(sensor_info()))
        for values in ({'band': '5', 'channel': 36}, {'channel': 177},
                       {'channel': True}, {'sensor_id': 'bad name'},
                       {'heartbeat_seconds': 0}, {'beacon_sample_n': 1001}):
            assert client.post(endpoint, headers=auth, json=values).status_code == 400
        assert engine.sensor.snapshot()['configuration']['values']['channel'] == 6


def test_sensor_command_acknowledgement_and_failure():
    control = SensorControl()
    control.connect()
    control.receive(sensor_info())
    replies = []
    worker = threading.Thread(target=lambda: replies.append(control.apply({'channel': 11})))
    worker.start()
    identifier, wire = control.outgoing.get(timeout=1)
    request = json.loads(wire.decode()[9:])
    assert request['settings']['channel'] == 11
    assert control.snapshot()['configuration']['values']['channel'] == 6
    ack = {**sensor_info(11), 'id': identifier}
    control.receive(ack)
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert replies[0]['configuration']['values']['channel'] == 11
    errors = []
    def rejected():
        try:
            control.apply({'channel': 1})
        except ValueError as exc:
            errors.append(str(exc))
    worker = threading.Thread(target=rejected)
    worker.start()
    identifier, _ = control.outgoing.get(timeout=1)
    control.receive({'kind': 'config_ack', 'id': identifier, 'ok': False, 'error': 'NVS failed'})
    worker.join(timeout=1)
    assert errors == ['NVS failed']
    assert control.snapshot()['configuration']['values']['channel'] == 11


def test_malformed_sensor_ack_does_not_replace_confirmed_settings():
    control = SensorControl()
    control.connect()
    control.receive(sensor_info())
    malformed = sensor_info(177)
    control.receive(malformed)
    assert control.snapshot()['configuration']['values']['channel'] == 6
    malformed = sensor_info()
    malformed['capabilities']['channels'] = None
    control.receive(malformed)
    assert control.snapshot()['configuration']['values']['channel'] == 6


def test_timeout_cancels_unsent_commands_and_disconnect_wakes_waiter():
    control = SensorControl()
    control.connect()
    control.receive(sensor_info())
    with pytest.raises(TimeoutError):
        control.apply({'channel': 11}, timeout=0.01)
    class Port:
        def write(self, wire):
            pytest.fail('Timed-out command must not be sent later')
    control.send_queued(Port())
    errors = []
    def waiting():
        try:
            control.apply({'channel': 11})
        except ConnectionError as exc:
            errors.append(str(exc))
    worker = threading.Thread(target=waiting)
    worker.start()
    control.outgoing.get(timeout=1)
    control.disconnect()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert 'disconnected' in errors[0]
    assert control.snapshot() == {'connected': False, 'configuration': None}


def test_failed_collector_persistence_leaves_effective_policy_unchanged(settings, monkeypatch):
    engine = Engine(settings)
    def fail(_):
        raise OSError('Disk full')
    monkeypatch.setattr('wids.engine.save_settings', fail)
    with pytest.raises(OSError):
        engine.configure({'window_seconds': 20})
    assert engine.settings.window_seconds == 10
    assert engine.detector.settings.window_seconds == 10
    engine.store.close()


def test_serial_reader_preserves_partial_lines_and_discards_oversized_input(settings, frame, monkeypatch):
    engine = Engine(replace(settings, serial_port='/dev/test-sensor'))
    stop = threading.Event()
    wire = ('WIDS ' + json.dumps(frame) + '\n').encode()
    chunks = [b'WIDS ' + b'x' * 2044, b'garbage\n', wire[:25], b'', wire[25:]]
    class Port:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        @property
        def in_waiting(self):
            return len(chunks[0]) if chunks else 0
        def write(self, _):
            pass
        def read(self, size):
            if chunks:
                chunk = chunks.pop(0)
                if len(chunk) > size:
                    chunks.insert(0, chunk[size:])
                return chunk[:size]
            stop.set()
            return b''
    monkeypatch.setattr('serial.Serial', lambda *args, **kwargs: Port())
    serial_loop(engine, stop)
    assert engine.store.summary()['frames_24h'] == 1
    assert not engine.sensor.snapshot()['connected']
    engine.store.close()
