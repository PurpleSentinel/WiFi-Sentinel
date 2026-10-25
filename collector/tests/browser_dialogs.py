"""Optional browser checks: python -m unittest discover -s collector/tests -p browser_*.py.

Requires Playwright and its Chromium browser. Network responses are mocked;
these checks do not reconfigure a real sensor.
"""
import json
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


class DashboardDialogs(unittest.TestCase):
    def test_configuration_and_status(self):
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        sensor = {'connected': True, 'configuration': {
            'values': {'sensor_id': 'c6', 'band': '2.4', 'channel': 6,
                       'beacon_sample_n': 20, 'heartbeat_seconds': 15},
            'capabilities': {'chip': 'esp32c6', 'console': 'USB Serial/JTAG',
                             'country': '01', 'bands': ['2.4'],
                             'beacon_sampling': 'per_bssid_channel_subtype', 'beacon_sampling_capacity': 64,
                             'channels': {'2.4': [1, 6, 11]}}}}
        config = {'sensor': sensor, 'collector': {
            'window_seconds': 10, 'protected_ssids': ['Office'],
            'host': '10.0.0.2', 'port': 8181},
            'limits': {'window_seconds': [1, 3600]}, 'lists': ['protected_ssids'],
            'restart_fields': ['host', 'port']}
        rows = [{'sensor_id': 'c6', 'last_seen': '2026-10-24T14:00:00+00:00',
                 'channel': 6, 'uptime_ms': 15000, 'dropped': 0},
                {'sensor_id': 'other', 'last_seen': '2026-10-24T13:00:00+00:00',
                 'channel': 1, 'uptime_ms': 20000, 'dropped': 1}]
        calls = []
        fail_status = False
        errors = []
        def route(request):
            path = request.request.url.split('/api/')[-1]
            status = 200
            if '/api/' not in request.request.url:
                request.fulfill(status=200, content_type='text/html', body=html)
                return
            if request.request.method == 'POST':
                body = request.request.post_data_json
                calls.append((path, body))
                if request.request.headers.get('x-configuration-key') != 'test-key':
                    status, data = 403, {'detail': 'A valid configuration key is required'}
                elif path.endswith('/sensor'):
                    sensor['configuration']['values'].update(body)
                    data = sensor
                else:
                    config['collector'].update(body)
                    data = config
            elif path == 'configuration':
                data = config
            elif path == 'alert-sources':
                data = {'macs': [], 'legacy_alerts_without_sources': 0}
            elif path == 'sensors':
                status, data = (503, {'detail': 'Sensor data unavailable'}) if fail_status else (200, rows)
            else:
                data = {'health': {'serial_enabled': True},
                        'summary': {'frames_24h': 3, 'alerts_24h': 0, 'sensors': 2,
                                    'by_subtype': []},
                        'channels': [], 'alerts?limit=200': [], 'frames?limit=100': []}[path]
            request.fulfill(status=status, content_type='application/json', body=json.dumps(data))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            context = browser.new_context()
            context.route('**/*', route)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://dashboard.test')
            self.assertFalse(page.locator('#status-dialog').is_visible())
            self.assertEqual(page.locator('main #sensor-rows').count(), 0)
            page.get_by_role('button', name='Status', exact=True).click()
            page.wait_for_function("document.querySelectorAll('#sensor-rows tr').length === 2")
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'), 'status')
            page.get_by_role('button', name='Pause updates').click()
            page.get_by_role('button', name='Status', exact=True).click()
            page.wait_for_function("document.querySelector('#status-message').textContent.includes('paused')")
            page.get_by_role('button', name='Close', exact=True).click()
            rows.clear()
            page.get_by_role('button', name='Status', exact=True).click()
            page.get_by_text('No connected or simulated sensors', exact=True).wait_for()
            page.keyboard.press('Escape')
            fail_status = True
            page.get_by_role('button', name='Status', exact=True).click()
            page.get_by_text('Could not load sensor status: Sensor data unavailable', exact=True).wait_for()
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Configuration', exact=True).click()
            page.locator('#sensor-channel').wait_for()
            self.assertEqual(page.locator('#sensor-band option').all_text_contents(), ['2.4'])
            self.assertIn('Per-AP sampling', page.locator('#sensor-description').inner_text())
            self.assertTrue(page.locator('#restart-host').evaluate('(node) => node.readOnly'))
            page.locator('#sensor-channel').select_option('11')
            page.get_by_role('button', name='Apply sensor settings').click()
            self.assertEqual(len(calls), 0)
            page.locator('#configuration-key').fill('wrong')
            page.get_by_role('button', name='Apply sensor settings').click()
            page.get_by_text('A valid configuration key is required', exact=True).wait_for()
            page.locator('#configuration-key').fill('test-key')
            page.get_by_role('button', name='Apply sensor settings').click()
            page.get_by_text('Sensor confirmed the settings and saved them on the device.', exact=True).wait_for()
            self.assertEqual(sensor['configuration']['values']['channel'], 11)
            page.locator('#collector-window_seconds').fill('20')
            page.get_by_role('button', name='Save collector settings').click()
            page.get_by_text('Collector settings saved and applied.', exact=True).wait_for()
            self.assertEqual(config['collector']['window_seconds'], 20)
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'), 'configuration')
            self.assertEqual(page.locator('#configuration-key').input_value(), '')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.get_by_role('button', name='Configuration', exact=True).click()
            page.locator('#sensor-channel').wait_for()
            self.assertTrue(page.locator('#configuration-dialog').evaluate('(node) => node.scrollWidth <= node.clientWidth'))
            self.assertEqual(errors, [])
            browser.close()
