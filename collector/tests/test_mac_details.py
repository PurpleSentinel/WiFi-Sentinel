import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from wids.detection import Alert, Detector
from wids.engine import Engine
from wids.models import Frame
from wids.storage import Store
from wids.vendors import VendorLookup, normalize_mac
from wids.webapp import create_app


def test_actual_sources_are_recorded_for_multi_source_alerts(settings, frame):
    engine = Engine(replace(settings, deauth_threshold=3))
    sources = ['00:11:22:33:44:01', '00:11:22:33:44:02', '00:11:22:33:44:01']
    for sa in sources:
        engine.ingest({**frame, 'sa': sa})
    alert = engine.store.rows('SELECT * FROM alerts')[0]
    assert alert['source_macs'] == sorted(set(sources))
    assert alert['bssid'] not in alert['source_macs']
    assert engine.store.alert_sources()['macs'] == sorted(set(sources))
    details = engine.store.mac_details(sources[0])
    assert details['roles'] == ['Source']
    assert details['frame_count'] == 2
    assert details['alerts'][0]['association'] == 'Contributing source'
    assert engine.store.mac_details(frame['bssid'])['alerts'][0]['association'] == 'BSSID context'
    engine.store.close()


def test_single_frame_ssid_alert_records_source_instead_of_bssid(settings, frame):
    detector = Detector(replace(settings, protected_ssids=('office',)))
    alerts = detector.observe(Frame.from_json({**frame, 'subtype': 'beacon', 'ssid': 'Office'}))
    assert alerts[0].source_macs == (frame['sa'],)


def test_legacy_migration_and_retention_remove_red_associations(settings, frame):
    db = sqlite3.connect(settings.database)
    db.execute('''CREATE TABLE alerts(id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,
        sensor_id TEXT NOT NULL,rule TEXT NOT NULL,severity TEXT NOT NULL,bssid TEXT NOT NULL,
        channel INTEGER NOT NULL,frame_count INTEGER NOT NULL,details TEXT NOT NULL)''')
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    db.execute('INSERT INTO alerts VALUES (1,?,?,?,?,?,?,?,?)',
               (stamp, 'old', 'deauth_flood', 'high', frame['bssid'], 6, 20, 'Legacy alert'))
    db.commit()
    db.close()
    store = Store(settings.database)
    assert store.alert_sources() == {'macs': [], 'legacy_alerts_without_sources': 1}
    assert store.mac_details(frame['bssid'])['alerts'][0]['source_macs'] is None
    alert = Alert(stamp, 'sensor', 'deauth_flood', 'high', frame['bssid'], 6, 1, 'Burst', (frame['sa'],))
    store.add_frame(Frame.from_json(frame), [alert])
    assert frame['sa'] in store.alert_sources()['macs']
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec='seconds')
    with store.db:
        store.db.execute('UPDATE alerts SET timestamp=?', (old,))
    assert store.alert_sources()['macs'] == []
    assert store.mac_details(frame['sa'])['alerts'] == []
    store.cleanup()
    assert store.rows('SELECT * FROM alerts') == []
    store.close()


@pytest.mark.parametrize('value', ['6098490DD57A', '60-98-49-0d-d5-7a', '6098.490d.d57a', '60:98:49:0D:D5:7A'])
def test_mac_normalization(value):
    assert normalize_mac(value) == '60:98:49:0d:d5:7a'


