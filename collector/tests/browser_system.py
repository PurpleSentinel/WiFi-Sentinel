"""System dialog reads, pause, lifecycle, errors and responsive layout."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from playwright.sync_api import sync_playwright
from wids.config import Settings
from wids.system_metrics import SystemMetrics


class SystemDialog(unittest.TestCase):
    def test_system_dialog(self):
        html = (Path(__file__).parents[1] / 'wids/static/index.html').read_text()
        calls, errors = [], []
        fail = False
        with tempfile.TemporaryDirectory() as folder:
            data = SystemMetrics().snapshot(replace(Settings.from_env(), database=Path(folder) / 'absent.sqlite3'), {'connected': False})
        data['host']['hardware_model'] = 'Raspberry Pi 4 Model B Rev 1.2'
        def route(request):
            nonlocal fail
            path = request.request.url.split('/api/')[-1]
            if '/api/' not in request.request.url:
                request.fulfill(content_type='text/html', body=html)
                return
            if path == 'system':
                calls.append(path)
                request.fulfill(status=503 if fail else 200, content_type='application/json', body=json.dumps({'detail': 'Busy; retry shortly'} if fail else data))
                return
            body = {'health': {'serial_enabled': False}, 'summary': {'frames_24h': 0, 'alerts_24h': 0, 'sensors': 0, 'by_subtype': []}, 'alert-sources': {'macs': [], 'legacy_alerts_without_sources': 0}, 'ble/devices?limit=200': {'devices': [], 'has_more': False}, 'devices?limit=200': {'devices': []}, 'configuration': {'sensor': {'connected': False, 'configuration': None}}}.get(path, [])
            request.fulfill(content_type='application/json', body=json.dumps(body))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
            page = browser.new_page()
            page.clock.install()
            page.route('**/*', route)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://dashboard.test')
            page.clock.run_for(16000)
            self.assertEqual(calls, [])
            self.assertEqual(page.locator('header button').all_text_contents()[1:4], ['Configuration', 'System', 'Status'])
            page.locator('#pause').click()
            page.locator('#system').click()
            page.get_by_text('Raspberry Pi 4 Model B Rev 1.2', exact=True).wait_for()
            page.wait_for_function("document.querySelector('#system-message').textContent.includes('paused')")
            page.clock.run_for(30000)
            self.assertEqual(len(calls), 1)
            page.locator('#system-refresh').click()
            page.wait_for_function("!document.querySelector('#system-refresh').disabled")
            self.assertEqual(len(calls), 2)
            page.keyboard.press('Escape')
            self.assertEqual(page.locator(':focus').get_attribute('id'), 'system')
            page.locator('#pause').click()
            page.locator('#system').click()
            page.wait_for_function("!document.querySelector('#system-refresh').disabled")
            page.clock.run_for(16000)
            page.wait_for_function("!document.querySelector('#system-refresh').disabled")
            self.assertGreaterEqual(len(calls), 4)
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertTrue(page.locator('#system-dialog').evaluate('(n)=>n.scrollWidth<=n.clientWidth'))
            page.keyboard.press('Escape')
            previous = len(calls)
            page.clock.run_for(30000)
            self.assertEqual(len(calls), previous)
            fail = True
            page.locator('#system').click()
            page.get_by_text('Could not load system information: Busy; retry shortly', exact=True).wait_for()
            self.assertEqual(errors, [])
            browser.close()
