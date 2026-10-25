"""Constrained JSON line protocol shared with the ESP-IDF firmware."""
import json
import re
from dataclasses import dataclass
from typing import Any

from .ssids import wire_ssid

# Parse only WIDS-prefixed lines. ESP boot/debug messages are deliberately ignored.
MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", re.IGNORECASE)
SENSOR = re.compile(r"^[a-zA-Z0-9_.-]{1,40}$")
SUBTYPES = {"deauth", "disassoc", "auth", "assoc_req", "assoc_resp", "reassoc_req", "reassoc_resp", "beacon", "probe_resp"}


@dataclass(frozen=True)
class Frame:
    sensor_id: str
    channel: int
    subtype: str
    sa: str
    da: str
    bssid: str
    rssi: int
    protected: bool
    reason_code: int | None = None
    status_code: int | None = None
    ssid: str | None = None
    uptime_ms: int = 0
    ssid_hex: str | None = None

    @property
    def ssid_bytes(self) -> bytes | None:
        if self.ssid_hex is not None:
            return bytes.fromhex(self.ssid_hex)
        return self.ssid.encode('utf-8') if self.ssid is not None else None

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Frame":
        if obj.get("v") != 1 or obj.get("kind") != "frame":
            raise ValueError("unsupported protocol version or event")
        sid = str(obj["sensor_id"])
        if not SENSOR.fullmatch(sid):
            raise ValueError("invalid sensor identifier")
        channel = int(obj["channel"])
        if not 1 <= channel <= 177:
            raise ValueError("invalid Wi-Fi channel")
        subtype = str(obj["subtype"])
        if subtype not in SUBTYPES:
            raise ValueError("unrecognised frame subtype")
        addresses = [str(obj[x]).lower() for x in ("sa", "da", "bssid")]
        if any(not MAC.fullmatch(x) for x in addresses):
            raise ValueError("invalid MAC address")
        rssi = int(obj["rssi"])
        if not -127 <= rssi <= 20:
            raise ValueError("invalid RSSI")
        if not isinstance(obj.get("protected"), bool):
            raise ValueError("protected must be boolean")
        ssid, ssid_hex = wire_ssid(obj)
        def maybe_code(field: str) -> int | None:
            value = obj.get(field)
            if value is None or value == -1:
                return None
            number = int(value)
            if not 0 <= number <= 65535:
                raise ValueError("invalid " + field)
            return number
        return cls(
            sensor_id=sid, channel=channel, subtype=subtype,
            sa=addresses[0], da=addresses[1], bssid=addresses[2], rssi=rssi,
            protected=obj["protected"], reason_code=maybe_code("reason_code"),
            status_code=maybe_code("status_code"), ssid=ssid,
            uptime_ms=max(0, int(obj.get("uptime_ms", 0))),
            ssid_hex=ssid_hex,
        )


def parse_wire_line(line: bytes | str) -> dict[str, Any] | None:
    """Return valid protocol objects or None for non-data ESP-IDF output."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    if not line.startswith("WIDS ") or len(line) > 2048:
        return None
    try:
        obj = json.loads(line[5:])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get("v") != 1:
        return None
    if obj.get("kind") == "frame":
        Frame.from_json(obj)  # validated before it reaches persistence
    elif obj.get("kind") == "config_ack":
        if not isinstance(obj.get('id'), str) or len(obj['id']) > 40 or type(obj.get('ok')) is not bool:
            return None
    elif obj.get("kind") == "heartbeat":
        if not SENSOR.fullmatch(str(obj.get("sensor_id", ""))):
            return None
    else:
        return None
    return obj