def test_vendor_prefix_only_fetch_cache_and_offline_fallback(tmp_path, monkeypatch):
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, size):
            assert size == 65537
            return json.dumps({'success': True, 'found': True, 'macPrefix': '609849',
                               'company': 'Nokia', 'address': '<untrusted text>'}).encode()
    def fetch(request, timeout):
        calls.append(request.full_url)
        assert timeout == 3
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', fetch)
    lookup = VendorLookup(tmp_path / 'vendors.sqlite3')
    result = lookup.lookup('60:98:49:0d:d5:7a')
    assert calls == ['https://api.maclookup.app/v2/macs/609849']
    assert result['registration']['vendorName'].startswith('Nokia')
    assert result['additional_details']['address'] == '<untrusted text>'
    assert result['registration']['blockSize'] == 2**24
    assert not result['cached']
    assert lookup.lookup('60:98:49:aa:bb:cc')['cached']
    assert len(calls) == 1
    lookup.close()
    lookup = VendorLookup(tmp_path / 'vendors.sqlite3')
    assert lookup.lookup('60:98:49:aa:bb:cc')['cached']
    lookup.last_fetch = float('-inf')
    monkeypatch.setattr(lookup, 'fetch', lambda _: (_ for _ in ()).throw(OSError('Offline')))
    result = lookup.lookup('60:98:49:aa:bb:cc', refresh=True)
    assert result['registration']['vendorName'].startswith('Nokia')
    assert result['additional_details']['company'] == 'Nokia'
    assert result['error']
    lookup.close()


def test_private_group_unknown_and_longest_prefix(tmp_path, monkeypatch):
    lookup = VendorLookup(tmp_path / 'vendors.sqlite3')
    monkeypatch.setattr(lookup, 'fetch', lambda _: pytest.fail('Must not query vendor service'))
    assert lookup.lookup('da:c4:01:b3:9d:a6')['status'] == 'locally_administered'
    assert lookup.lookup('ff:ff:ff:ff:ff:ff')['status'] == 'multicast_or_broadcast'
    assert lookup.lookup('00:00:00:00:00:00')['status'] == 'zero_address'
    def fake_registry():
        return {prefix: {'macPrefix': prefix, 'vendorName': prefix, 'blockType': 'MA-S'}
                for prefix in ['001122', '0011223', '001122334']}, {'retrieved_at': 'test'}
    monkeypatch.setattr('wids.vendors.registry', fake_registry)
    assert lookup.lookup('00:11:22:33:44:55')['registration']['vendorName'] == '001122334'
    assert lookup.lookup('00:11:22:33:44:55')['registration']['blockSize'] == 4096
    assert lookup.lookup('04:11:22:33:44:55')['status'] == 'not_found'
    lookup.close()


def test_mac_api_rejects_invalid_addresses_and_keeps_local_details(settings, monkeypatch):
    monkeypatch.setattr(VendorLookup, 'fetch', staticmethod(lambda _: (_ for _ in ()).throw(OSError('Offline'))))
    engine = Engine(settings)
    with TestClient(create_app(settings, engine)) as client:
        assert client.get('/api/mac/invalid').status_code == 400
        assert client.get('/api/mac/invalid/vendor').status_code == 400
        result = client.get('/api/mac/6098490DD57A').json()
        assert result['mac'] == '60:98:49:0d:d5:7a'
        assert result['observations']['frame_count'] == 0
        result = client.get('/api/mac/6098490DD57A/vendor').json()
        assert result['status'] == 'found'
        assert result['error']


def test_unavailable_vendor_cache_and_registry_do_not_break_capture(settings, frame, monkeypatch):
    cache = settings.database.parent / 'broken.vendors.sqlite3'
    cache.write_bytes(b'not a sqlite database')
    lookup = VendorLookup(cache)
    monkeypatch.setattr(lookup, 'fetch', lambda _: (_ for _ in ()).throw(OSError('Offline')))
    assert lookup.lookup('60:98:49:0d:d5:7a')['registration']['vendorName'].startswith('Nokia')
    monkeypatch.setattr('wids.vendors.registry', lambda: (_ for _ in ()).throw(OSError('Missing registry')))
    assert lookup.lookup('60:98:49:0d:d5:7a')['status'] == 'registry_unavailable'
    lookup.close()
    engine = Engine(settings)
    assert engine.ingest(frame)
    assert engine.store.summary()['frames_24h'] == 1
    engine.store.close()
