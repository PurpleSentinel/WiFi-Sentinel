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
            'health': {'serial_enabled': True},
            'alert-sources': {'macs': [], 'legacy_alerts_without_sources': 0},
            'summary': {'frames_24h': 12, 'alerts_24h': 2, 'sensors': 1,
                        'by_subtype': [{'subtype': 'beacon', 'count': 12}]},
            'channels': [{'channel': 6, 'count': 12}],
            'alerts?limit=200': [] if self.empty else alerts,
            'frames?limit=100': [] if self.empty else [{
                'timestamp': '2026-10-24T14:00:00Z', 'subtype': 'beacon',
                'sa': '02:11:22:33:44:55', 'bssid': '02:11:22:33:44:55',
                'rssi': -40, 'channel': 6, 'protected': False, 'ssid': 'Office'}],
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
                         ['Overview', 'Alerts', 'Reporting', 'Devices'])
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
        for name in ('Overview', 'Alerts', 'Reporting', 'Devices'):
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
        page.wait_for_function("document.querySelector('#panel-devices').getAttribute('aria-busy') === 'false'")
        self.assertEqual(page.locator(':focus').inner_text(), 'Devices')
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
        for name in ('Overview', 'Alerts', 'Reporting', 'Devices'):
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
