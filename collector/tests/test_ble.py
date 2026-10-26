import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from wids.ble import Advertisement, BLEPolicy, decode_ad
from wids.engine import Engine
from wids.models import parse_wire_line
from wids.runtime import validate_collector
from wids.webapp import create_app
from test_configuration import headers, sensor_info


def advertisement(**values):
    # Complete name Test, Battery service, Apple company ID, battery service data.
    return {'v': 1, 'kind': 'ble', 'sensor_id': 'c6', 'address': 'cc:bb:aa:11:22:33',
            'address_type': 'random', 'rssi': -55, 'event_type': 0,
            'payload_hex': '05095465737403030f1804ff4c000105160f186401',
            'uptime_ms': 100, **values}


def test_decode_ble_advertisement_and_raw_preservation():
    event = advertisement()
    assert parse_wire_line('WIDS ' + json.dumps(event)) == event
    ad = Advertisement.from_json(event)
    decoded = ad.decoded()
    assert decoded == {'local_name': 'Test', 'service_uuids': ['180f'],
                       'manufacturer_data': [{'company_id': '004c', 'data_hex': '01'}],
                       'service_data': [{'uuid': '180f', 'data_hex': '6401'}], 'ad_malformed': False}
    for value in ('name:test', 'address:CC:BB:AA:11:22:33', 'service:180F', 'company:004C'):
        assert ad.matches(value)
    assert not ad.matches('name:other')
    assert Advertisement.from_json(advertisement(payload_hex='')).decoded()['local_name'] is None
    assert decode_ad(bytes.fromhex('07096162'))['ad_malformed']
    assert decode_ad(bytes.fromhex('02ff00'))['ad_malformed']
    assert decode_ad(bytes.fromhex('0203ff'))['ad_malformed']
    assert decode_ad(bytes.fromhex('0309ff00'))['local_name'] == r'\xff\x00'


@pytest.mark.parametrize('values', [ {'address': 'bad'}, {'address_type': 'identity'},
    {'rssi': True}, {'rssi': -128}, {'uptime_ms': -1}, {'event_type': 4},
    {'payload_hex': 'g0'}, {'payload_hex': '0'}, {'payload_hex': '00' * 32},
    {'sensor_id': 'bad id'}, {'payload_hex': None}])
def test_invalid_ble_reports(values):
    with pytest.raises(ValueError):
        parse_wire_line('WIDS ' + json.dumps(advertisement(**values)))


def test_policy_dedup_cooldown_filters_churn(settings):
    policy = BLEPolicy()
    settings = replace(settings, ble_alert_rules=('name:Test',), ble_duplicate_seconds=10)
    ad = Advertisement.from_json(advertisement())
    assert policy.observe(ad, settings, 0) == (True, ['name:Test'])
    assert policy.observe(ad, settings, 1) == (False, [])
    assert policy.observe(ad, settings, 10) == (True, [])
    assert policy.observe(ad, settings, 60) == (True, ['name:Test'])
    assert policy.observe(ad, replace(settings, ble_filters=('name:other',)), 120) == (False, [])
    for i in range(3000):
        other = replace(ad, address=f'cc:00:00:{i >> 16:02x}:{(i >> 8) & 255:02x}:{i & 255:02x}')
        policy.observe(other, settings, 120)
    assert len(policy.seen) == 1024
    assert len(policy.alerted) == 1  # Rotation cannot bypass a per-sensor/rule cooldown.


def test_ble_api_storage_alerts_retention_and_wifi_compatibility(settings, frame):
    engine = Engine(replace(settings, ble_alert_rules=('service:180f',)))
    with TestClient(create_app(settings, engine)) as client:
        engine.ingest(advertisement())
        engine.ingest(advertisement())
        engine.ingest(frame)
        rows = client.get('/api/ble/observations').json()
        assert len(rows) == 1
        assert rows[0]['payload_hex'] == advertisement()['payload_hex']
        assert rows[0]['local_name'] == 'Test'
        assert client.get('/api/ble/observations?address=invalid').status_code == 400
        assert client.get('/api/ble/observations?address_type=other').status_code == 400
        assert client.get('/api/ble/observations?limit=501').status_code == 400
        assert client.get('/api/ble/devices?limit=0').status_code == 400
        devices = client.get('/api/ble/devices').json()['devices']
        assert devices[0]['observation_count'] == 1
        alerts = client.get('/api/alerts').json()
        assert alerts[0]['protocol'] == 'ble'
        assert alerts[0]['bssid'] is None and alerts[0]['channel'] is None
        assert alerts[0]['address_type'] == 'random'
        assert advertisement()['address'] in client.get('/api/alert-sources').json()['macs']
        assert client.get('/api/summary').json()['ble_observations_24h'] == 1
        assert client.get('/api/summary').json()['frames_24h'] == 1
        # Same address with a different address type is a separate observation identity.
        engine.ingest(advertisement(address_type='public'))
        assert len(client.get('/api/ble/devices').json()['devices']) == 2
        engine.store.db.execute("UPDATE ble_observations SET timestamp='2000-01-01'")
        engine.store.db.execute("UPDATE ble_alerts SET timestamp='2000-01-01'")
        engine.store.db.commit()
        engine.store.cleanup()
        assert client.get('/api/ble/observations').json() == []
        assert client.get('/api/alerts').json() == []
        assert client.get('/api/summary').json()['frames_24h'] == 1


