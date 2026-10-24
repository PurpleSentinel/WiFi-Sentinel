"""Local longest-prefix registry with cached, prefix-only vendor enrichment."""
import gzip
import json
import re
import sqlite3
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / 'data'
SOURCE = 'https://maclookup.app/downloads/json-database'
API = 'https://api.maclookup.app/v2/macs/'


def normalize_mac(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F:.\-]{12,17}', value):
        raise ValueError('Enter a complete MAC address')
    digits = re.sub(r'[:.\-]', '', value).lower()
    if len(digits) != 12:
        raise ValueError('A MAC address must contain 12 hexadecimal digits')
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2))


@lru_cache(maxsize=1)
def registry():
    with gzip.open(DATA / 'vendors.json.gz', 'rt', encoding='utf-8') as stream:
        rows = json.load(stream)
    metadata = json.loads((DATA / 'vendors-meta.json').read_text())
    return {row['macPrefix'].replace(':', '').upper(): row for row in rows}, metadata


class VendorLookup:
    def __init__(self, path: Path):
        self.db = None
        try:
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS vendors (prefix TEXT PRIMARY KEY, data TEXT, checked_at TEXT)')
            self.db.commit()
        except sqlite3.Error:
            if self.db:
                self.db.close()
            self.db = None
        self.lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.last_fetch = float('-inf')

    def close(self):
        with self.lock:
            if self.db:
                self.db.close()

    @staticmethod
    def fetch(prefix):
        # Never send an observed suffix. This provider resolves only 24-bit prefixes.
        request = urllib.request.Request(API + prefix[:6], headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError('Vendor response exceeded the size limit')
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get('success') is not True or data.get('found') is not True:
            raise ValueError('Vendor service returned no matching registration')
        returned = str(data.get('macPrefix', '')).replace(':', '').upper()
        if returned != prefix or len(prefix) != 6:
            raise ValueError('Vendor service did not resolve the selected assignment')
        return data

    def lookup(self, mac: str, refresh=False):
        mac = normalize_mac(mac)
        now = datetime.now(timezone.utc)
        result = {'mac': mac, 'looked_up_at': now.isoformat(timespec='seconds'),
                  'cached': False, 'stale': False, 'source_url': SOURCE,
                  'registration': None, 'additional_details': None, 'error': None}
        octet = int(mac[:2], 16)
        if mac == '00:00:00:00:00:00':
            return {**result, 'status': 'zero_address'}
        if octet & 1:
            return {**result, 'status': 'multicast_or_broadcast'}
        if octet & 2:
            return {**result, 'status': 'locally_administered'}
        try:
            entries, metadata = registry()
        except (OSError, ValueError, KeyError):
            return {**result, 'status': 'registry_unavailable', 'error': 'Local vendor registry is unavailable; restore the packaged registry and retry.'}
        result['registry'] = metadata
        digits = mac.replace(':', '').upper()
        match = next((entries[digits[:length]] for length in (9, 7, 6) if digits[:length] in entries), None)
        if match is None:
            return {**result, 'status': 'not_found'}
        prefix = match['macPrefix'].replace(':', '').upper()
        bits = len(prefix) * 4
        start = int(prefix, 16) << (48 - bits)
        size = 1 << (48 - bits)
        result.update(status='found', cached=True, registration={**match, 'prefix_bits': bits,
                      'blockStart': f'{start:012X}', 'blockEnd': f'{start + size - 1:012X}',
                      'blockSize': size})
        if len(prefix) != 6:
            result['details_note'] = 'Longest-prefix local assignment shown. The online service resolves only 24-bit prefixes, so it is not used for this subassignment.'
            return result
        with self.lock:
            try:
                cached = self.db.execute('SELECT data,checked_at FROM vendors WHERE prefix=?', (prefix,)).fetchone() if self.db else None
            except sqlite3.Error:
                cached = None
        if cached:
            try:
                result['additional_details'] = json.loads(cached[0])
                result['details_checked_at'] = cached[1]
                result['stale'] = datetime.fromisoformat(cached[1]) < now - timedelta(days=30)
                if not refresh and not result['stale']:
                    return result
            except (ValueError, TypeError):
                result['additional_details'] = None
        if not self.fetch_lock.acquire(blocking=False):
            result['error'] = 'Another vendor lookup is in progress. Local registry details are available; retry shortly for additional details.'
            return result
        try:
            if time.monotonic() - self.last_fetch < 1:
                result['error'] = 'Vendor lookup rate limit: retry shortly for additional details.'
                return result
            self.last_fetch = time.monotonic()
            data = self.fetch(prefix)
            stamp = now.isoformat(timespec='seconds')
            try:
                with self.lock:
                    if self.db:
                        with self.db:
                            self.db.execute('INSERT OR REPLACE INTO vendors VALUES (?,?,?)',
                                            (prefix, json.dumps(data), stamp))
                            self.db.execute('DELETE FROM vendors WHERE prefix NOT IN (SELECT prefix FROM vendors ORDER BY checked_at DESC LIMIT 4096)')
            except sqlite3.Error:
                result['details_note'] = 'Additional details loaded but could not be saved in the local cache.'
            result.update(additional_details=data, details_checked_at=stamp, cached=False, stale=False)
        except (OSError, ValueError, TypeError):
            result['error'] = 'Additional vendor details are unavailable. Local registry details remain available; retry when the service is reachable.'
        finally:
            self.fetch_lock.release()
        return result
