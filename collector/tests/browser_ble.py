"""BLE explorer, protected labels and approximate ranging browser regressions."""
import json
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright


class BLEBrowser(unittest.TestCase):
    def test_explorer_ranging_identity_privacy_filters_and_labels(self):
        html=(Path(__file__).parents[1]/'wids/static/index.html').read_text()
        address='cc:bb:aa:11:22:33'
        now=time.time()
        stamp=lambda seconds: datetime.fromtimestamp(now-seconds,timezone.utc).isoformat()
        item={'id':2,'address':address,'address_type':'random','sensor_id':'c6',
              'timestamp':stamp(1),'last_seen':stamp(1),'local_name':'<img src=x onerror=alert(1)>',
              'advertised_name':'<img src=x onerror=alert(1)>','display_label':'<img src=x onerror=alert(1)>',
              'label_source':'Advertised local name','category':'Battery advertised',
              'address_subtype':'Static random','identity_confidence':'Unverified advertisement',
              'registry_source':'Bluetooth SIG Assigned Numbers','registry_retrieved_at':'2026-10-25',
              'service_uuids':['180f'],'service_details':[{'uuid':'180f','name':'Battery'}],
              'manufacturer_data':[{'company_id':'004c','data_hex':'01'}],
              'company_details':[{'id':'004c','name':'Apple, Inc.'}],
              'service_data':[],'payload_hex':'04ff4c0001','rssi':-59,
              'observation_count':2,'event_type':0,'ad_malformed':False,'alert_associated':True}
        second={**item,'sensor_id':'second','display_label':'Second receiver','local_name':'Second receiver',
                'rssi':-79,'alert_associated':False}
        labels={}
        sensor={'connected':True,'configuration':{
            'values':{'sensor_id':'c6','band':'2.4','channel':6,'beacon_sample_n':20,
                      'heartbeat_seconds':15,'ble_enabled':True,'ble_interval_ms':100,'ble_window_ms':20},
            'capabilities':{'chip':'esp32c6','console':'USB Serial/JTAG','bands':['2.4'],'channels':{'2.4':[6]},'ble':True},
            'ble_status':{'scanning':True,'captured':20,'dropped':3,'error':0}}}
        config={'sensor':sensor,'collector':{'ble_retention_days':7,'ble_filters':[],'ble_alert_rules':[]},
                'limits':{'ble_retention_days':[1,3650]},'lists':['ble_filters','ble_alert_rules'],'restart_fields':[]}
        calls,posts,errors=[],[],[]
        stale=False
        def route(request):
            nonlocal stale
            path=urlsplit(request.request.url).path
            if not path.startswith('/api/'):
                request.fulfill(status=200,content_type='text/html',body=html);return
            name=path[5:];params=parse_qs(urlsplit(request.request.url).query);calls.append(request.request.url)
            def label_for(row):return labels.get(row['sensor_id'],{'alias':'','notes':''})
            def enriched(row):
                label=label_for(row)
                return {**row,**label,'display_label':label['alias'] or row['display_label'],
                        'label_source':'Operator alias' if label['alias'] else row['label_source']}
            status=200
            if name=='ble/label':
                body=request.request.post_data_json;posts.append(body)
                if request.request.headers.get('x-configuration-key')!='test-key':
                    status,data=403,{'detail':'A valid configuration key is required'}
                else:
                    labels[body['sensor_id']]={'alias':body['alias'],'notes':body['notes']};data=labels[body['sensor_id']]
            elif name=='ble/devices':
                rows=[enriched(item),enriched(second)]
                query=params.get('query',[''])[0].lower()
                if query:rows=[row for row in rows if query in json.dumps(row).lower()]
                if params.get('address_type')==['public']:rows=[]
                if params.get('alert_only')==['true']:rows=[row for row in rows if row['alert_associated']]
                data={'devices':rows,'has_more':False,'total_identities':2,'latest_observation':item['timestamp']}
            elif name=='ble/advertiser':
                row=item if params['sensor_id']==['c6'] else second
                if stale:row={**row,'timestamp':stamp(120),'last_seen':stamp(120)}
                old={**row,'id':1,'timestamp':stamp(5 if not stale else 125),'rssi':-79}
                data={'advertiser':enriched(row),'label':label_for(row),'observations':[row,old],'sample_limit':100}
            elif name=='ble/observations':data=[item,second]
            elif request.request.method=='POST':
                body=request.request.post_data_json;posts.append(body);sensor['configuration']['values'].update(body);data=sensor
            else:
                data={'health':{'serial_enabled':True},'alert-sources':{'macs':[address],'legacy_alerts_without_sources':0},
                      'summary':{'frames_24h':1,'alerts_24h':1,'sensors':1,'by_subtype':[],'ble_observations_24h':2},
                      'channels':[],'frames':[],'devices':{'devices':[],'has_more':False},'alerts':[],
                      'sensors':[],'configuration':config}[name]
            request.fulfill(status=status,content_type='application/json',body=json.dumps(data))
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page();page.route('**/*',route);page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://dashboard.test')
            self.assertEqual(page.get_by_role('tab').all_text_contents(),['Overview','Alerts','Reporting','Devices','BLE'])
            for tab in ('Reporting','Devices'):
                page.get_by_role('tab',name=tab,exact=True).click()
                page.wait_for_function("name=>document.querySelector('#panel-'+name).getAttribute('aria-busy')==='false'",arg=tab.lower())
                self.assertEqual(page.locator('#panel-'+tab.lower()+' [id^=ble-]').count(),0)
            self.assertFalse(any('/ble/' in call for call in calls))
            page.get_by_role('tab',name='BLE',exact=True).click()
            page.locator('#ble-device-rows .ble-label').first.wait_for()
            self.assertIn('Apple, Inc.',page.locator('#ble-device-rows').inner_text())
            self.assertIn('Static random',page.locator('#ble-device-rows').inner_text())
            self.assertEqual(page.locator('#ble-device-rows img').count(),0)
            self.assertTrue(page.locator('#ble-recent').evaluate('(node)=>!node.open'))
            page.locator('#ble-device-rows .mac-link').first.click()
            page.get_by_text('Random/private BLE address: vendor attribution and persistent identity are unavailable.',exact=True).wait_for()
            self.assertIn('004c',page.locator('#ble-details').inner_text())
            self.assertFalse(any('/api/mac/' in call for call in calls))
            page.keyboard.press('Escape')
            page.locator('#ble-device-rows .ble-label').first.click()
            page.wait_for_function("document.querySelector('#ble-range-values').textContent.includes('≈ 1.00 m')")
            self.assertIn('UNCALIBRATED',page.locator('#ble-model-message').inner_text())
            self.assertEqual(page.locator('#ble-range-plot polyline').count(),1)
            self.assertEqual(page.locator('#ble-range-plot circle').count(),1)
            # A new selection must clear the prior identity synchronously, before its fetch resolves.
            cleared=page.evaluate("key=>{selectBLE(key);return {count:bleState.samples.length,text:document.querySelector('#ble-range-values').textContent};}", json.dumps(['second',address,'random'],separators=(',',':')))
            self.assertEqual(cleared['count'],0)
            self.assertIn('Unavailable',cleared['text'])
            page.wait_for_function("document.querySelector('#ble-range-values').textContent.includes('≈ 10.0 m')")
            page.locator('#ble-advertiser').select_option(json.dumps(['c6',address,'random'],separators=(',',':')))
            page.wait_for_function("document.querySelector('#ble-range-values').textContent.includes('≈ 1.00 m')")
            page.locator('#ble-smoothing').fill('10');page.locator('#ble-smoothing').dispatch_event('change')
            self.assertIn('≈ 3.16 m',page.locator('#ble-range-values').inner_text())
            self.assertEqual(page.locator('#ble-range-plot circle').count(),2)
            page.locator('#ble-distance-max').fill('0.5');page.locator('#ble-distance-max').dispatch_event('change')
            self.assertIn('outside plotting range',page.locator('#ble-model-message').inner_text())
            self.assertEqual(page.locator('#ble-range-plot circle').count(),0)
            page.locator('#ble-exponent').fill('0');page.locator('#ble-exponent').dispatch_event('change')
            self.assertIn('finite values',page.locator('#ble-model-message').inner_text())
            self.assertEqual(page.locator('#ble-range-plot polyline').count(),0)
            page.locator('#ble-exponent').fill('2');page.locator('#ble-distance-max').fill('30');page.locator('#ble-distance-max').dispatch_event('change')
            page.locator('#ble-calibrated').check()
            self.assertIn('Operator-supplied',page.locator('#ble-model-message').inner_text())
            page.locator('#ble-alias').fill('Desk sensor');page.locator('#ble-notes').fill('Operator note')
            page.get_by_role('button',name='Save alias / notes',exact=True).click()
            self.assertIn('Enter the configuration key',page.locator('#ble-label-message').inner_text())
            page.locator('#ble-label-key').fill('test-key');page.get_by_role('button',name='Save alias / notes',exact=True).click()
            page.get_by_text('Operator label saved for this sensor/address/type only.',exact=True).wait_for()
            page.wait_for_function("document.querySelector('#ble-selected-label').textContent==='Desk sensor'")
            self.assertEqual(posts[-1]['sensor_id'],'c6')
            self.assertEqual(page.locator('#ble-label-key').input_value(),'')
            self.assertEqual(labels.get('second'),None)
            page.get_by_role('button',name='Pause updates',exact=True).click();calls.clear()
            page.locator('#ble-model-form button').click()
            self.assertFalse(calls)
            page.locator('#ble-advertiser').select_option(json.dumps(['second',address,'random'],separators=(',',':')))
            self.assertIn('Unavailable',page.locator('#ble-range-values').inner_text())
            self.assertFalse(calls)
            page.get_by_role('button',name='Refresh',exact=True).click()
            page.wait_for_function("document.querySelector('#ble-range-values').textContent.includes('≈ 10.0 m')")
            self.assertFalse(page.locator('#ble-calibrated').is_checked())
            self.assertEqual(page.locator('#ble-smoothing').input_value(),'0')
            self.assertEqual(page.locator('#ble-alias').input_value(),'')
            stale=True;page.get_by_role('button',name='Refresh',exact=True).click()
            page.wait_for_function("document.querySelector('#ble-model-message').textContent.includes('stale stored sample')")
            page.locator('#ble-search').fill('Desk sensor')
            page.wait_for_function("document.querySelectorAll('#ble-device-rows .ble-label').length===1")
            self.assertTrue(any('query=Desk' in call for call in calls))
            page.locator('#ble-search').fill('');page.locator('#ble-address-type').select_option('public')
            page.get_by_text('No advertisers match these filters. Check scan status or clear filters.',exact=True).wait_for()
            for width in (1920,2560):
                page.set_viewport_size({'width':width,'height':1440})
                layout=page.evaluate('''()=>{
                    const workspace=document.querySelector('.ble-workspace').getBoundingClientRect();
                    const panels=[...document.querySelectorAll('.ble-workspace>section')].map(node=>node.getBoundingClientRect());
                    const plot=document.querySelector('#ble-range-plot').getBoundingClientRect();
                    return {left:workspace.left,right:workspace.right,width:workspace.width,panels:panels.map(p=>({left:p.left,right:p.right,width:p.width})),plotWidth:plot.width,viewport:document.documentElement.clientWidth};
                }''')
                self.assertGreater(layout['width'],layout['viewport']*.95)
                self.assertGreater(layout['panels'][1]['width'],layout['panels'][0]['width'])
                self.assertGreater(layout['plotWidth'],layout['viewport']*.5)
                self.assertLessEqual(layout['panels'][1]['right'],layout['right']+1)
            page.set_viewport_size({'width':390,'height':844})
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            self.assertEqual(errors,[])
            browser.close()

    def test_distance_model_math_validation_missing_and_windowed_samples(self):
        html=(Path(__file__).parents[1]/'wids/static/index.html').read_text()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page()
            page.route('**/*',lambda request:request.fulfill(status=200,content_type='text/html' if '/api/' not in request.request.url else 'application/json',body=html if '/api/' not in request.request.url else '{}'))
            page.goto('http://dashboard.test')
            result=page.evaluate('''()=>{
                const options={reference:-59,exponent:2,minimum:0.1,maximum:30,smoothing:0};
                const now=Date.now(),row={id:1,rssi:-59,timestamp:new Date(now).toISOString()};
                const a=bleModel([row],options,now),b=bleModel([{...row,rssi:-79}],options,now);
                const empty=bleModel([],options,now),old=bleModel([{...row,timestamp:new Date(now-120000).toISOString()}],{...options,smoothing:10},now);
                const invalid=[{exponent:0},{exponent:NaN},{reference:Infinity},{minimum:0},{maximum:0.01},{smoothing:-1},{smoothing:1.5}].map(patch=>{try{bleModel([],{...options,...patch},now);return false;}catch{return true;}});
                return {a:a.distance,b:b.distance,empty:empty.distance,old:old.distance,stale:old.stale,invalid};
            }''')
            self.assertAlmostEqual(result['a'],1)
            self.assertAlmostEqual(result['b'],10)
            self.assertIsNone(result['empty'])
            self.assertIsNone(result['old'])
            self.assertTrue(result['stale'])
            self.assertTrue(all(result['invalid']))
            browser.close()
