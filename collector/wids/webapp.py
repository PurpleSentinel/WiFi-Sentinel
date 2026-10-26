"""Dashboard data and key-protected settings; use a trusted LAN or TLS proxy."""
import secrets
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from .config import Settings
from .device_roles import ROLE_LABELS
from .engine import Engine, retention_loop, serial_loop
from .runtime import LIMITS, LISTS, RESTART_FIELDS, configuration_key
from .vendors import VendorLookup, normalize_mac
from .models import SENSOR
from .ble_identity import identify

WEB_ROOT = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings, engine: Engine | None = None) -> FastAPI:
    core = engine or Engine(settings)
    key = configuration_key(core.settings)
    vendors = VendorLookup(core.settings.database.with_suffix('.vendors.sqlite3'))
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        workers = []
        try:
            targets = [('wids-retention', retention_loop)]
            if settings.serial_port:
                targets.append(('wids-serial', serial_loop))
            for name, target in targets:
                thread = threading.Thread(name=name, target=target, args=(core, stop), daemon=True)
                thread.start()
                workers.append(thread)
            yield
        finally:
            stop.set()
            # Never close SQLite while a worker can still be using it.
            for worker in workers:
                worker.join()
            core.store.close()
            vendors.close()

    app = FastAPI(title="WiFi Sentinel", version="1.2.0", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware('http')
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'"
        return response

    def authorize(request: Request):
        if not secrets.compare_digest(request.headers.get('X-Configuration-Key', '').encode(), key.encode()):
            raise HTTPException(403, 'A valid configuration key is required')
        origin = request.headers.get('origin', '')
        try:
            parsed = urlsplit(origin)
        except ValueError as exc:
            raise HTTPException(403, 'Invalid request origin') from exc
        if parsed.scheme not in ('http', 'https') or parsed.netloc != request.headers.get('host') or parsed.scheme != request.url.scheme:
            raise HTTPException(403, 'Configuration changes require a same-origin request')

    @app.get('/api/configuration')
    def configuration():
        values = asdict(core.settings)
        values['database'] = str(values['database'])
        return {'collector': values, 'limits': LIMITS, 'lists': LISTS,
                'restart_fields': RESTART_FIELDS, 'sensor': core.sensor.snapshot()}

    @app.post('/api/configuration/{scope}')
    def configure(scope: str, values: dict, request: Request):
        authorize(request)
        try:
            if scope == 'collector':
                core.configure(values)
                return configuration()
            if scope == 'sensor':
                return core.sensor.apply(values)
            raise HTTPException(404, 'Unknown configuration scope')
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ConnectionError as exc:
            raise HTTPException(503, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, 'Could not persist configuration; check collector logs and file permissions') from exc

    @app.get("/")
    def index():
        return FileResponse(WEB_ROOT / "index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "serial_enabled": bool(settings.serial_port)}

    @app.get("/api/summary")
    def summary():
        return core.store.summary()

    @app.get("/api/alerts")
    def alerts(limit: int = 100):
        if not 1 <= limit <= 500:
            raise HTTPException(400, "limit must be 1..500")
        return core.store.all_alerts(limit)

    @app.get("/api/frames")
    def frames(limit: int = 100):
        if not 1 <= limit <= 500:
            raise HTTPException(400, "limit must be 1..500")
        return core.store.rows("SELECT * FROM frames ORDER BY id DESC LIMIT ?", (limit,))

    @app.get("/api/sensors")
    def sensors():
        return core.store.rows("SELECT * FROM sensors ORDER BY last_seen DESC")

    @app.get("/api/channels")
    def channels():
        return core.store.rows("SELECT channel,COUNT(*) count FROM frames GROUP BY channel ORDER BY channel")

    @app.get('/api/devices')
    def devices(limit: int = 200, role: str = 'all'):
        if not 1 <= limit <= 500:
            raise HTTPException(400, 'limit must be 1..500')
        if role != 'all' and role not in ROLE_LABELS:
            raise HTTPException(400, 'role must be all, access_point, client, mixed or unknown')
        return core.store.devices(limit, role)

    @app.get('/api/ble/observations')
    def ble_observations(limit: int = 100, address: str | None = None, address_type: str | None = None, sensor_id: str | None = None):
        if not 1 <= limit <= 500 or address_type not in (None, 'public', 'random'):
            raise HTTPException(400, 'Invalid BLE limit or address type')
        try:
            address = normalize_mac(address) if address else None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if sensor_id is not None and not SENSOR.fullmatch(sensor_id):
            raise HTTPException(400, 'Invalid sensor identifier')
        return core.store.ble_observations(limit, address, address_type, sensor_id)

    @app.get('/api/ble/devices')
    def ble_devices(limit: int = 200, query: str = '', address_type: str = 'all', alert_only: bool = False, sort: str = 'recent'):
        if len(query) > 200 or address_type not in ('all','public','random') or sort not in ('recent','rssi','name'):
            raise HTTPException(400, 'Invalid BLE filter or sort')
        if not 1 <= limit <= 500:
            raise HTTPException(400, 'limit must be 1..500')
        return core.store.ble_devices(limit, query, address_type, alert_only, sort)

    def ble_identity(sensor_id, address, address_type):
        if not isinstance(sensor_id, str) or not SENSOR.fullmatch(sensor_id) or address_type not in ('public','random'):
            raise ValueError('A sensor, advertiser address and public/random type are required')
        return sensor_id, normalize_mac(address), address_type

    @app.get('/api/ble/advertiser')
    def ble_advertiser(sensor_id: str, address: str, address_type: str):
        try:
            sid, mac, kind = ble_identity(sensor_id, address, address_type)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        rows = core.store.ble_observations(100, mac, kind, sid)
        label = core.store.ble_label(sid, mac, kind)
        summary = None
        if rows:
            named = core.store.rows("SELECT local_name,timestamp FROM ble_observations WHERE sensor_id=? AND address=? AND address_type=? AND local_name IS NOT NULL AND local_name!='' ORDER BY id DESC LIMIT 1", (sid,mac,kind))
            count = core.store.rows('SELECT COUNT(*) AS count FROM ble_observations WHERE sensor_id=? AND address=? AND address_type=? AND timestamp>=?', (sid,mac,kind,core.store.ble_window_start()))[0]['count']
            summary = identify({**rows[0], **label, 'observed_name': named[0]['local_name'] if named else None, 'observation_count':count, 'window_hours':1})
        return {'sensor_id':sid,'address':mac,'address_type':kind,'advertiser':summary,
                'label':label,'observations':rows,'sample_limit':100}

    @app.get('/api/ble/labels')
    def ble_labels():
        return core.store.rows('SELECT * FROM ble_labels ORDER BY updated_at DESC LIMIT 1024')

    @app.post('/api/ble/label')
    def ble_label(values: dict, request: Request):
        authorize(request)
        try:
            if values.keys() - {'sensor_id','address','address_type','alias','notes'}:
                raise ValueError('Unknown BLE label field')
            sid, mac, kind = ble_identity(values.get('sensor_id'), values.get('address'), values.get('address_type'))
            alias, notes = values.get('alias',''), values.get('notes','')
            if not isinstance(alias,str) or len(alias)>80 or any(not c.isprintable() for c in alias):
                raise ValueError('Alias must be up to 80 printable characters')
            if not isinstance(notes,str) or len(notes)>1000 or any(not c.isprintable() and c not in '\n\t' for c in notes):
                raise ValueError('Notes must be up to 1000 printable characters/newlines')
            return core.store.save_ble_label(sid,mac,kind,alias.strip(),notes.strip())
        except (ValueError, TypeError) as exc:
            raise HTTPException(400,str(exc)) from exc

    @app.get('/api/alert-sources')
    def alert_sources():
        return core.store.alert_sources()

    @app.get('/api/mac/{address}')
    def mac_details(address: str):
        try:
            mac = normalize_mac(address)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {'mac': mac, 'observations': core.store.mac_details(mac),
                'alert_sources': core.store.alert_sources()}

    @app.get('/api/mac/{address}/vendor')
    def vendor_details(address: str, refresh: bool = False):
        try:
            return vendors.lookup(address, refresh)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return app
