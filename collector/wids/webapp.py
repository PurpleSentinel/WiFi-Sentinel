"""Local-only dashboard API; do not expose to the internet without auth/TLS."""
from contextlib import asynccontextmanager
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import Settings
from .engine import Engine, serial_loop


WEB_ROOT = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings, engine: Engine | None = None) -> FastAPI:
    core = engine or Engine(settings)
    stop = threading.Event()
    thread = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal thread
        if settings.serial_port:
            thread = threading.Thread(target=serial_loop, args=(core, stop), daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=3)
        core.store.close()

    app = FastAPI(title="WiFi Sentinel", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)

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

    return app
