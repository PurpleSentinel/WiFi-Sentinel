"""Lossless SSID transport, readable display, and protected-name matching."""
import re

HEX_SSID = re.compile(r'(?:[0-9a-fA-F]{2}){0,32}')


def display_ssid(raw: bytes) -> str | None:
    if not raw:
        return None
    result = []
    for character in raw.decode('utf-8', errors='surrogateescape'):
        number = ord(character)
        if 0xDC80 <= number <= 0xDCFF:
            result.append(f'\\x{number - 0xDC00:02x}')
        elif character == '\\':
            result.append('\\\\')
        elif not character.isprintable():
            result.extend(f'\\x{byte:02x}' for byte in character.encode('utf-8'))
        else:
            result.append(character)
    return ''.join(result)


def wire_ssid(obj: dict) -> tuple[str | None, str | None]:
    text, encoded = obj.get('ssid'), obj.get('ssid_hex')
    if encoded is not None:
        if not isinstance(encoded, str) or not HEX_SSID.fullmatch(encoded):
            raise ValueError('ssid_hex must encode 0..32 bytes as pairs of hexadecimal digits')
        raw = bytes.fromhex(encoded)
        if text is not None and (not isinstance(text, str) or text.encode('utf-8') != raw):
            raise ValueError('ssid and ssid_hex disagree')
        return display_ssid(raw), encoded.lower()
    # Accept existing text-only telemetry/replays without pretending to recover
    # bytes that older firmware already replaced with underscores.
    if text is not None and (not isinstance(text, str) or len(text.encode('utf-8')) > 32
                             or any(not character.isprintable() for character in text)):
        raise ValueError('invalid SSID')
    return text, None


def protected_name(value: str) -> tuple[str, str | bytes]:
    if value.lower().startswith('hex:'):
        encoded = value[4:]
        if not encoded or not HEX_SSID.fullmatch(encoded):
            raise ValueError('A hex: protected SSID must encode 1..32 bytes')
        return 'hex', bytes.fromhex(encoded)
    text = value[5:] if value.lower().startswith('utf8:') else value
    if not text or len(text.encode('utf-8')) > 32 or any(not character.isprintable() for character in text):
        raise ValueError('A protected SSID must contain 1..32 UTF-8 bytes; use hex: for raw bytes')
    return 'utf8', text.lower()


def matches_protected(raw: bytes, configured: tuple[str, ...]) -> bool:
    try:
        text = raw.decode('utf-8').lower()
    except UnicodeDecodeError:
        text = None
    for value in configured:
        kind, target = protected_name(value)
        if (kind == 'hex' and raw == target) or (kind == 'utf8' and text == target):
            return True
    return False
