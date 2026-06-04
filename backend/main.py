"""
Telifisan — FastAPI application entry point.
Stripped to core: ingest, validate, output.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from backend.config import get_config, generate_api_key
from backend.database import init_db, get_session
from backend.models import SystemConfig
from backend.utils.logger import write_log, setup_logging, get_logger

from backend.api.health import router as health_router
from backend.api.sources import router as sources_router
from backend.api.channels import router as channels_router
from backend.api.profiles import router as profiles_router
from backend.api.tasks import router as tasks_router
from backend.api.config import router as config_router
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

API_START = datetime.now(timezone.utc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    os.makedirs(config["app"]["data_dir"], exist_ok=True)
    setup_logging()
    logger = get_logger("telifisan")
    logger.info("Starting Telifisan")

    init_db(config)

    # Alembic migrations
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command
        alembic_ini = Path(__file__).parent / "alembic.ini"
        if alembic_ini.exists():
            cfg = AlembicConfig(str(alembic_ini))
            cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
            command.upgrade(cfg, "head")
    except Exception:
        pass

    # Seed defaults
    session = get_session()
    try:
        if not session.query(SystemConfig).filter_by(key="api_key").first():
            key = generate_api_key()
            session.add(SystemConfig(key="api_key", value=key))
            session.commit()
            logger.info(f"API key generated: {key[:8]}...")

        # Default output profile
        from backend.models import OutputProfile, OutputMode
        if not session.query(OutputProfile).filter_by(enabled=True, deleted_at=None).first():
            p = OutputProfile(name="Default", mode=OutputMode.DIRECT, include_dead_channels=False)
            session.add(p)
            session.commit()
            logger.info("Default output profile created")
    finally:
        session.close()

    yield


app = FastAPI(
    title="Telifisan",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Auth middleware ────────────────────────────────────────────

def _verify_key(token: str) -> bool:
    if not token:
        return False
    session = get_session()
    try:
        row = session.query(SystemConfig).filter_by(key="api_key").first()
        return bool(row and row.value == token)
    finally:
        session.close()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Non-API paths always pass through
    if not path.startswith("/api/v1/"):
        return await call_next(request)

    # GET requests are public (read-only)
    if request.method == "GET":
        return await call_next(request)

    # Write operations (POST, PUT, DELETE) require API key
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and _verify_key(auth[7:]):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={
            "success": False, "data": None,
            "error": {"code": "UNAUTHORIZED", "message": "Valid API key required for write operations. Use Authorization: Bearer <api_key>"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ── Routers ────────────────────────────────────────────────────



app.include_router(health_router)
app.include_router(sources_router, prefix="/api/v1")
app.include_router(channels_router, prefix="/api/v1")
app.include_router(profiles_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(config_router, prefix="/api/v1")


# ── Public M3U endpoint ────────────────────────────────────────




@app.get("/output/default.m3u")
def serve_default_m3u():
    import logging
    log = logging.getLogger("telifisan")
    db = get_session()
    try:
        from backend.models import OutputProfile
        profile = db.query(OutputProfile).filter(OutputProfile.enabled.is_(True), OutputProfile.deleted_at.is_(None)).first()
        if not profile:
            return StreamingResponse(content=iter(["#EXTM3U\n"]), media_type="audio/x-mpegurl")

        from backend.api.profiles import _output_cache
        cached = _output_cache.get(profile.id)
        if not cached:
            from backend.services.output import generate_profile_output, _select_best_stream, _sort_channels, _generate_m3u
            from backend.models import CanonicalChannel, ValidationStatus
            generate_profile_output(profile.id, db)
            channels = db.query(CanonicalChannel).all()
            # Filter to only ALIVE channels unless profile overrides
            if not profile.include_dead_channels:
                channels = [ch for ch in channels if ch.validation_status == ValidationStatus.ALIVE]
            ch_streams = []
            for ch in channels:
                best = _select_best_stream(ch, profile)
                if best:
                    ch_streams.append((ch, best))
            ch_streams = _sort_channels(ch_streams)
            m3u = _generate_m3u(ch_streams, profile)
            _output_cache[profile.id] = {"m3u": m3u}
        else:
            m3u = cached.get("m3u", "")
        return StreamingResponse(content=iter([m3u]), media_type="audio/x-mpegurl")
    except Exception as e:
        log.exception(f"M3U endpoint error: {e}")
        return StreamingResponse(content=iter(["#EXTM3U\n"]), media_type="audio/x-mpegurl")
    finally:
        db.close()


# ── Frontend static files (catch-all, defined last so specific routes take priority) ──

frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "build"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"success": False, "error": "Not found"}, status_code=404)
        index = frontend_dir / "index.html"
        if index.exists():
            return HTMLResponse(content=index.read_text())
        return JSONResponse({"success": False, "error": "Frontend not built"}, status_code=404)


# ── Entry Point ────────────────────────────────────────────────

def load_config():
    from backend.config import load_config as _lc
    return _lc()

if __name__ == "__main__":
    import uvicorn
    config = get_config()
    port = int(os.environ.get("TELIFISAN_PORT", config["app"]["port"]))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
