"""Conservative rules, keyed per sensor/BSSID/channel, with sliding windows.

Rates are counts of observed frames, *not* uniquely authenticated users or
proof of an attack. A single-radio sensor may miss frames.
"""
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import Settings
from .models import Frame
from .ssids import matches_protected


@dataclass(frozen=True)
class Alert:
    timestamp: str
    sensor_id: str
    rule: str
    severity: str
    bssid: str
    channel: int
    frame_count: int
    details: str
    source_macs: tuple[str, ...] | None = None


class Detector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.recent: dict[tuple, deque[tuple[float, str]]] = defaultdict(deque)
        self.last_alert: dict[tuple, float] = {}
        self.seen_ssids: set[tuple] = set()
        self._last_prune = 0.0

    def observe(self, frame: Frame, now: float | None = None) -> list[Alert]:
        t = time.monotonic() if now is None else now
        alerts: list[Alert] = []
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def make(rule: str, severity: str, count: int, detail: str,
                 source_macs: tuple[str, ...]) -> None:
            key = (frame.sensor_id, frame.bssid, frame.channel, rule)
            if t - self.last_alert.get(key, float("-inf")) < self.settings.cooldown_seconds:
                return
            self.last_alert[key] = t
            alerts.append(Alert(stamp, frame.sensor_id, rule, severity, frame.bssid,
                                frame.channel, count, detail, source_macs))

        # SSID allowlisting does not depend on the monitored BSSID filter.
        if frame.subtype in {"beacon", "probe_resp"} and frame.ssid:
            fingerprint = (frame.sensor_id, frame.bssid, frame.ssid_bytes)
            if fingerprint not in self.seen_ssids:
                self.seen_ssids.add(fingerprint)
                if (matches_protected(frame.ssid_bytes, self.settings.protected_ssids)
                        and frame.bssid not in self.settings.trusted_bssids):
                    make("protected_ssid_untrusted_bssid", "high", 1,
                         f"SSID {frame.ssid!r} advertised by non-allowlisted BSSID; investigate, not proof of evil twin",
                         (frame.sa,))

        if self.settings.monitored_bssids and frame.bssid not in self.settings.monitored_bssids:
            return alerts

        thresholds = {
            "deauth": (self.settings.deauth_threshold, "high", "deauthentication burst"),
            "disassoc": (self.settings.disassoc_threshold, "high", "disassociation burst"),
            "auth": (self.settings.auth_threshold, "medium", "authentication burst"),
        }
        if frame.subtype in thresholds:
            threshold, severity, detail = thresholds[frame.subtype]
            key = (frame.sensor_id, frame.bssid, frame.channel, frame.subtype)
            count = self._append(key, t, frame.sa)
            if count >= threshold:
                sources = len(Counter(sa for _, sa in self.recent[key]))
                make(f"{frame.subtype}_flood", severity, count,
                     f"Possible {detail}: {count} frames in {self.settings.window_seconds}s, {sources} source MAC(s)",
                     tuple(sorted({sa for _, sa in self.recent[key]})))

        if frame.subtype in {"auth", "assoc_resp", "reassoc_resp"} and frame.status_code not in (None, 0):
            key = (frame.sensor_id, frame.bssid, frame.channel, "failed_auth")
            count = self._append(key, t, frame.sa)
            if count >= self.settings.failed_auth_threshold:
                make("failed_auth_burst", "medium", count,
                     f"{count} unsuccessful authentication/association responses; not proof of password guessing",
                     tuple(sorted({sa for _, sa in self.recent[key]})))
        if now is None and t - self._last_prune > 60:
            self._prune(t)
            self._last_prune = t
        return alerts

    def _append(self, key: tuple, timestamp: float, sa: str) -> int:
        queue = self.recent[key]
        queue.append((timestamp, sa))
        while queue and timestamp - queue[0][0] >= self.settings.window_seconds:
            queue.popleft()
        return len(queue)

    def _prune(self, timestamp: float) -> None:
        for key, queue in list(self.recent.items()):
            while queue and timestamp - queue[0][0] >= self.settings.window_seconds:
                queue.popleft()
            if not queue:
                del self.recent[key]
        for key, last in list(self.last_alert.items()):
            if timestamp - last > max(3600, self.settings.cooldown_seconds * 2):
                del self.last_alert[key]
