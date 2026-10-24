#!/usr/bin/env python3
"""Refresh the bundled public snapshot; never upload observed addresses."""
import gzip
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URL = 'https://maclookup.app/downloads/json-database/get-db'


def main():
    with urllib.request.urlopen(URL, timeout=30) as response:
        payload = response.read(20_000_001)
    if len(payload) > 20_000_000:
        raise ValueError('Vendor snapshot exceeded the download limit')
    rows = json.loads(payload)
    if not isinstance(rows, list) or not 1000 <= len(rows) <= 200000:
        raise ValueError('Unexpected registry size')
    for row in rows:
        prefix = row.get('macPrefix', '').replace(':', '')
        if not re.fullmatch(r'(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{7}|[0-9A-Fa-f]{9})', prefix):
            raise ValueError('Invalid registry prefix')
        if not isinstance(row.get('vendorName'), str) or type(row.get('private')) is not bool:
            raise ValueError('Invalid registry record')
    data = Path(__file__).resolve().parents[1] / 'collector/wids/data'
    metadata = {'source': 'MACLookup', 'url': 'https://maclookup.app/downloads/json-database',
                'download_url': URL, 'retrieved_at': datetime.now(UTC).isoformat(timespec='seconds'),
                'records': len(rows), 'fields': list(rows[0])}
    for name, contents in [('vendors.json.gz', gzip.compress(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)),
                           ('vendors-meta.json', (json.dumps(metadata, indent=2) + '\n').encode())]:
        temporary = data / (name + '.tmp')
        temporary.write_bytes(contents)
        temporary.replace(data / name)
    print(f'Updated {len(rows)} vendor prefixes. Restart the collector and refresh affected checksums.')


if __name__ == '__main__':
    main()
