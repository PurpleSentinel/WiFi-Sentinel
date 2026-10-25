"""Optional browser coverage for MAC lookup, red alert sources and nested dialogs."""
import json
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


class MacDetails(unittest.TestCase):
    def test_clicks_highlighting_details_failures_and_mobile(self):
        source = '00:11:22:33:44:01'
        bssid = '60:98:49:0d:d5:7a'
        sources = {'macs': [source], 'legacy_alerts_without_sources': 1}
        alerts = [{'timestamp': '2026-10-24T14:00:00Z', 'severity': 'high', 'rule': 'deauth_flood',
                   'sensor_id': 'c6', 'bssid': bssid, 'channel': 6, 'frame_count': 20,
                   'details': 'Observed burst from ' + source, 'source_macs': [source],
                   'association': 'Contributing source'}]
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        vendor_status = 'found'
        vendor_failure = False
        errors = []
        calls = []
        def route(request):
            if '/api/' not in request.request.url:
                request.fulfill(status=200, content_type='text/html', body=html)
                return
            path = request.request.url.split('/api/')[1]
            calls.append(path)
            if path.startswith('mac/'):
                mac = path.split('/')[1].replace('%3A', ':')
                if '/vendor' in path:
                    if vendor_failure:
                        request.fulfill(status=503, content_type='application/json', body='{"detail":"Offline"}')
                        return
                    data = {'mac': mac, 'status': vendor_status, 'cached': True, 'stale': False,
                            'looked_up_at': '2026-10-24T14:00:00Z', 'error': None,
                            'registry': {'retrieved_at': '2026-10-24'},
                            'registration': {'vendorName': '<img src=x onerror=alert(1)>',
                                             'macPrefix': '00:11:22', 'blockType': 'MA-L'},
                            'additional_details': {'company': 'Vendor', 'country': 'GB'}}
                else:
                    data = {'mac': mac, 'alert_sources': sources, 'observations': {
                        'classification': {'role': 'Client / Host', 'role_code': 'client', 'evidence': ['Association requests sent: 20'], 'window_hours': 24},
                        'roles': ['Source'], 'ssids': [], 'ssid_hex_values': ['436166c3a9'], 'bssids': [bssid], 'channels': [6],
                        'sensor_ids': ['c6'], 'first_seen': '2026-10-24', 'last_seen': '2026-10-24',
                        'frame_count': 20, 'alerts': alerts}}
            else:
                data = {
                    'alert-sources': sources,
                    'health': {'serial_enabled': True},
                    'summary': {'frames_24h': 20, 'alerts_24h': 1, 'sensors': 1, 'by_subtype': []},
                    'channels': [], 'alerts?limit=200': alerts,
                    'frames?limit=100': [{'timestamp': '2026-10-24', 'subtype': 'deauth',
                        'sa': source, 'bssid': bssid, 'rssi': -40, 'channel': 6, 'protected': False, 'ssid': None}],
                    'devices?limit=200': {'devices': [{'mac': source, 'role': 'Client / Host', 'role_code': 'client', 'evidence': ['Association requests sent: 20'],
                        'ssids': [], 'bssids': [bssid], 'channels': [6], 'last_seen': '2026-10-24',
                        'frame_count': 20, 'sensor_ids': ['c6']}], 'has_more': False},
                    'sensors': [],
                    'configuration': {'collector': {'trusted_bssids': [source],
                        'serial_port': '/dev/serial/by-id/usb-board_' + source + '-if00'},
                        'lists': ['trusted_bssids'], 'limits': {}, 'restart_fields': ['serial_port'],
                        'sensor': {'connected': False, 'configuration': None}},
                }[path]
            request.fulfill(status=200, content_type='application/json', body=json.dumps(data))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.route('**/*', route)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://dashboard.test')
            for name in ('Overview', 'Alerts', 'Reporting', 'Devices'):
                page.get_by_role('tab', name=name, exact=True).click()
                panel = page.locator('#panel-' + name.lower())
                red = panel.locator(f'.mac-link[data-mac="{source}"]').first
                red.wait_for()
                self.assertIn('alert-source', red.get_attribute('class'))
                self.assertIn('alert-associated source', red.get_attribute('aria-label'))
                self.assertNotIn('alert-source', panel.locator(f'.mac-link[data-mac="{bssid}"]').first.get_attribute('class'))
                red.click()
                page.get_by_text('Vendor registration found.', exact=True).wait_for()
                self.assertEqual(page.locator('#mac-vendor-details img').count(), 0)
                self.assertIn('<img src=x onerror=alert(1)>', page.locator('#mac-vendor-details').inner_text())
                self.assertIn('Unknown / not observed', page.locator('#mac-local-details').inner_text())
                self.assertIn('Client / Host', page.locator('#mac-local-details').inner_text())
                self.assertIn('Association requests sent: 20', page.locator('#mac-local-details').inner_text())
                self.assertIn('436166c3a9', page.locator('#mac-local-details').inner_text())
                self.assertIn('alert-source', page.locator('#mac-address .mac-link').get_attribute('class'))
                page.keyboard.press('Escape')
                self.assertEqual(page.locator(':focus').get_attribute('data-mac'), source)
            page.get_by_role('button', name='Configuration', exact=True).click()
            config_mac = page.locator('#configuration-dialog .mac-link').first
            config_mac.wait_for()
            self.assertEqual(page.locator('#configuration-dialog .mac-link').count(), 2)
            config_mac.click()
            self.assertTrue(page.locator('#configuration-dialog').is_visible())
            page.get_by_text('Vendor registration found.', exact=True).wait_for()
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('data-mac'), source)
            page.keyboard.press('Escape')
            vendor_failure = True
            page.locator('#panel-devices .mac-link').first.click()
            page.get_by_text('Vendor lookup failed: Offline. Local observations remain available.', exact=True).wait_for()
            self.assertIn('Retained frames', page.locator('#mac-local-details').inner_text())
            vendor_failure = False
            vendor_status = 'locally_administered'
            page.get_by_role('button', name='Retry / refresh vendor details').click()
            page.wait_for_function("document.querySelector('#mac-vendor-message').textContent.includes('Locally administered')")
            self.assertTrue(any('?refresh=true' in call for call in calls))
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertTrue(page.locator('#mac-dialog').evaluate('(node) => node.scrollWidth <= node.clientWidth'))
            page.keyboard.press('Escape')
            sources['macs'] = []
            page.get_by_role('button', name='Refresh', exact=True).click()
            page.wait_for_function("document.querySelectorAll('.mac-link.alert-source').length === 0")
            self.assertEqual(errors, [])
            browser.close()
