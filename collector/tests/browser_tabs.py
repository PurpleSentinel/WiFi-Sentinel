"""Optional Playwright checks for dashboard tabs and reduced-motion branding."""
import json
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


class DashboardTabs(unittest.TestCase):
    def setUp(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        self.context = self.browser.new_context()
        self.calls = []
        self.fail = None
        self.empty = False
        self.errors = []
        self.html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.clock.install()
        self.page.goto('http://dashboard.test')
        self.page.wait_for_function("document.querySelector('#frames').textContent === '12'")

    def tearDown(self):
        self.browser.close()
        self.playwright.stop()

    def route(self, route):
        url = route.request.url
        if '/api/' not in url:
            route.fulfill(status=200, content_type='text/html', body=self.html)
            return
        path = url.split('/api/')[1]
        self.calls.append(path)
        if path == self.fail:
            route.fulfill(status=503, content_type='application/json', body='{"detail":"Unavailable"}')
            return
        alerts = [{'timestamp': '2026-10-24T14:00:00Z', 'severity': severity,
                   'rule': 'disassoc_flood', 'sensor_id': 'c6', 'bssid': '02:11:22:33:44:55',
                   'channel': 6, 'frame_count': 20, 'details': 'Observed burst'}
                  for severity in ('high', 'medium')]
        data = {
            'ble/observations?limit=100': [], 'ble/devices?limit=200': {'devices': [], 'has_more': False},
                    'health': {'serial_enabled': True},
            'alert-sources': {'macs': [], 'legacy_alerts_without_sources': 0},
            'summary': {'frames_24h': 12, 'alerts_24h': 2, 'sensors': 1,
                        'by_subtype': [{'subtype': 'beacon', 'count': 12}]},
            'channels': [{'channel': 6, 'count': 12}],
            'alerts?limit=200': [] if self.empty else alerts,
            'frames?limit=100': [] if self.empty else [{
                'timestamp': '2026-10-24T14:00:00Z', 'subtype': 'beacon',
                'sa': '02:11:22:33:44:55', 'bssid': '02:11:22:33:44:55',
                'rssi': -40, 'channel': 6, 'protected': False, 'ssid': 'Café', 'ssid_hex': '436166c3a9'}],
            'devices?limit=200': {'window_hours': 24, 'limit': 200, 'has_more': False,
                'devices': [] if self.empty else [{
                    'mac': '02:11:22:33:44:55', 'role': 'Access Point', 'role_code': 'access_point',
                    'evidence': ['Beacon advertisements sent: 12'],
                    'ssids': ['<img src=x onerror=alert(1)>'], 'bssids': ['02:11:22:33:44:55'],
                    'channels': [6], 'last_seen': '2026-10-24T14:00:00Z',
                    'frame_count': 12, 'sensor_ids': ['c6']}]},
            'sensors': [],
            'configuration': {'collector': {'window_seconds': 10},
                'limits': {'window_seconds': [1, 3600]}, 'lists': [], 'restart_fields': [],
                'sensor': {'connected': False, 'configuration': None}},
        }[path.split('&role=')[0]]
        if path.startswith('devices?') and not self.empty:
            base = data['devices'][0]
            data['devices'] += [{**base, 'mac': mac, 'role': label, 'role_code': code, 'evidence': evidence, 'ssids': []}
                for mac, label, code, evidence in [
                    ('02:00:00:00:00:02', 'Client / Host', 'client', ['Association requests sent: 1']),
                    ('02:00:00:00:00:03', 'Mixed (AP + Client)', 'mixed', ['Beacon advertisements sent: 1', 'Reassociation requests sent: 1']),
                    ('02:00:00:00:00:04', 'Unknown', 'unknown', ['Insufficient subtype/address evidence in the last 24 hours'])]]
            if '&role=' in path:
                code = path.split('&role=')[1]
                data['devices'] = [row for row in data['devices'] if row['role_code'] == code]
                data['role'] = code
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    def select(self, name):
        self.page.get_by_role('tab', name=name, exact=True).click()
        self.page.wait_for_function(
            "name => document.querySelector('#panel-' + name).getAttribute('aria-busy') === 'false'",
            arg=name.lower())

    def test_tabs_polling_pause_filters_and_dialogs(self):
        page = self.page
        self.assertEqual(page.get_by_role('tab').all_text_contents(),
                         ['Overview', 'Alerts', 'Reporting', 'Devices', 'BLE'])
        self.assertEqual(page.get_by_role('tab', selected=True).inner_text(), 'Overview')
        self.assertNotIn('devices?limit=200', self.calls)
        self.assertNotIn('frames?limit=100', self.calls)
        self.select('Alerts')
        page.locator('#severity').select_option('high')
        self.assertEqual(page.locator('#alert-rows tr').count(), 1)
        self.calls.clear()
        page.clock.run_for(5100)
        page.wait_for_function("document.querySelector('#panel-alerts').getAttribute('aria-busy') === 'false'")
        self.assertIn('alerts?limit=200', self.calls)
        self.assertNotIn('frames?limit=100', self.calls)
        self.assertNotIn('devices?limit=200', self.calls)
        self.select('Reporting')
        self.assertEqual(page.locator('#frame-rows tr').count(), 1)
        self.assertIn('Café', page.locator('#frame-rows').inner_text())
        self.select('Devices')
        self.assertIn('<img src=x onerror=alert(1)>', page.locator('#device-rows').inner_text())
        self.assertEqual(page.locator('#device-rows img').count(), 0)
        page.get_by_role('button', name='Pause updates').click()
        self.calls.clear()
        page.clock.run_for(6000)
        self.assertEqual(self.calls, [])
        page.get_by_role('tab', name='Alerts', exact=True).click()
        self.assertEqual(self.calls, [])
        self.assertEqual(page.locator('#severity').input_value(), 'high')
        page.get_by_role('button', name='Refresh', exact=True).click()
        page.wait_for_function("document.querySelector('#panel-alerts').getAttribute('aria-busy') === 'false'")
        self.assertEqual(page.get_by_role('tab', selected=True).inner_text(), 'Alerts')
        self.assertEqual(page.locator('#severity').input_value(), 'high')
        with page.expect_download() as download:
            page.get_by_role('button', name='Export alert JSON').click()
        self.assertEqual(download.value.suggested_filename, 'wifi-sentinel-alerts.json')
        for name in ('Overview', 'Alerts', 'Reporting', 'Devices', 'BLE'):
            self.select(name)
            page.get_by_role('button', name='Status', exact=True).click()
            page.get_by_text('No connected or simulated sensors', exact=True).wait_for()
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Configuration', exact=True).click()
            page.locator('#collector-window_seconds').wait_for()
            page.keyboard.press('Escape')
            self.assertEqual(page.get_by_role('tab', selected=True).inner_text(), name)
        self.assertEqual(self.errors, [])

    def test_keyboard_mobile_motion_and_error_states(self):
        page = self.page
        page.get_by_role('tab', name='Overview', exact=True).focus()
        page.keyboard.press('End')
        page.wait_for_function("document.querySelector('#panel-ble').getAttribute('aria-busy') === 'false'")
        self.assertEqual(page.locator(':focus').inner_text(), 'BLE')
        page.keyboard.press('Home')
        self.assertEqual(page.locator(':focus').inner_text(), 'Overview')
        page.keyboard.press('ArrowRight')
        self.assertEqual(page.locator(':focus').inner_text(), 'Alerts')
        self.assertEqual(page.locator('.orb').evaluate(
            "node => getComputedStyle(node, '::before').animationName"), 'sentinel-pulse')
        page.emulate_media(reduced_motion='reduce')
        self.assertEqual(page.locator('.orb').evaluate(
            "node => getComputedStyle(node, '::before').animationName"), 'none')
        self.fail = 'devices?limit=200'
        self.select('Devices')
        self.assertIn('Could not update devices: Unavailable', page.locator('#devices-message').inner_text())
        self.fail = None
        self.empty = True
        self.select('Devices')
        self.assertIn('No device addresses observed', page.locator('#device-rows').inner_text())
        self.select('Reporting')
        self.assertIn('No frames received', page.locator('#frame-rows').inner_text())
        self.select('Alerts')
        self.assertIn('No matching alerts', page.locator('#alert-rows').inner_text())
        page.set_viewport_size({'width': 390, 'height': 844})
        for name in ('Overview', 'Alerts', 'Reporting', 'Devices', 'BLE'):
            self.select(name)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    def test_role_filter_evidence_and_paused_behavior(self):
        page = self.page
        self.select('Devices')
        self.assertEqual(page.locator('#device-rows tr').count(), 4)
        for code, label in [('access_point', 'Access Point'), ('client', 'Client / Host'),
                            ('mixed', 'Mixed (AP + Client)'), ('unknown', 'Unknown')]:
            page.locator('#device-role').select_option(code)
            page.wait_for_function("document.querySelector('#panel-devices').getAttribute('aria-busy') === 'false'")
            self.assertEqual(page.locator('#device-rows tr').count(), 1)
            self.assertEqual(page.locator('#device-rows .role-badge').inner_text(), label)
            self.assertIn('devices?limit=200&role=' + code, self.calls)
            self.assertTrue(page.locator('#device-rows .role-evidence').inner_text())
        page.get_by_role('button', name='Pause updates').click()
        self.calls.clear()
        page.locator('#device-role').select_option('client')
        self.assertEqual(self.calls, [])
        self.assertIn('filtering loaded observations only', page.locator('#devices-message').inner_text())
        page.get_by_role('button', name='Refresh', exact=True).click()
        page.wait_for_function("document.querySelector('#panel-devices').getAttribute('aria-busy') === 'false'")
        self.assertEqual(page.locator('#device-rows .role-badge').inner_text(), 'Client / Host')
        self.select('Overview')
        self.select('Devices')
        self.assertEqual(page.locator('#device-role').input_value(), 'client')
        self.assertEqual(page.locator('#device-rows .role-badge').inner_text(), 'Client / Host')
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors, [])

    def test_full_width_desktop_and_contained_narrow_layouts(self):
        page = self.page
        for width in (1920, 2560, 768, 390, 320):
            page.set_viewport_size({'width': width, 'height': 1080 if width > 1000 else 844})
            for name in ('Overview', 'Alerts', 'Reporting', 'Devices', 'BLE'):
                self.select(name)
                bounds = page.evaluate('''() => {
                    const tab = document.querySelector('[role=tabpanel]:not([hidden])').getBoundingClientRect();
                    const brand = document.querySelector('.brand').getBoundingClientRect();
                    const main = document.querySelector('main').getBoundingClientRect();
                    return {viewport:document.documentElement.clientWidth, page:document.documentElement.scrollWidth,
                            mainWidth:main.width, left:tab.left, right:tab.right, brandLeft:brand.left};
                }''')
                self.assertLessEqual(bounds['page'], width)
                self.assertAlmostEqual(bounds['mainWidth'], bounds['viewport'], delta=1)
                self.assertAlmostEqual(bounds['left'], bounds['brandLeft'], delta=1)
                self.assertAlmostEqual(bounds['viewport'] - bounds['right'], bounds['left'], delta=1)
                if width >= 1920:
                    self.assertLessEqual(bounds['left'], 36)
                    self.assertGreater(bounds['right'] - bounds['left'], bounds['viewport'] * .95)
            page.get_by_role('button', name='Configuration', exact=True).click()
            page.locator('#collector-window_seconds').wait_for()
            self.assertTrue(page.locator('#configuration-dialog').evaluate(
                '(node) => node.getBoundingClientRect().width <= innerWidth && node.scrollWidth <= node.clientWidth'))
            page.keyboard.press('Escape')
        self.assertEqual(self.errors, [])

    def test_many_bssid_contexts_keep_table_bounded_and_remain_accessible(self):
        page = self.page
        self.select('Devices')
        page.get_by_role('button', name='Pause updates', exact=True).click()
        page.evaluate('''() => {
            const addresses=Array.from({length:80},(_,i)=>'02:aa:00:00:00:'+i.toString(16).padStart(2,'0'));
            deviceData.devices[0].bssids=addresses;
            setAlertSources({macs:[addresses[5]],legacy_alerts_without_sources:0});
            displayDevices(deviceData);
        }''')
        self.assertEqual(page.locator('#device-rows tr').first.locator('.device-bssids .mac-link').count(), 2)
        more=page.get_by_role('button',name='View all 80 observed BSSID contexts for 02:11:22:33:44:55',exact=True)
        for width in (1280,1920,2560):
            page.set_viewport_size({'width':width,'height':1080})
            dimensions=page.locator('#device-table').evaluate(
                '(table)=>({width:table.getBoundingClientRect().width,content:table.scrollWidth,container:table.parentElement.clientWidth})')
            self.assertLessEqual(dimensions['width'],dimensions['container']+1)
            self.assertLessEqual(dimensions['content'],dimensions['container']+1)
        page.set_viewport_size({'width':390,'height':844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        more.click()
        page.locator('#device-context-list li').first.wait_for()
        self.assertEqual(page.locator('#device-context-list .mac-link').count(),80)
        self.assertIn('80 of 80',page.locator('#device-context-count').inner_text())
        marked=page.locator('#device-context-list [data-mac="02:aa:00:00:00:05"]')
        self.assertIn('alert-source',marked.get_attribute('class'))
        page.locator('#device-context-search').fill('00:05')
        self.assertEqual(page.locator('#device-context-list .mac-link').count(),1)
        self.assertIn('1 of 80',page.locator('#device-context-count').inner_text())
        self.assertTrue(page.locator('#device-context-dialog').evaluate('(node)=>node.scrollWidth<=node.clientWidth'))
        page.locator('#device-context-search').fill('not-an-address')
        self.assertIn('No matching BSSID contexts',page.locator('#device-context-list').inner_text())
        page.keyboard.press('Escape')
        page.wait_for_function("!document.querySelector('#device-context-dialog').open && document.activeElement.classList.contains('device-context-more')")
        self.assertEqual(page.locator(':focus').get_attribute('class'),'device-context-more')
        self.assertEqual(self.errors,[])

    def test_device_column_sorting_numeric_dates_and_persistence(self):
        page=self.page
        self.select('Devices')
        page.get_by_role('button',name='Pause updates',exact=True).click()
        page.evaluate('''()=>{
            const base=deviceData.devices[0];
            deviceData.devices=[
              {...base,mac:'02:00:00:00:00:01',frame_count:100,last_seen:'2026-10-25T02:00:00Z',channels:[11],ssids:['Zoo'],bssids:['02:00:00:00:10:01','02:00:00:00:10:02']},
              {...base,mac:'02:00:00:00:00:02',frame_count:2,last_seen:'2026-10-25T01:00:00Z',channels:[2],ssids:['Alpha'],bssids:['02:00:00:00:10:01']},
              {...base,mac:'02:00:00:00:00:03',frame_count:10,last_seen:'2026-10-25T03:00:00Z',channels:[6],ssids:['Middle'],bssids:[]}
            ];displayDevices(deviceData);
        }''')
        def addresses():return page.locator('#device-rows tr td:first-child .mac-link').all_text_contents()
        frames=page.locator('[data-device-sort="frame_count"]')
        frames.click()
        self.assertEqual([mac[-2:] for mac in addresses()],['02','03','01'])
        self.assertEqual(frames.locator('..').get_attribute('aria-sort'),'ascending')
        self.assertIn('active',frames.locator('.sort-up').get_attribute('class'))
        frames.press('Enter')
        self.assertEqual([mac[-2:] for mac in addresses()],['01','03','02'])
        self.assertEqual(frames.locator('..').get_attribute('aria-sort'),'descending')
        page.evaluate('displayDevices(deviceData)')
        self.assertEqual([mac[-2:] for mac in addresses()],['01','03','02'])
        page.locator('[data-device-sort="last_seen"]').click()
        self.assertEqual([mac[-2:] for mac in addresses()],['02','01','03'])
        page.locator('[data-device-sort="channels"]').click()
        self.assertEqual([mac[-2:] for mac in addresses()],['02','03','01'])
        page.locator('[data-device-sort="ssids"]').click()
        self.assertEqual([mac[-2:] for mac in addresses()],['02','03','01'])
        page.locator('[data-device-sort="bssids"]').click()
        self.assertEqual([mac[-2:] for mac in addresses()],['03','02','01'])
        self.assertIn('loaded rows only',page.locator('#devices-message').inner_text())
        self.assertEqual(page.locator('#device-table [data-device-sort]').count(),9)
        for key in ('mac','role','evidence','sensor_ids'):
            page.locator('[data-device-sort="'+key+'"]').click()
            self.assertEqual(page.locator('#device-table th[aria-sort="ascending"]').count(),1)
        self.assertEqual(self.errors,[])
