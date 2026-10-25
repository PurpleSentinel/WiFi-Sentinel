import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from wids.ble_identity import identify, registry
from wids.engine import Engine
from wids.storage import Store
from wids.webapp import create_app
from test_ble import advertisement
from test_configuration import headers


def test_offline_registry_evidence_and_label_precedence():
    from wids.ble import Advertisement
    row = {**advertisement(), **Advertisement.from_json(advertisement()).decoded()}
    data = identify(row)
    assert data['display_label'] == 'Test' and data['label_source'] == 'Advertised local name'
    assert data['company_details'][0]['name'] == 'Apple, Inc.'
    assert data['service_details'][0]['name'] == 'Battery'
    assert data['address_subtype'] == 'Static random'
    assert 'Unverified' in data['identity_confidence']
    assert identify({**row,'alias':'My sensor'})['label_source'] == 'Operator alias'
    assert identify({**row,'local_name':None})['label_source'] == 'Advertised service'
    unknown = identify({**row,'local_name':None,'service_uuids':['01234567-89ab-cdef-0123-456789abcdef'],
                        'manufacturer_data':[{'company_id':'ffff','data_hex':''}]})
    assert unknown['label_source'] == 'Address fallback'
    assert unknown['category'] == 'Unknown device category'
    assert unknown['company_details'][0]['name'] is None
    assert unknown['service_details'][0]['uuid'].startswith('01234567')
    for address,kind in [('00:11:22:33:44:55','Non-resolvable private'),
                         ('40:11:22:33:44:55','Resolvable private'),
                         ('80:11:22:33:44:55','Reserved random address pattern')]:
        assert identify({**row,'address':address})['address_subtype'] == kind
    assert identify({**row,'address_type':'public'})['address_subtype'] == 'Public'
    assert len(registry()['companies']) > 1000


def test_sensor_scoped_history_labels_authorization_and_persistence(settings):
    engine = Engine(replace(settings,ble_duplicate_seconds=0))
    ad = advertisement()
    with TestClient(create_app(settings,engine)) as client:
        engine.ingest(ad)
        engine.ingest({**ad,'sensor_id':'second','rssi':-79})
        engine.ingest({**ad,'address_type':'public','rssi':-89})
        query='sensor_id=c6&address='+ad['address']+'&address_type=random'
        details=client.get('/api/ble/advertiser?'+query).json()
        assert [row['rssi'] for row in details['observations']] == [-55]
        assert client.get('/api/ble/observations?'+query).json()[0]['rssi'] == -55
        values={key:ad[key] for key in ('sensor_id','address','address_type')}
        values.update(alias='Desk beacon',notes='Operator supplied, not verified')
        assert client.post('/api/ble/label',json=values).status_code == 403
        assert client.post('/api/ble/label',headers={**headers(settings),'Origin':'http://elsewhere'},json=values).status_code == 403
        assert client.post('/api/ble/label',headers=headers(settings),json=values).status_code == 200
        details=client.get('/api/ble/advertiser?'+query).json()
        assert details['label']['alias'] == details['advertiser']['display_label'] == 'Desk beacon'
        assert client.get('/api/ble/labels').json()[0]['alias'] == 'Desk beacon'
        assert client.get('/api/ble/advertiser?'+query.replace('c6','second')).json()['label']['alias'] == ''
        assert client.get('/api/ble/advertiser?'+query.replace('random','public')).json()['label']['alias'] == ''
        assert client.get('/api/ble/advertiser?'+query.replace(ad['address'],'cc:00:00:00:00:01')).json()['observations'] == []
        for patch in ({'alias':'a'*81},{'notes':'a'*1001},{'alias':'bad\x00'}, {'notes':False},
                      {'sensor_id':'bad id'}, {'address':'bad'}, {'address_type':'unknown'}, {'unexpected':1}):
            assert client.post('/api/ble/label',headers=headers(settings),json={**values,**patch}).status_code == 400
        assert client.get('/api/ble/advertiser?'+query.replace('c6','bad%20id')).status_code == 400
        assert client.get('/api/ble/observations?'+query.replace('c6','bad%20id')).status_code == 400
    restarted=Engine(settings)
    assert restarted.store.ble_label('c6',ad['address'],'random')['alias'] == 'Desk beacon'
    restarted.store.save_ble_label('c6',ad['address'],'random','','')
    assert restarted.store.ble_label('c6',ad['address'],'random')['alias'] == ''
    restarted.store.close()


def test_explorer_search_before_limit_names_evidence_and_sort(settings):
    engine=Engine(replace(settings,ble_duplicate_seconds=0,ble_alert_rules=('name:Test',)))
    with TestClient(create_app(settings,engine)) as client:
        first=advertisement(address='cc:00:00:00:00:01')
        engine.ingest(first)
        # Most recent advertisement omits the name; preserve earlier named evidence.
        engine.ingest({**first,'payload_hex':'04ff4c0001','rssi':-70})
        for i in range(2,6):
            engine.ingest(advertisement(address=f'cc:00:00:00:00:{i:02x}',payload_hex='',rssi=-40))
        values={key:first[key] for key in ('sensor_id','address','address_type')}
        client.post('/api/ble/label',headers=headers(settings),json={**values,'alias':'Old desk beacon'})
        data=client.get('/api/ble/devices?limit=1&query=desk').json()
        assert len(data['devices']) == 1 and data['devices'][0]['address'] == first['address']
        assert data['devices'][0]['advertised_name'] == 'Test'
        assert data['total_identities'] == 5
        assert client.get('/api/ble/devices?query=Apple').json()['devices'][0]['address'] == first['address']
        assert client.get('/api/ble/devices?alert_only=true').json()['devices'][0]['alert_associated']
        assert client.get('/api/ble/devices?address_type=public').json()['devices'] == []
        assert client.get('/api/ble/devices?sort=rssi').json()['devices'][0]['rssi'] == -40
        assert client.get('/api/ble/devices?sort=name').status_code == 200
        assert client.get('/api/ble/devices?limit=1').json()['has_more']
        for query in ('sort=invalid','address_type=invalid','query='+'x'*201):
            assert client.get('/api/ble/devices?'+query).status_code == 400


def test_legacy_ble_schema_backfills_names(tmp_path):
    path=tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE ble_observations (id INTEGER PRIMARY KEY,timestamp TEXT,sensor_id TEXT,address TEXT,address_type TEXT,rssi INTEGER,payload_hex TEXT,event_type INTEGER,uptime_ms INTEGER)')
        db.execute('INSERT INTO ble_observations VALUES (1,?,?,?,?,?,?,?,?)',
                   (Store.timestamp(),'c6','cc:00:00:00:00:01','random',-55,'050954657374',0,100))
    store=Store(path)
    assert store.ble_devices()['devices'][0]['advertised_name'] == 'Test'
    store.close()


def test_label_record_limit_and_clear(settings):
    engine=Engine(settings)
    with engine.store.db:
        engine.store.db.executemany('INSERT INTO ble_labels VALUES (?,?,?,?,?,?)',
            [(f'sensor-{i}','cc:00:00:00:00:01','random','alias','',Store.timestamp()) for i in range(1024)])
    with pytest.raises(ValueError,match='1024'):
        engine.store.save_ble_label('new','cc:00:00:00:00:01','random','alias','')
    engine.store.save_ble_label('sensor-0','cc:00:00:00:00:01','random','updated','')
    engine.store.save_ble_label('sensor-1','cc:00:00:00:00:01','random','','')
    engine.store.save_ble_label('new','cc:00:00:00:00:01','random','alias','')
    engine.store.close()
