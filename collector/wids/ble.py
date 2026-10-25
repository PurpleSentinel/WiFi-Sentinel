"""Passive legacy BLE advertisements: bounded validation, AD decoding and rules."""
import re
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID

from .models import MAC, SENSOR


def rule(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or len(value) > 256 or ':' not in value:
        raise ValueError('BLE rules use name:, address:, service: or company:')
    kind, text = value.split(':', 1)
    if not text or kind not in ('name', 'address', 'service', 'company'):
        raise ValueError('Invalid BLE rule')
    if kind == 'address' and not MAC.fullmatch(text):
        raise ValueError('Invalid BLE address rule')
    if kind == 'service':
        text = service_uuid(text)
    if kind == 'company':
        if not re.fullmatch(r'[0-9a-fA-F]{4}', text):
            raise ValueError('BLE company rules require four hexadecimal digits')
    return kind, text.casefold()


def service_uuid(value: str) -> str:
    if re.fullmatch(r'[0-9a-fA-F]{4}|[0-9a-fA-F]{8}', value):
        return value.lower()[4:] if len(value) == 8 and value.startswith("0000") else value.lower()
    try:
        value = str(UUID(value))
        if value.endswith('-0000-1000-8000-00805f9b34fb'):
            return service_uuid(value[:8])
        return value
    except (ValueError, AttributeError) as exc:
        raise ValueError('Invalid BLE service UUID') from exc


def decode_ad(raw: bytes) -> dict:
    result = {'local_name': None, 'service_uuids': [], 'manufacturer_data': [],
              'service_data': [], 'ad_malformed': False}
    offset = 0
    while offset < len(raw):
        size = raw[offset]
        offset += 1
        if size == 0:
            break
        if offset + size > len(raw):
            result['ad_malformed'] = True
            break
        kind, data = raw[offset], raw[offset + 1:offset + size]
        offset += size
        if kind in (8, 9):
            # Complete names take precedence. Escape controls; raw bytes are retained.
            name = ''.join(c if c.isprintable() else f'\\x{ord(c):02x}'
                           for c in data.decode('utf-8', errors='backslashreplace'))
            if result['local_name'] is None or kind == 9:
                result['local_name'] = name
        elif kind in (2, 3, 4, 5, 6, 7):
            width = {2: 2, 3: 2, 4: 4, 5: 4, 6: 16, 7: 16}[kind]
            if len(data) % width:
                result['ad_malformed'] = True
            for start in range(0, len(data) - width + 1, width):
                part = data[start:start + width]
                value = service_uuid(str(UUID(bytes=part[::-1])) if width == 16 else part[::-1].hex())
                if value not in result['service_uuids']:
                    result['service_uuids'].append(value)
        elif kind == 255:
            if len(data) < 2:
                result['ad_malformed'] = True
            else:
                result['manufacturer_data'].append({'company_id': data[:2][::-1].hex(), 'data_hex': data[2:].hex()})
        elif kind in (0x16, 0x20, 0x21):
            width = {0x16: 2, 0x20: 4, 0x21: 16}[kind]
            if len(data) < width:
                result['ad_malformed'] = True
            else:
                value = service_uuid(str(UUID(bytes=data[:width][::-1])) if width == 16 else data[:width][::-1].hex())
                result['service_data'].append({'uuid': value, 'data_hex': data[width:].hex()})
                if value not in result['service_uuids']:
                    result['service_uuids'].append(value)
    return result


@dataclass(frozen=True)
class Advertisement:
    sensor_id: str
    address: str
    address_type: str
    rssi: int
    payload_hex: str
    event_type: int
    uptime_ms: int

    @classmethod
    def from_json(cls, obj):
        if obj.get('v') != 1 or obj.get('kind') != 'ble':
            raise ValueError('Unsupported BLE event')
        sid, address = obj.get('sensor_id'), obj.get('address')
        if not isinstance(sid, str) or not SENSOR.fullmatch(sid):
            raise ValueError('Invalid BLE sensor')
        if not isinstance(address, str) or not MAC.fullmatch(address):
            raise ValueError('Invalid BLE advertiser address')
        if obj.get('address_type') not in ('public', 'random'):
            raise ValueError('Invalid BLE address type')
        for name, low, high in [('rssi', -127, 20), ('event_type', 0, 3), ('uptime_ms', 0, 2**32 - 1)]:
            if type(obj.get(name)) is not int or not low <= obj[name] <= high:
                raise ValueError('Invalid BLE ' + name)
        payload = obj.get('payload_hex')
        if not isinstance(payload, str) or len(payload) > 62 or len(payload) % 2 or not re.fullmatch('[0-9a-fA-F]*', payload):
            raise ValueError('Invalid legacy BLE advertisement bytes')
        return cls(sid, address.lower(), obj['address_type'], obj['rssi'], payload.lower(), obj['event_type'], obj['uptime_ms'])

    def decoded(self):
        return decode_ad(bytes.fromhex(self.payload_hex))

    def matches(self, expression, data=None):
        kind, text = rule(expression)
        data = self.decoded() if data is None else data
        return {'address': lambda: self.address == text,
                'name': lambda: (data['local_name'] or '').casefold() == text,
                'service': lambda: text in data['service_uuids'],
                'company': lambda: any(item['company_id'] == text for item in data['manufacturer_data'])}[kind]()


class BLEPolicy:
    """Fixed-size caches prevent rotating addresses growing process memory."""
    CAPACITY = 1024

    def __init__(self):
        self.seen = OrderedDict()
        self.alerted = OrderedDict()

    @staticmethod
    def remember(cache, key, now):
        cache[key] = now
        cache.move_to_end(key)
        while len(cache) > BLEPolicy.CAPACITY:
            cache.popitem(last=False)

    def observe(self, ad, settings, now):
        data = ad.decoded() if settings.ble_filters or settings.ble_alert_rules else None
        if settings.ble_filters and not any(ad.matches(item, data) for item in settings.ble_filters):
            return False, []
        key = (ad.sensor_id, ad.address, ad.address_type)
        matched = []
        for expression in settings.ble_alert_rules:
            alert_key = (ad.sensor_id, expression)
            if ad.matches(expression, data) and now - self.alerted.get(alert_key, float('-inf')) >= settings.cooldown_seconds:
                self.remember(self.alerted, alert_key, now)
                matched.append(expression)
        duplicate = (*key, ad.payload_hex, ad.event_type)
        accept = now - self.seen.get(duplicate, float('-inf')) >= settings.ble_duplicate_seconds
        if accept:
            self.remember(self.seen, duplicate, now)
        return accept, matched
