from dataclasses import replace

from fastapi.testclient import TestClient

from wids.engine import Engine
from wids.models import Frame
from wids.webapp import create_app


def test_devices_keep_advertised_ssids_separate_from_clients(settings, frame):
    engine = Engine(settings)
    beacon = Frame.from_json({**frame, 'subtype': 'beacon', 'sa': frame['bssid'],
                              'ssid': 'Home, WiFi'})
    engine.store.add_frame(beacon, [])
    client = '02:aa:bb:cc:dd:ee'
    engine.store.add_frame(replace(beacon, subtype='assoc_req', sa=client,
                                   da=beacon.bssid, ssid=None), [])
    engine.store.add_frame(replace(beacon, subtype='deauth', da=client, ssid=None), [])
    result = engine.store.devices()
    devices = {device['mac']: device for device in result['devices']}
    assert set(devices) == {beacon.bssid, client}
    assert devices[beacon.bssid]['role'] == 'Access Point'
    assert devices[beacon.bssid]['ssids'] == ['Home, WiFi']
    assert devices[beacon.bssid]['frame_count'] == 3  # One count per frame, not per address field.
    assert devices[client]['role'] == 'Client / Host'
    assert devices[client]['ssids'] == []
    assert devices[client]['bssids'] == [beacon.bssid]
    assert devices[client]['frame_count'] == 2
    assert not result['has_more']
    assert engine.store.devices(limit=1)['has_more']
    engine.store.close()


def test_devices_exclude_group_zero_and_old_addresses(settings, frame):
    engine = Engine(settings)
    # A probe with a wildcard BSSID does not establish a network association.
    engine.ingest({**frame, 'bssid': 'ff:ff:ff:ff:ff:ff', 'da': '01:00:5e:00:00:01'})
    engine.ingest({**frame, 'bssid': '00:00:00:00:00:00', 'da': '00:00:00:00:00:00'})
    engine.ingest({**frame, 'sa': '02:00:00:00:00:99', 'bssid': '02:00:00:00:00:98'})
    with engine.store.db:
        engine.store.db.execute("UPDATE frames SET timestamp='2000-01-01T00:00:00+00:00' WHERE sa=?",
                                ('02:00:00:00:00:99',))
    result = engine.store.devices()['devices']
    assert len(result) == 1
    assert result[0]['mac'] == frame['sa']
    assert result[0]['bssids'] == []
    assert result[0]['ssids'] == []
    assert result[0]['channels'] == [6]
    engine.store.close()


def test_devices_api_empty_and_limit_validation(settings, frame):
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        assert client.get('/api/devices').json()['devices'] == []
        for limit in (0, -1, 501):
            assert client.get(f'/api/devices?limit={limit}').status_code == 400
        assert client.get('/api/devices?limit=bad').status_code == 422
        engine.ingest(frame)
        response = client.get('/api/devices?limit=1')
        assert response.status_code == 200
        assert len(response.json()['devices']) == 1
        assert response.json()['has_more'] is True
        assert response.json()['window_hours'] == 24
