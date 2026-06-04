"""
Telifisan v2.0 — Database initialization and session management.

Uses sync SQLAlchemy with ThreadPoolExecutor isolation per the spec.
Migration to async SQLAlchemy is a Phase 2 upgrade.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

from .config import get_config
from .models import Base

_engine = None
_SessionLocal = None


def get_database_url(config=None) -> str:
    """Resolve the database URL from env var or config.

    Phase 3: supports SQLite (default) and PostgreSQL.
    Set TELIFISAN_DB_URL to override, e.g.:
      postgresql://user:pass@host:5432/telifisan
    """
    if config is None:
        config = get_config()
    env_url = os.environ.get("TELIFISAN_DB_URL", "")
    if env_url:
        return env_url
    config_url = config.get("database", {}).get("url", "")
    if config_url:
        return config_url
    driver = config.get("database", {}).get("driver", "sqlite")
    if driver == "postgresql":
        pg_host = config.get("database", {}).get("host", "localhost")
        pg_port = config.get("database", {}).get("port", 5432)
        pg_db = config.get("database", {}).get("name", "telifisan")
        pg_user = config.get("database", {}).get("user", "telifisan")
        pg_pass = config.get("database", {}).get("password", "")
        return f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    data_dir = config.get("app", {}).get("data_dir", "/data")
    db_path = os.path.join(data_dir, "telifisan.db")
    return f"sqlite:///{db_path}"


def init_db(config=None):
    """Initialize the database engine and create all tables."""
    global _engine, _SessionLocal

    if config is None:
        config = get_config()

    db_url = get_database_url(config)
    is_sqlite = db_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    if is_sqlite:
        # WAL mode: concurrent reads during writes, crash-resistant journaling
        connect_args["timeout"] = 15  # seconds to wait for write lock
        from sqlalchemy import event

        def _enable_wal(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=10000")  # 10s busy timeout
                cursor.close()
            except Exception:
                pass

    engine_kwargs = {
        "connect_args": connect_args,
        "echo": False,
    }
    if is_sqlite:
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs["poolclass"] = QueuePool
        engine_kwargs["pool_size"] = config.get("database", {}).get("pool_size", 20)
        engine_kwargs["max_overflow"] = config.get("database", {}).get("max_overflow", 10)
        engine_kwargs["pool_pre_ping"] = True

    _engine = create_engine(db_url, **engine_kwargs)

    if is_sqlite:
        event.listen(_engine, "connect", _enable_wal)

    # Skip create_all on startup — migrations handle schema (avoids write lock)
    # Base.metadata.create_all(bind=_engine)

    _SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    return _engine


def get_session() -> Session:
    """Get a new database session. Use as a context manager or with try/finally."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def get_db():
    """FastAPI dependency: yields a session and closes it on teardown."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def fts_search_channels(db, query: str, limit: int = 100) -> list[str]:
    """Simple ILIKE fallback for channel search."""
    from backend.models import CanonicalChannel
    ids = db.query(CanonicalChannel.id).filter(
        CanonicalChannel.name.ilike(f"%{query}%")
    ).limit(limit).all()
    return [id for (id,) in ids]
