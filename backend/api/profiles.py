"""
Telifisan — Output Profiles API.
Simplified: DIRECT mode only, M3U generation + serving.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import OutputProfile, OutputMode, CanonicalChannel
from backend.common.responses import success_response

router = APIRouter(tags=["profiles"])

# Output cache moved to main.py for centralized management
_output_cache: dict[str, dict] = {}


class ProfileCreate(BaseModel):
    """Schema for creating an output profile."""
    name: str
    include_dead_channels: bool = False
    min_uptime_percent: float = 0
    generate_schedule: str | None = None


class ProfileUpdate(BaseModel):
    """Schema for updating an output profile."""
    name: str | None = None
    enabled: bool | None = None
    include_dead_channels: bool | None = None
    min_uptime_percent: float | None = None
    generate_schedule: str | None = None


def _profile_to_dict(p: OutputProfile) -> dict:
    """Convert an OutputProfile model to a dictionary."""
    return {
        "id": p.id,
        "name": p.name,
        "enabled": p.enabled,
        "include_dead_channels": p.include_dead_channels,
        "min_uptime_percent": p.min_uptime_percent,
        "generate_schedule": p.generate_schedule,
        "last_generated": p.last_generated.isoformat() if p.last_generated else None,
        "channel_count": p.channel_count,
        "m3u_url_path": p.m3u_url_path,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    """List all active output profiles."""
    profiles = db.query(OutputProfile).filter(OutputProfile.deleted_at.is_(None)).all()
    return success_response(data=[_profile_to_dict(p) for p in profiles])


@router.post("/profiles")
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    """Create a new output profile."""
    profile = OutputProfile(
        name=body.name,
        mode=OutputMode.DIRECT,
        include_dead_channels=body.include_dead_channels,
        min_uptime_percent=body.min_uptime_percent,
        generate_schedule=body.generate_schedule,
        m3u_url_path=f"/output/{body.name.lower().replace(' ', '-')}.m3u",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return success_response(data=_profile_to_dict(profile))


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    """Get a specific output profile by ID."""
    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return success_response(data=_profile_to_dict(profile))


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileUpdate, db: Session = Depends(get_db)):
    """Update an existing output profile."""
    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    updatable_fields = ["name", "enabled", "include_dead_channels", "min_uptime_percent", "generate_schedule"]
    for field in updatable_fields:
        value = getattr(body, field, None)
        if value is not None:
            setattr(profile, field, value)
    
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return success_response(data=_profile_to_dict(profile))


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    """Soft-delete an output profile."""
    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return success_response(data={"deleted": profile_id})


@router.post("/profiles/{profile_id}/generate")
def generate_profile(profile_id: str, db: Session = Depends(get_db)):
    """Generate M3U output for a profile."""
    from backend.services.output import (
        generate_profile_output,
        _select_best_stream,
        _sort_channels,
        _generate_m3u,
    )
    
    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    generate_profile_output(profile_id, db)
    
    channels = db.query(CanonicalChannel).all()
    channel_streams = [
        (ch, best) for ch in channels
        if (best := _select_best_stream(ch, profile)) is not None
    ]
    channel_streams = _sort_channels(channel_streams)
    m3u_content = _generate_m3u(channel_streams, profile)
    _output_cache[profile_id] = {"m3u": m3u_content}
    
    return success_response(data={
        "channel_count": profile.channel_count,
        "generated_at": profile.last_generated.isoformat() if profile.last_generated else None,
    })


@router.get("/profiles/{profile_id}/m3u")
def serve_m3u(profile_id: str, db: Session = Depends(get_db)):
    """Serve the M3U playlist for a profile."""
    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    cached = _output_cache.get(profile_id)
    if not cached:
        # Import here to avoid circular dependency
        from .profiles import generate_profile as gen_profile
        generate_profile(profile_id, db)
        cached = _output_cache.get(profile_id, {})
    
    m3u_content = cached.get("m3u", "")
    return StreamingResponse(content=iter([m3u_content]), media_type="audio/x-mpegurl")
