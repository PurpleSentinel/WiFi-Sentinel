#!/usr/bin/env python3
"""Refresh offline Bluetooth SIG factual mappings. Dev dependency: PyYAML."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

BASE = 'https://bitbucket.org/bluetooth-SIG/public/raw/HEAD/assigned_numbers/'
FILES = {'companies': ('company_identifiers/company_identifiers.yaml', 'company_identifiers', 'value'),
         'services': ('uuids/service_uuids.yaml', 'uuids', 'uuid')}


def main():
    import yaml  # Maintenance only; the running collector has no YAML dependency.
    result = {'source': 'Bluetooth SIG Assigned Numbers',
              'source_url': 'https://www.bluetooth.com/specifications/assigned-numbers/',
              'retrieved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'terms': 'Bluetooth SIG assigned-number facts; upstream notices and terms apply, not the project MIT license.',
              'sources': {}}
    for kind, (filename, collection, key) in FILES.items():
        url = BASE + filename
        with urlopen(Request(url, headers={'User-Agent': 'WiFi-Sentinel-registry-maintenance'}), timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Registry exceeds download limit')
        entries = yaml.safe_load(raw)[collection]
        mapped = {}
        for row in entries:
            value, name = row[key], row['name']
            if type(value) is not int or not 0 <= value <= 65535 or not isinstance(name, str) or not 1 <= len(name) <= 300:
                raise ValueError('Invalid assigned-number record')
            number = f'{value:04x}'
            if number in mapped:
                raise ValueError('Duplicate assigned number')
            mapped[number] = name
        if len(mapped) < (1000 if kind == 'companies' else 30):
            raise ValueError('Unexpectedly small registry')
        result[kind] = mapped
        result['sources'][kind] = {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'count': len(mapped)}
    target = Path(__file__).resolve().parents[1] / 'collector/wids/data/ble-assigned-numbers.json'
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(target)
    print({kind: len(result[kind]) for kind in FILES})


if __name__ == '__main__':
    main()
