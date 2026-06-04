"""
Telifisan v2.0 — Sources API.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Source, SourceStream, SourceType

router = APIRouter(tags=["sources"])


class SourceCreate(BaseModel):
    name: str
    type: str  # M3U_URL, M3U_FILE, XTREAM_CODES_API
    url: str | None = None
    file_path: str | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    auth_headers: dict | None = None
    priority: int = 100
    ingest_schedule: str | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    file_path: str | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    auth_headers: dict | None = None
    enabled: bool | None = None
    priority: int | None = None
    ingest_schedule: str | None = None


def _source_to_dict(s: Source) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "type": s.type.value if s.type else None,
        "url": s.url,
        "file_path": s.file_path,
        "auth_username": s.auth_username,
        "auth_password": "***" if s.auth_password else None,
        "auth_headers": s.auth_headers,
        "enabled": s.enabled,
        "priority": s.priority,
        "last_ingest": s.last_ingest.isoformat() if s.last_ingest else None,
        "last_ingest_status": s.last_ingest_status.value if s.last_ingest_status else None,
        "last_ingest_error": s.last_ingest_error,
        "ingest_schedule": s.ingest_schedule,
        "stream_count": s.stream_count,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = db.query(Source).filter(Source.deleted_at.is_(None)).all()
    return {
        "success": True,
        "data": [_source_to_dict(s) for s in sources],
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/sources")
def create_source(body: SourceCreate, db: Session = Depends(get_db)):
    try:
        src_type = SourceType(body.type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source type: {body.type}")

    source = Source(
        name=body.name,
        type=src_type,
        url=body.url,
        file_path=body.file_path,
        auth_username=body.auth_username,
        auth_password=body.auth_password,
        auth_headers=body.auth_headers,
        priority=body.priority,
        ingest_schedule=body.ingest_schedule,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {
        "success": True,
        "data": _source_to_dict(source),
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/sources/{source_id}")
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id, deleted_at=None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {
        "success": True,
        "data": _source_to_dict(source),
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id, deleted_at=None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.name is not None:
        source.name = body.name
    if body.url is not None:
        source.url = body.url
    if body.file_path is not None:
        source.file_path = body.file_path
    if body.auth_username is not None:
        source.auth_username = body.auth_username
    if body.auth_password is not None:
        source.auth_password = body.auth_password
    if body.auth_headers is not None:
        source.auth_headers = body.auth_headers
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.priority is not None:
        source.priority = body.priority
    if body.ingest_schedule is not None:
            source.ingest_schedule = body.ingest_schedule

    source.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return {
        "success": True,
        "data": _source_to_dict(source),
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id, deleted_at=None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Cascade soft-delete to all active streams from this source
    now = datetime.now(timezone.utc)
    source.deleted_at = now
    db.query(SourceStream).filter(
        SourceStream.source_id == source_id,
        SourceStream.deleted_at.is_(None),
    ).update({"deleted_at": now}, synchronize_session=False)
    db.commit()
    return {
        "success": True,
        "data": {"deleted": source_id},
        "error": None,
        "timestamp": now.isoformat(),
    }


@router.post("/sources/{source_id}/ingest")
def trigger_ingest(source_id: str, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id, deleted_at=None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from backend.services.ingest import ingest_source
    task_log = ingest_source(source_id, db)
    return {
        "success": task_log.status.value == "SUCCESS",
        "data": {
            "task_log_id": task_log.id,
            "status": task_log.status.value if task_log.status else None,
            "message": task_log.message,
            "stats": task_log.stats,
        },
        "error": None if task_log.status.value == "SUCCESS" else {"code": "INGEST_FAILED", "message": task_log.message, "details": {}},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/sources/{source_id}/streams")
def list_source_streams(
    source_id: str,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    per_page = min(per_page, 200)
    total = db.query(SourceStream).filter(
        SourceStream.source_id == source_id,
        SourceStream.deleted_at.is_(None),
    ).count()
    streams = db.query(SourceStream).filter(
        SourceStream.source_id == source_id,
        SourceStream.deleted_at.is_(None),
    ).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "success": True,
        "data": [
            {
                "id": s.id,
                "name": s.name,
                "url": s.url,
                "group": s.group,
                "tvg_id": s.tvg_id,
                "logo": s.logo,
                "canonical_channel_id": s.canonical_channel_id,
                "deleted_at": s.deleted_at.isoformat() if s.deleted_at else None,
            }
            for s in streams
        ],
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": max(1, (total + per_page - 1) // per_page)},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/sources/{source_id}/streams/bulk")
def bulk_delete_streams(source_id: str, body: dict, db: Session = Depends(get_db)):
    """Bulk soft-delete streams from a source."""
    stream_ids = body.get("stream_ids", [])
    if not stream_ids:
        raise HTTPException(status_code=400, detail="No stream_ids provided")

    count = (
        db.query(SourceStream)
        .filter(
            SourceStream.id.in_(stream_ids),
            SourceStream.source_id == source_id,
            SourceStream.deleted_at.is_(None),
        )
        .update({"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    db.commit()
    return {
        "success": True,
        "data": {"deleted": count},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/sources/{source_id}/validate")
def validate_source(source_id: str, db: Session = Depends(get_db)):
    """Validate streams from a single source only."""
    source = db.query(Source).filter_by(id=source_id, deleted_at=None).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    from backend.services.validation import validate_all_streams
    from backend.services.validation import check_stream
    from backend.models import SourceStream, TaskLog, TaskStatus
    from datetime import datetime, timezone

    task_log = TaskLog(task_name="validate_source", status=TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))
    db.add(task_log)
    db.commit()

    streams = db.query(SourceStream).filter(
        SourceStream.source_id == source_id, SourceStream.deleted_at.is_(None)
    ).all()

    checked = 0
    alive = 0
    dead = 0
    errors = 0

    for stream in streams:
        try:
            record = check_stream(stream, db)
            checked += 1
            if record and record.success:
                alive += 1
            elif record:
                dead += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    # Update channel statuses for affected channels
    from backend.services.validation import _update_channel_statuses
    _update_channel_statuses(db)

    task_log.status = TaskStatus.SUCCESS
    task_log.message = f"Checked {checked} streams: {alive} alive, {dead} dead, {errors} errors"
    task_log.stats = {"checked": checked, "alive": alive, "dead": dead, "errors": errors}
    task_log.completed_at = datetime.now(timezone.utc)
    if task_log.started_at:
        task_log.duration_ms = int((task_log.completed_at - task_log.started_at).total_seconds() * 1000)
    db.commit()

    return {
        "success": True,
        "data": {"task_log_id": task_log.id, "status": task_log.status.value, "message": task_log.message, "stats": task_log.stats},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
