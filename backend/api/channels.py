"""
Telifisan — Channels API.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    CanonicalChannel, SourceStream, ValidationStatus,
)

router = APIRouter(tags=["channels"])


def _channel_to_dict(ch: CanonicalChannel) -> dict:
    return {
        "id": ch.id,
        "name": ch.name,
        "name_original": ch.name_original,
        "group": ch.group,
        "country": ch.country,
        "language": ch.language,
        "logo": ch.logo,
        "tvg_id": ch.tvg_id,
        "last_validation": ch.last_validation.isoformat() if ch.last_validation else None,
        "validation_status": ch.validation_status.value if ch.validation_status else None,
        "uptime_percent": ch.uptime_percent,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


@router.get("/channels")
def list_channels(
    q: str | None = Query(None),
    status: str | None = Query(None),
    group: str | None = Query(None),
    country: str | None = Query(None),
    has_streams: bool | None = Query(None),
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(CanonicalChannel)

    if has_streams is not None:
        active_ids = (
            db.query(SourceStream.canonical_channel_id)
            .filter(SourceStream.deleted_at.is_(None), SourceStream.canonical_channel_id.isnot(None))
            .distinct()
        )
        if has_streams:
            query = query.filter(CanonicalChannel.id.in_(active_ids))
        else:
            query = query.filter(~CanonicalChannel.id.in_(active_ids))

    if q:
        query = query.filter(
            (CanonicalChannel.name.ilike(f"%{q}%")) |
            (CanonicalChannel.name_original.ilike(f"%{q}%"))
        )
    if status:
        try:
            vs = ValidationStatus(status.upper())
            query = query.filter(CanonicalChannel.validation_status == vs)
        except ValueError:
            pass
    if group:
        query = query.filter(CanonicalChannel.group.ilike(f"%{group}%"))
    if country:
        query = query.filter(CanonicalChannel.country == country.upper())

    per_page = min(per_page, 200)
    total = query.count()
    channels = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "success": True,
        "data": [_channel_to_dict(ch) for ch in channels],
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": max(1, (total + per_page - 1) // per_page)},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/channels/{channel_id}")
def get_channel(channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(CanonicalChannel).filter_by(id=channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    stream_data = [
        {"id": s.id, "source_id": s.source_id, "name": s.name, "url": s.url, "group": s.group}
        for s in ch.source_streams if s.deleted_at is None
    ]
    return {
        "success": True,
        "data": {**_channel_to_dict(ch), "source_streams": stream_data},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    ch = db.query(CanonicalChannel).filter_by(id=channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.query(SourceStream).filter(SourceStream.canonical_channel_id == channel_id).update({"canonical_channel_id": None})
    db.delete(ch)
    db.commit()
    return {
        "success": True,
        "data": {"deleted": channel_id},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/channels/{channel_id}/validation-history")
def get_validation_history(channel_id: str, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    per_page = min(per_page, 200)
    from backend.models import ValidationRecord
    stream_ids = [s.id for s in db.query(SourceStream).filter(
        SourceStream.canonical_channel_id == channel_id, SourceStream.deleted_at.is_(None),
    ).all()]
    if not stream_ids:
        return {"success": True, "data": [], "pagination": {"page": page, "per_page": per_page, "total": 0, "pages": 1}, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}
    total = db.query(ValidationRecord).filter(ValidationRecord.source_stream_id.in_(stream_ids)).count()
    records = db.query(ValidationRecord).filter(ValidationRecord.source_stream_id.in_(stream_ids)).order_by(ValidationRecord.checked_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "success": True,
        "data": [{"id": r.id, "checked_at": r.checked_at.isoformat() if r.checked_at else None, "success": r.success, "codec": r.codec, "resolution": r.resolution, "checker_tool": r.checker_tool.value if r.checker_tool else None, "error_message": r.error_message} for r in records],
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": max(1, (total + per_page - 1) // per_page)},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
