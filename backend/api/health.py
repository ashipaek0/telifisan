"""
Telifisan — Health, dashboard, and logs endpoints.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text, func, select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    Source, SourceStream, CanonicalChannel, OutputProfile, TaskLog, ValidationStatus,
)

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/v1/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "success": True,
        "data": {"status": "healthy" if db_ok else "degraded", "database": "connected" if db_ok else "disconnected"},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/dashboard")
@router.get("/api/v1/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """Dashboard stats — channels with active streams only."""
    now = datetime.now(timezone.utc)

    total_sources = db.query(func.count(Source.id)).filter(Source.deleted_at.is_(None)).scalar() or 0

    active_ids = select(SourceStream.canonical_channel_id).where(
        SourceStream.deleted_at.is_(None), SourceStream.canonical_channel_id.isnot(None),
    ).distinct()

    def ch_count(status=None):
        q = db.query(func.count(CanonicalChannel.id)).filter(CanonicalChannel.id.in_(active_ids))
        if status:
            q = q.filter(CanonicalChannel.validation_status == status)
        return q.scalar() or 0

    alive = ch_count(ValidationStatus.ALIVE)
    soft_dead = ch_count(ValidationStatus.SOFT_DEAD)
    hard_dead = ch_count(ValidationStatus.HARD_DEAD)
    unknown = ch_count(ValidationStatus.UNKNOWN)
    total_profiles = db.query(func.count(OutputProfile.id)).filter(OutputProfile.deleted_at.is_(None)).scalar() or 0

    # Latest run per task type (deduplicated)
    task_names = db.query(TaskLog.task_name).distinct().all()
    recent_tasks = []
    for (name,) in task_names:
        last = db.query(TaskLog).filter(TaskLog.task_name == name).order_by(TaskLog.created_at.desc()).first()
        if last:
            recent_tasks.append(last)
    recent_tasks.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
    recent_tasks = recent_tasks[:5]

    from backend.services.scheduler import get_progress as _get_progress
    task_progress = list(_get_progress().values())

    return {
        "success": True,
        "data": {
            "sources": total_sources,
            "channels": {"total": ch_count(), "alive": alive, "soft_dead": soft_dead, "hard_dead": hard_dead, "unknown": unknown},
            "profiles": total_profiles,
            "recent_tasks": [
                {"task_name": t.task_name, "status": t.status.value if t.status else None,
                 "started_at": t.started_at.isoformat() if t.started_at else None, "message": t.message}
                for t in recent_tasks
            ],
            "task_progress": task_progress,
        },
        "error": None,
        "timestamp": now.isoformat(),
    }


@router.get("/api/v1/logs")
def get_logs(lines: int = 200, level: str = "DEBUG"):
    from backend.utils.logger import read_log_file
    return {
        "success": True,
        "data": read_log_file(lines=min(lines, 500), level=level.upper()),
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
