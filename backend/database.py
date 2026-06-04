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

    Base.metadata.create_all(bind=_engine)

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


# ── Phase 3: FTS5 Full-Text Search ─────────────────────────────

def _init_fts5(engine):
    """Create FTS5 virtual table for channel search (SQLite only)."""
    from sqlalchemy import text
    import sqlite3
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        # Check if FTS5 is available
        cursor.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')")
        if not cursor.fetchone()[0]:
            return

        # Create FTS5 table if not exists
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS channels_fts USING fts5(
                name, name_original, group_name, tvg_id,
                content='canonical_channels', content_rowid='rowid'
            )
        """)
        # Populate if empty
        cursor.execute("SELECT COUNT(*) FROM channels_fts")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO channels_fts(rowid, name, name_original, group_name, tvg_id)
                SELECT rowid, name, name_original, "group", tvg_id
                FROM canonical_channels
            """)
        # Create triggers to keep FTS in sync
        cursor.executescript("""
            CREATE TRIGGER IF NOT EXISTS channels_fts_insert AFTER INSERT ON canonical_channels BEGIN
                INSERT INTO channels_fts(rowid, name, name_original, group_name, tvg_id)
                VALUES (new.rowid, new.name, new.name_original, new."group", new.tvg_id);
            END;
            CREATE TRIGGER IF NOT EXISTS channels_fts_delete AFTER DELETE ON canonical_channels BEGIN
                INSERT INTO channels_fts(channels_fts, rowid, name, name_original, group_name, tvg_id)
                VALUES ('delete', old.rowid, old.name, old.name_original, old."group", old.tvg_id);
            END;
            CREATE TRIGGER IF NOT EXISTS channels_fts_update AFTER UPDATE ON canonical_channels BEGIN
                INSERT INTO channels_fts(channels_fts, rowid, name, name_original, group_name, tvg_id)
                VALUES ('delete', old.rowid, old.name, old.name_original, old."group", old.tvg_id);
                INSERT INTO channels_fts(rowid, name, name_original, group_name, tvg_id)
                VALUES (new.rowid, new.name, new.name_original, new."group", new.tvg_id);
            END;
        """)
        conn.commit()
        cursor.close()
    except (sqlite3.OperationalError, Exception):
        pass  # FTS5 not available or not on SQLite


def fts_search_channels(db, query: str, limit: int = 100) -> list[str]:
    """
    Phase 3: full-text search using SQLite FTS5.

    Returns list of canonical_channel rowids matching the query.
    Falls back to ILIKE if FTS5 is not available.
    """
    from backend.models import CanonicalChannel
    import sqlite3
    try:
        conn = db.bind.raw_connection()
        cursor = conn.cursor()
        # Use FTS5 with prefix matching
        cursor.execute(
            "SELECT rowid FROM channels_fts WHERE channels_fts MATCH ? ORDER BY rank LIMIT ?",
            (f"{query}*", limit),
        )
        rowids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        if rowids:
            return rowids
    except (sqlite3.OperationalError, Exception):
        pass

    # Fallback: ILIKE search
    ids = db.query(CanonicalChannel.id).filter(
        CanonicalChannel.name.ilike(f"%{query}%")
    ).limit(limit).all()
    return [id for (id,) in ids]


def get_db():
    """FastAPI dependency: yields a session and closes it on teardown."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def fts_search_channels(db, query: str, limit: int = 100) -> list[str]:
    """Simple ILIKE fallback (no FTS)."""
    from backend.models import CanonicalChannel
    ids = db.query(CanonicalChannel.id).filter(
        CanonicalChannel.name.ilike(f"%{query}%")
    ).limit(limit).all()
    return [id for (id,) in ids]
