"""BLE UI regression: protocol separation, safe rendering and random-address privacy."""
import json
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


class BLEBrowser(unittest.TestCase):
    def test_ble_views_configuration_status_and_private_details(self):
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        address = 'cc:bb:aa:11:22:33'  # Even a global-looking prefix is private when BLE says random.
        item = {'address': address, 'address_type': 'random', 'sensor_id': 'c6',
                'timestamp': '2026-10-25T00:00:00Z', 'last_seen': '2026-10-25T00:00:00Z',
                'local_name': '<img src=x onerror=alert(1)>', 'service_uuids': ['180f'],
                'manufacturer_data': [{'company_id': '004c', 'data_hex': '01'}],
                'service_data': [], 'payload_hex': '04ff4c0001', 'rssi': -55,
                'observation_count': 2, 'event_type': 0, 'ad_malformed': False}
        sensor = {'connected': True, 'configuration': {
            'values': {'sensor_id': 'c6', 'band': '2.4', 'channel': 6, 'beacon_sample_n': 20,
                       'heartbeat_seconds': 15, 'ble_enabled': True, 'ble_interval_ms': 100, 'ble_window_ms': 20},
            'capabilities': {'chip': 'esp32c6', 'console': 'USB Serial/JTAG', 'bands': ['2.4'],
                             'channels': {'2.4': [6]}, 'ble': True},
            'ble_status': {'scanning': True, 'captured': 20, 'dropped': 3, 'error': 0}}}
        config = {'sensor': sensor, 'collector': {'ble_retention_days': 7, 'ble_filters': [], 'ble_alert_rules': []},
                  'limits': {'ble_retention_days': [1, 3650]}, 'lists': ['ble_filters', 'ble_alert_rules'], 'restart_fields': []}
        calls, posts, errors = [], [], []
        def route(request):
            path = request.request.url.split('/api/')[-1]
            if '/api/' not in request.request.url:
                request.fulfill(status=200, content_type='text/html', body=html)
                return
            calls.append(path)
            if request.request.method == 'POST':
                posts.append(request.request.post_data_json)
                sensor['configuration']['values'].update(posts[-1])
                data = sensor
            elif path.startswith('ble/observations'):
                data = [item]
            else:
                data = {'health': {'serial_enabled': True}, 'alert-sources': {'macs': [address], 'legacy_alerts_without_sources': 0},
                    'summary': {'frames_24h': 1, 'alerts_24h': 1, 'sensors': 1, 'by_subtype': [], 'ble_observations_24h': 2},
                    'channels': [], 'frames?limit=100': [], 'devices?limit=200': {'devices': [], 'has_more': False},
                    'ble/devices?limit=200': {'devices': [item], 'has_more': False},
                    'alerts?limit=200': [{'timestamp': item['timestamp'], 'severity': 'medium', 'rule': 'ble_match',
                        'sensor_id': 'c6', 'source_macs': [address], 'protocol': 'ble', 'address_type': 'random',
                        'bssid': None, 'channel': None, 'frame_count': 1, 'details': 'BLE advertisement matched company:004c'}],
                    'sensors': [], 'configuration': config}[path]
            request.fulfill(status=200, content_type='application/json', body=json.dumps(data))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.route('**/*', route)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://dashboard.test')
            self.assertEqual(page.get_by_role('tab').all_text_contents(), ['Overview', 'Alerts', 'Reporting', 'Devices', 'BLE'])
            for tab in ('Reporting', 'Devices'):
                page.get_by_role('tab', name=tab, exact=True).click()
                page.wait_for_function("name => document.querySelector('#panel-'+name).getAttribute('aria-busy') === 'false'", arg=tab.lower())
                self.assertEqual(page.locator('#panel-'+tab.lower()+' [id^=ble-]').count(), 0)
            self.assertFalse(any(path.startswith('ble/') for path in calls))
            page.get_by_role('tab', name='BLE', exact=True).click()
            page.wait_for_function("document.querySelector('#ble-overview').textContent.includes('24h: 2')")
            for tab, body in [('BLE', 'ble-report-rows'), ('BLE', 'ble-device-rows')]:
                page.get_by_role('tab', name=tab, exact=True).click()
                page.locator('#'+body+' .mac-link').wait_for()
                self.assertIn('BLE · random', page.locator('#'+body).inner_text())
                self.assertIn(item['local_name'], page.locator('#'+body).inner_text())
                self.assertEqual(page.locator('#'+body+' img').count(), 0)
                self.assertIn('alert-source', page.locator('#'+body+' .mac-link').get_attribute('class'))
                page.locator('#'+body+' .mac-link').click()
                page.get_by_text('Random/private BLE address: vendor attribution and persistent identity are unavailable.', exact=True).wait_for()
                self.assertIn('004c', page.locator('#ble-details').inner_text())
                self.assertIn('04ff4c0001', page.locator('#ble-details').inner_text())
                self.assertFalse(any(path.startswith('mac/') for path in calls))
                page.keyboard.press('Escape')
                self.assertEqual(page.locator(':focus').get_attribute('data-mac'), address)
            page.get_by_role('button', name='Status', exact=True).click()
            page.wait_for_function("document.querySelector('#ble-status').textContent.includes('scanning passively')")
            self.assertIn('rate-limited 3', page.locator('#ble-status').inner_text())
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Configuration', exact=True).click()
            page.locator('#sensor-ble_enabled').wait_for()
            self.assertTrue(page.locator('#sensor-ble_enabled').is_checked())
            page.locator('#sensor-ble_enabled').uncheck()
            page.locator('#configuration-key').fill('test-key')
            page.get_by_role('button', name='Apply sensor settings').click()
            page.get_by_text('Sensor confirmed the settings and saved them on the device.', exact=True).wait_for()
            self.assertIs(posts[0]['ble_enabled'], False)
            self.assertEqual(posts[0]['channel'], 6)
            self.assertEqual(posts[0]['ble_interval_ms'], 100)
            page.keyboard.press('Escape')
            self.assertEqual(errors, [])
            browser.close()
