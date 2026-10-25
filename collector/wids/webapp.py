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

    app = FastAPI(title="WiFi Sentinel", version="1.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)

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
        return core.store.rows("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))

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
