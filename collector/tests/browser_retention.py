"""Automatic retention dialog, preview and policy-save browser behavior."""
import json
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright


class RetentionDialog(unittest.TestCase):
    def test_retention_window_preview_save_pause_mobile_focus(self):
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        policy = {'wifi_age_hours': 168, 'ble_age_hours': 168, 'automatic_age_deletion': True,
                  'cleanup_interval_seconds': 60, 'ble_max_records': 100000}
        sources = dict.fromkeys(policy, 'default')
        status = {'running': False, 'last_run_at': None, 'last_deleted': {}, 'last_error': None,
                  'next_run_at': '2026-10-26T13:00:00+00:00'}
        calls, errors = [], []
        def route(request):
            path = request.request.url.split('/api/')[-1]
            if '/api/' not in request.request.url:
                request.fulfill(content_type='text/html', body=html)
                return
            calls.append((path, request.request.method))
            code = 200
            if path == 'retention':
                data = {'policy': policy, 'sources': sources, 'status': status}
            elif path == 'retention/preview':
                new = request.request.post_data_json
                destructive = new['wifi_age_hours'] < policy['wifi_age_hours'] or new['ble_max_records'] < policy['ble_max_records']
                data = {'token': 'retention-preview', 'policy': new, 'current_policy': policy,
                        'destructive': destructive, 'cutoffs': dict.fromkeys(['frames','alerts','ble_observations','ble_alerts'], '2026-10-25T12:00:00+00:00'),
                        'counts': {table: {'total': 100, 'age_eligible': 15 if table=='frames' else 0,
                                          'cap_excess': 0} for table in ['frames','alerts','ble_observations','ble_alerts']}}
            elif path == 'retention/apply':
                if request.request.headers.get('x-configuration-key') != 'test-key':
                    code, data = 403, {'detail': 'A valid configuration key is required'}
                else:
                    policy.update(request.request.post_data_json['policy'])
                    status.update(last_run_at='2026-10-26T12:59:00+00:00', last_deleted={'frames': 15})
                    data = {'policy': policy, 'sources': sources, 'status': status}
            elif path == 'configuration':
                data = {'sensor': {'connected': False, 'configuration': None}, 'collector': {'window_seconds': 10,'host': '127.0.0.1','port':8181},
                        'limits': {'window_seconds': [1,3600], 'retention_days': [1,3650], 'retention_hours': [1,87600], 'ble_max_records': [100,1000000]},
                        'lists': [], 'restart_fields': []}
            elif path == 'purge':
                data = {'job': None, 'defaults_hours': {'frames': policy['wifi_age_hours'], 'alerts': policy['wifi_age_hours'],
                        'ble_observations': policy['ble_age_hours'], 'ble_alerts': policy['ble_age_hours']}}
            elif path == 'system':
                data = {}
            else:
                data = {'health': {'serial_enabled': False}, 'summary': {'frames_24h': 0, 'alerts_24h': 0, 'sensors': 0, 'by_subtype': []},
                        'alert-sources': {'macs': [], 'legacy_alerts_without_sources': 0},
                        'ble/devices?limit=200': {'devices': [], 'has_more': False}}.get(path, [])
            request.fulfill(status=code, content_type='application/json', body=json.dumps(data))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True,args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':1280,'height':900})
            page.clock.install()
            page.route('**/*',route)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://dashboard.test')
            page.locator('#pause').click()
            page.locator('#configuration').click()
            page.locator('#configuration-retention').click()
            page.wait_for_function("document.querySelector('#retention-status').textContent.includes('Automatic age deletion on')")
            self.assertEqual(page.locator('#retention-wifi-preset').input_value(), '168')
            self.assertEqual(page.locator('#collector-retention_days').count(), 0)
            self.assertEqual(page.locator('#collector-ble_max_records').count(), 0)
            page.clock.run_for(10000)
            self.assertEqual(calls.count(('retention','GET')),1)
            page.locator('#retention-wifi-preset').select_option('custom')
            page.locator('#retention-wifi-amount').fill('2')
            page.locator('#retention-wifi-unit').select_option('24')
            page.locator('#retention-preview-button').click()
            page.locator('#retention-confirmation').wait_for()
            self.assertTrue(page.locator('#retention-danger').is_visible())
            self.assertIn('Age eligible 15',page.locator('#retention-preview-content').inner_text())
            page.locator('#retention-interval').fill('120')
            self.assertFalse(page.locator('#retention-confirmation').is_visible())
            page.locator('#retention-preview-button').click()
            page.locator('#retention-confirmation').wait_for()
            page.locator('#retention-save').click()
            self.assertEqual(calls.count(('retention/apply','POST')),0)
            page.locator('#retention-key').fill('wrong')
            page.locator('#retention-confirm-text').fill('RETENTION')
            page.locator('#retention-save').click()
            page.wait_for_function("document.querySelector('#retention-message').textContent.includes('valid configuration key')")
            page.locator('#retention-key').fill('test-key')
            page.locator('#retention-save').click()
            page.wait_for_function("document.querySelector('#retention-message').textContent.includes('Policy saved')")
            self.assertEqual(policy['wifi_age_hours'],48)
            self.assertEqual(policy['cleanup_interval_seconds'],120)
            page.locator('#retention-wifi-preset').select_option('168')
            page.locator('#retention-preview-button').click()
            page.locator('#retention-confirmation').wait_for()
            self.assertFalse(page.locator('#retention-danger').is_visible())
            self.assertFalse(page.locator('#retention-confirm-label').is_visible())
            page.set_viewport_size({'width':390,'height':844})
            self.assertTrue(page.locator('#retention-dialog').evaluate('(n)=>n.scrollWidth<=n.clientWidth'))
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'),'configuration-retention')
            self.assertEqual(page.locator('#retention-key').input_value(),'')
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'),'configuration')
            self.assertEqual(errors,[])
            browser.close()
