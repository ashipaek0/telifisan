"""
Telifisan — FastAPI application entry point.
Stripped to core: ingest, validate, output.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.config import get_config, generate_api_key, load_config as _load_config
from backend.database import init_db, get_session
from backend.models import SystemConfig, OutputProfile, OutputMode, CanonicalChannel, ValidationStatus
from backend.utils.logger import write_log, setup_logging, get_logger

from backend.api.health import router as health_router
from backend.api.sources import router as sources_router
from backend.api.channels import router as channels_router
from backend.api.profiles import router as profiles_router
from backend.api.tasks import router as tasks_router
from backend.api.config import router as config_router
from backend.services.output import generate_profile_output, _select_best_stream, _sort_channels, _generate_m3u

API_START = datetime.now(timezone.utc)
_output_cache: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    config = _load_config()
    data_dir = config["app"]["data_dir"]
    os.makedirs(data_dir, exist_ok=True)
    
    setup_logging()
    logger = get_logger("telifisan")
    logger.info("Starting Telifisan")

    init_db(config)

    # Run Alembic migrations
    _run_alembic_migrations(logger)

    # Seed default data
    _seed_defaults(logger)

    yield


def _run_alembic_migrations(logger):
    """Run Alembic database migrations."""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command
        
        alembic_ini = Path(__file__).parent / "alembic.ini"
        if alembic_ini.exists():
            cfg = AlembicConfig(str(alembic_ini))
            cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
            command.upgrade(cfg, "head")
    except Exception:
        pass  # Silently continue if migrations fail


def _seed_defaults(logger):
    """Seed default API key and output profile if they don't exist."""
    session = get_session()
    try:
        # Generate API key if not exists
        if not session.query(SystemConfig).filter_by(key="api_key").first():
            key = generate_api_key()
            session.add(SystemConfig(key="api_key", value=key))
            session.commit()
            logger.info(f"API key generated: {key[:8]}...")

        # Create default output profile if not exists
        if not session.query(OutputProfile).filter_by(enabled=True, deleted_at=None).first():
            profile = OutputProfile(
                name="Default",
                mode=OutputMode.DIRECT,
                include_dead_channels=False
            )
            session.add(profile)
            session.commit()
            logger.info("Default output profile created")
    finally:
        session.close()


app = FastAPI(
    title="Telifisan",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Auth middleware ────────────────────────────────────────────

def _verify_token(token: str) -> bool:
    """Verify if the provided token matches the stored API key."""
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
    """Authenticate API requests requiring write access."""
    path = request.url.path
    
    # Non-API paths always pass through
    if not path.startswith("/api/v1/"):
        return await call_next(request)

    # GET requests are public (read-only)
    if request.method == "GET":
        return await call_next(request)

    # Write operations (POST, PUT, DELETE) require API key
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and _verify_token(auth_header[7:]):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Valid API key required for write operations. Use Authorization: Bearer <api_key>"
            },
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
    """Serve the default M3U playlist for the enabled output profile."""
    log = get_logger("telifisan")
    db = get_session()
    try:
        profile = db.query(OutputProfile).filter(
            OutputProfile.enabled.is_(True),
            OutputProfile.deleted_at.is_(None)
        ).first()
        
        if not profile:
            return StreamingResponse(content=iter(["#EXTM3U\n"]), media_type="audio/x-mpegurl")

        # Check cache
        cached = _output_cache.get(profile.id)
        if not cached:
            # Generate output
            generate_profile_output(profile.id, db)
            
            channels = db.query(CanonicalChannel).all()
            
            # Filter to only ALIVE channels unless profile overrides
            if not profile.include_dead_channels:
                channels = [
                    ch for ch in channels 
                    if ch.validation_status == ValidationStatus.ALIVE
                ]
            
            # Select best streams
            channel_streams = []
            for channel in channels:
                best = _select_best_stream(channel, profile)
                if best:
                    channel_streams.append((channel, best))
            
            channel_streams = _sort_channels(channel_streams)
            m3u_content = _generate_m3u(channel_streams, profile)
            _output_cache[profile.id] = {"m3u": m3u_content}
        else:
            m3u_content = cached.get("m3u", "")
            
        return StreamingResponse(
            content=iter([m3u_content]),
            media_type="audio/x-mpegurl"
        )
    except Exception as e:
        log.exception(f"M3U endpoint error: {e}")
        return StreamingResponse(
            content=iter(["#EXTM3U\n"]),
            media_type="audio/x-mpegurl"
        )
    finally:
        db.close()


# ── Frontend static files ──────────────────────────────────────

frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "build"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA, catching all non-API routes."""
        if full_path.startswith("api/"):
            return JSONResponse(
                {"success": False, "error": "Not found"},
                status_code=404
            )
        index = frontend_dir / "index.html"
        if index.exists():
            return HTMLResponse(content=index.read_text())
        return JSONResponse(
            {"success": False, "error": "Frontend not built"},
            status_code=404
        )


# ── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    config = get_config()
    port = int(os.environ.get("TELIFISAN_PORT", config["app"]["port"]))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
