"""Offline, evidence-labelled BLE identification. Never guesses a physical identity."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def registry():
    try:
        return json.loads((Path(__file__).parent / 'data/ble-assigned-numbers.json').read_text())
    except (OSError, ValueError):
        return {'companies': {}, 'services': {}, 'source': 'Registry unavailable', 'retrieved_at': None}


def identify(row):
    data = registry()
    companies = [{'id': item['company_id'], 'name': data['companies'].get(item['company_id']),
                  'source': data['source']} for item in row['manufacturer_data']]
    services = [{'uuid': value, 'name': data['services'].get(value), 'source': data['source']}
                for value in row['service_uuids']]
    name = row.get('observed_name') or row.get('local_name')
    alias = row.get('alias') or ''
    known_service = next((item for item in services if item['name']), None)
    known_company = next((item for item in companies if item['name']), None)
    if alias:
        label, origin = alias, 'Operator alias'
    elif name:
        label, origin = name, 'Advertised local name'
    elif known_service:
        label, origin = known_service['name'] + ' advertisement', 'Advertised service'
    elif known_company:
        label, origin = known_company['name'] + ' advertisement', 'Advertised company identifier'
    else:
        label, origin = 'Unnamed advertiser · ' + row['address'][-8:], 'Address fallback'
    category = (known_service['name'] + ' advertised') if known_service else 'Unknown device category'
    subtype = 'Public'
    if row['address_type'] == 'random':
        subtype = {0: 'Non-resolvable private', 1: 'Resolvable private',
                   2: 'Reserved random address pattern', 3: 'Static random'}[int(row['address'][:2], 16) >> 6]
    return {**row, 'display_label': label, 'label_source': origin, 'category': category,
            'identity_confidence': 'Unverified; no physical device/model/owner established',
            'address_subtype': subtype, 'advertised_name': name,
            'company_details': companies, 'service_details': services,
            'registry_source': data['source'], 'registry_retrieved_at': data.get('retrieved_at'),
            'evidence_note': 'Company IDs describe advertised data, not verified hardware manufacture. Names and addresses can be spoofed.'}
