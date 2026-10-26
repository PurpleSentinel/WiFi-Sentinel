"""Mocked purge workflow: no real captured data is deleted by browser checks."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from playwright.sync_api import sync_playwright
from wids.config import Settings
from wids.system_metrics import SystemMetrics


class PurgeDialog(unittest.TestCase):
    def test_preview_confirm_progress_pause_and_mobile(self):
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        with tempfile.TemporaryDirectory() as folder:
            system = SystemMetrics().snapshot(replace(Settings.from_env(), database=Path(folder) / 'absent.sqlite3'), {'connected': False})
        calls, errors = [], []
        job = None
        eligible = 12
        def route(request):
            nonlocal job
            path = request.request.url.split('/api/')[-1]
            if '/api/' not in request.request.url:
                request.fulfill(content_type='text/html', body=html)
                return
            calls.append((path, request.request.method))
            status = 200
            if path == 'system':
                data = system
            elif path == 'purge':
                data = {'job': job, 'defaults_hours': {'frames': 168, 'alerts': 168, 'ble_observations': 72, 'ble_alerts': 72}}
            elif path == 'purge/preview':
                ages = request.request.post_data_json['ages_hours']
                data = {'token': 'preview-token', 'cutoffs': dict.fromkeys(ages, '2026-10-25T12:00:00+00:00'), 'counts': {table: {'eligible': eligible, 'remaining': 5, 'total': eligible + 5} for table in ages}}
            elif path == 'purge/start':
                if request.request.headers.get('x-configuration-key') != 'test-key':
                    status, data = 403, {'detail': 'A valid configuration key is required'}
                else:
                    job = {'id': 'job1', 'state': 'running', 'started_at': '2026-10-26T12:00:00Z', 'finished_at': None, 'deleted': {'frames': 4}, 'cutoffs': {'frames': '2026-10-25T12:00:00Z'}, 'preview_counts': {'frames': {'eligible': 12}}, 'cancel_requested': False, 'error': None}
                    data = job
            elif path == 'purge/cancel':
                job.update(state='cancelled', finished_at='2026-10-26T12:01:00Z', cancel_requested=True)
                data = job
            else:
                data = {'health': {'serial_enabled': False}, 'summary': {'frames_24h': 0, 'alerts_24h': 0, 'sensors': 0, 'by_subtype': []}, 'alert-sources': {'macs': [], 'legacy_alerts_without_sources': 0}, 'ble/devices?limit=200': {'devices': [], 'has_more': False}, 'devices?limit=200': {'devices': [], 'total_devices': 0, 'has_more': False}}.get(path, [])
            request.fulfill(status=status, content_type='application/json', body=json.dumps(data))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.clock.install()
            page.route('**/*', route)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://dashboard.test')
            page.locator('#pause').click()
            page.locator('#system').click()
            page.locator('#system-purge').click()
            page.wait_for_function("purgeDefaults !== null")
            page.locator('#purge-defaults').click()
            self.assertEqual(page.locator('#purge-age-ble_alerts').input_value(), '72')
            self.assertTrue(page.locator('#purge-separate').is_checked())
            page.locator('#purge-separate').uncheck()
            page.locator('#purge-preset').select_option('24')
            self.assertEqual(page.locator('#purge-age').input_value(), '24')
            for name in ('alerts', 'ble_observations', 'ble_alerts'):
                page.locator('#purge-check-'+name).uncheck()
            page.locator('#purge-preview').click()
            page.locator('#purge-confirmation').wait_for()
            self.assertEqual(page.locator('.purge-summary-total').inner_text(), '12\nrecords selected for deletion')
            self.assertEqual(page.locator('#purge-preview-content .purge-counts strong').all_text_contents(), ['12', '5', '17'])
            self.assertFalse(page.locator('#purge-age').is_visible())
            page.locator('#purge-preset').select_option('custom')
            page.locator('#purge-age').fill('2')
            self.assertFalse(page.locator('#purge-confirmation').is_visible())
            page.locator('#purge-preview').click()
            page.locator('#purge-confirmation').wait_for()
            page.locator('#purge-start').click()
            self.assertFalse(any(path == 'purge/start' for path, _ in calls))
            page.locator('#purge-key').fill('wrong')
            page.locator('#purge-confirm-text').fill('PURGE')
            page.locator('#purge-start').click()
            page.wait_for_function("document.querySelector('#purge-message').textContent.includes('valid configuration key')")
            page.locator('#purge-key').fill('test-key')
            page.locator('#purge-start').click()
            page.wait_for_function("document.querySelector('#purge-progress').textContent.includes('RUNNING')")
            status_calls = calls.count(('purge', 'GET'))
            page.clock.run_for(8000)
            self.assertEqual(calls.count(('purge', 'GET')), status_calls)
            self.assertTrue(page.locator('#purge-options').evaluate('(n)=>n.disabled'), page.evaluate('({purgeRunning,purgeBusy,html:document.querySelector("#purge-options").outerHTML})'))
            page.locator('#purge-progress-refresh').click()
            page.wait_for_function('!purgeStatusBusy')
            self.assertGreater(calls.count(('purge', 'GET')), status_calls)
            page.locator('#purge-cancel').click()
            page.wait_for_function("document.querySelector('#purge-progress').textContent.includes('CANCELLED')")
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertTrue(page.locator('#purge-dialog').evaluate('(n)=>n.scrollWidth<=n.clientWidth'))
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'), 'system-purge')
            self.assertEqual(page.locator('#purge-key').input_value(), '')
            page.locator('#system-purge').click()
            eligible = 0
            page.locator('#purge-preview').click()
            page.wait_for_function("document.querySelector('#purge-message').textContent.includes('No matching records')")
            self.assertFalse(page.locator('#purge-confirmation').is_visible())
            page.keyboard.press('Escape')
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'), 'system')
            self.assertEqual(errors, [])
            browser.close()
