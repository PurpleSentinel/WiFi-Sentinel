from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from wids.engine import Engine
from wids.models import Frame
from wids.webapp import create_app


def test_ap_hidden_ssid_client_and_mixed_evidence(settings, frame):
    engine = Engine(settings)
    ap, client, mixed = frame['bssid'], frame['sa'], '02:00:00:00:00:77'
    base = Frame.from_json(frame)
    engine.store.add_frame(replace(base, subtype='beacon', sa=ap, ssid=None), [])
    engine.store.add_frame(replace(base, subtype='assoc_req', sa=client, da=ap), [])
    engine.store.add_frame(replace(base, subtype='probe_resp', sa=mixed, bssid=mixed, ssid='Mixed'), [])
    engine.store.add_frame(replace(base, subtype='reassoc_req', sa=mixed, da=ap), [])
    devices = {row['mac']: row for row in engine.store.devices()['devices']}
    assert devices[ap]['role_code'] == 'access_point'
    assert devices[ap]['ssids'] == []  # Hidden SSID does not negate advertisement evidence.
    assert devices[ap]['evidence_counts']['beacons'] == 1
    assert devices[client]['role_code'] == 'client'
    assert devices[client]['observed_roles'] == ['Source']
    assert devices[mixed]['role_code'] == 'mixed'
    assert devices[mixed]['evidence_counts']['probe_responses'] == 1
    assert devices[mixed]['evidence_counts']['reassociation_requests'] == 1
    assert engine.store.mac_details(mixed)['classification'] == {
        key: devices[mixed][key] for key in ('role_code', 'role', 'evidence', 'evidence_counts', 'window_hours')}
    for code, expected in [('access_point', ap), ('client', client), ('mixed', mixed)]:
        assert [row['mac'] for row in engine.store.devices(role=code)['devices']] == [expected]
    engine.store.close()


@pytest.mark.parametrize('subtype', ['assoc_resp', 'reassoc_resp'])
def test_response_destination_is_client_evidence_without_claiming_success(settings, frame, subtype):
    engine = Engine(settings)
    engine.ingest({**frame, 'subtype': subtype, 'sa': frame['bssid'], 'da': frame['sa'], 'status_code': 1})
    devices = {row['mac']: row for row in engine.store.devices()['devices']}
    assert devices[frame['sa']]['role_code'] == 'client'
    # A response's source/BSSID without an advertisement is not enough for this AP classification.
    assert devices[frame['bssid']]['role_code'] == 'unknown'
    engine.store.close()


@pytest.mark.parametrize('subtype', ['auth', 'deauth', 'disassoc', 'beacon', 'probe_resp', 'assoc_req', 'reassoc_req'])
def test_header_fields_and_inconsistent_advertisements_do_not_force_roles(settings, frame, subtype):
    engine = Engine(settings)
    # Source differs from BSSID; destination is broadcast rather than the BSSID.
    engine.ingest({**frame, 'subtype': subtype, 'ssid': 'Forged' if subtype in ('beacon', 'probe_resp') else None})
    devices = engine.store.devices()['devices']
    assert all(row['role_code'] == 'unknown' for row in devices)
    assert all(row['ssids'] == [] for row in devices)
    assert all('Insufficient' in row['evidence'][0] for row in devices)
    engine.store.close()


def test_expired_role_evidence_reclassifies_without_removing_retained_observations(settings, frame):
    engine = Engine(settings)
    engine.ingest({**frame, 'subtype': 'beacon', 'sa': frame['bssid'], 'ssid': 'Old AP'})
    assert engine.store.devices(role='access_point')['devices']
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec='seconds')
    with engine.store.db:
        engine.store.db.execute('UPDATE frames SET timestamp=?', (old,))
    engine.ingest(frame)  # New disconnection frame is not classification evidence.
    ap = next(row for row in engine.store.devices()['devices'] if row['mac'] == frame['bssid'])
    assert ap['role_code'] == 'unknown'
    assert engine.store.devices(role='access_point')['devices'] == []
    details = engine.store.mac_details(frame['bssid'])
    assert details['classification']['role_code'] == 'unknown'
    assert details['ssids'] == ['Old AP']  # Retained local facts stay separate from 24h classification.
    engine.store.close()


def test_role_filter_is_applied_before_limit_and_api_validates(settings, frame):
    engine = Engine(settings)
    engine.ingest({**frame, 'subtype': 'beacon', 'sa': frame['bssid']})
    for i in range(5):
        engine.ingest({**frame, 'sa': f'02:00:00:00:01:{i:02x}'})
    with TestClient(create_app(settings, engine)) as client:
        result = client.get('/api/devices?limit=1&role=access_point').json()
        assert result['role'] == 'access_point'
        assert result['devices'][0]['mac'] == frame['bssid']
        assert result['has_more'] is False
        assert client.get('/api/devices?role=invalid').status_code == 400
        assert client.get('/api/devices?role=client').json()['devices'] == []
        details = client.get('/api/mac/' + frame['bssid']).json()['observations']
        assert details['classification']['role'] == 'Access Point'