def test_ble_configuration_persistence_limits_and_bounded_storage(settings):
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        values = {'ble_filters': ['name:Test', 'company:004c'],
                  'ble_duplicate_seconds': 0, 'ble_alert_rules': ['name:Test']}
        assert client.post('/api/configuration/collector', headers=headers(settings), json=values).status_code == 200
        policy = client.get('/api/retention').json()['policy']
        policy.update(ble_age_hours=48, ble_max_records=100)
        preview = client.post('/api/retention/preview', json=policy).json()
        assert preview['destructive'] is True
        assert client.post('/api/retention/apply', headers=headers(settings), json={
            'policy': policy, 'token': preview['token'], 'confirmation': 'RETENTION'}).status_code == 200
        for bad in ({'ble_filters': ['invalid']}, {'ble_alert_rules': ['company:xyz']},
                    {'ble_retention_days': 0}, {'ble_duplicate_seconds': -1}, {'ble_max_records': 99}):
            assert client.post('/api/configuration/collector', headers=headers(settings), json=bad).status_code == 400
        for i in range(150):
            engine.ingest(advertisement(address=f'cc:00:00:00:00:{i:02x}'))
        assert len(client.get('/api/ble/observations?limit=500').json()) <= 100
        assert len(client.get('/api/alerts?limit=500').json()) <= 100
    restarted = Engine(settings)
    assert restarted.settings.ble_filters == ('name:Test', 'company:004c')
    restarted.store.close()


def test_ble_sensor_capability_validation():
    from wids.sensor import SensorControl
    sensor = SensorControl()
    sensor.connect()
    ack = sensor_info()
    sensor.receive(ack)
    with pytest.raises(ValueError, match='does not support BLE'):
        sensor.validate({'ble_enabled': True})
    ack['capabilities']['ble'] = True
    ack['config'].update(ble_enabled=False, ble_interval_ms=100, ble_window_ms=20)
    ack['ble_status'] = {'scanning': False, 'captured': 0, 'dropped': 0, 'error': 0}
    ack['ble_status']['error'] = -1  # Failed stack initialization must remain visible in Status.
    sensor.receive(ack)
    assert sensor.snapshot()['configuration']['ble_status']['error'] == -1
    assert sensor.validate({'ble_enabled': True})['ble_enabled'] is True
    with pytest.raises(ValueError, match='must not exceed'):
        sensor.validate({'ble_window_ms': 101})
    with pytest.raises(ValueError):
        sensor.validate({'ble_enabled': 'true'})
    bad = json.loads(json.dumps(ack))
    bad['config']['ble_window_ms'] = 200
    sensor.receive(bad)
    assert sensor.snapshot()['configuration']['values']['ble_window_ms'] == 20


def test_service_uuid_widths_and_malformed_ad():
    # Same standard service in 16/32/128-bit forms is normalized for rules.
    from wids.ble import service_uuid
    assert service_uuid('0000180f-0000-1000-8000-00805f9b34fb') == '180f'
    assert decode_ad(bytes.fromhex('05050f180000'))['service_uuids'] == ['180f']
    raw = bytes.fromhex('1107fb349b5f80000080001000000f180000')
    assert decode_ad(raw)['service_uuids'] == ['180f']
    assert decode_ad(bytes.fromhex('021600'))['ad_malformed']


def test_startup_applies_ble_policy_before_cleanup(settings):
    from datetime import datetime, timedelta, timezone
    engine = Engine(replace(settings, ble_retention_days=30, ble_duplicate_seconds=0, ble_max_records=200))
    for i in range(150):
        engine.ingest(advertisement(address=f'cc:00:00:00:00:{i:02x}'))
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec='seconds')
    engine.store.db.execute('UPDATE ble_observations SET timestamp=?', (old,))
    engine.store.db.commit()
    engine.store.close()
    restarted = Engine(replace(settings, ble_retention_days=30, ble_max_records=200))
    assert len(restarted.store.ble_observations(500)) == 150
    restarted.store.close()
