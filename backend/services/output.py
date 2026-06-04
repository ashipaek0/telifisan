"""
Telifisan — M3U Output Generator.
DIRECT mode only — generates M3U of live channels.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.config import get_config
from backend.models import (
    CanonicalChannel, SourceStream, OutputProfile, ValidationStatus, TaskLog, TaskStatus,
)

logger = logging.getLogger("telifisan.output")


def generate_profile_output(profile_id: str, db: Session) -> TaskLog:
    task_log = TaskLog(task_name="generate_outputs", status=TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))
    db.add(task_log)
    db.commit()

    profile = db.query(OutputProfile).filter_by(id=profile_id, deleted_at=None).first()
    if not profile:
        task_log.status = TaskStatus.FAILED
        task_log.message = f"Profile {profile_id} not found"
        task_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        return task_log

    try:
        channels = db.query(CanonicalChannel).all()

        # Filter by included_sources
        if profile.included_sources:
            source_ids = set(profile.included_sources)
            channels = [ch for ch in channels if any(
                s.deleted_at is None and s.source_id in source_ids for s in ch.source_streams
            )]

        # Exclude dead channels
        if not profile.include_dead_channels:
            channels = [ch for ch in channels if ch.validation_status not in (ValidationStatus.HARD_DEAD,)]

        # Min uptime
        if profile.min_uptime_percent and profile.min_uptime_percent > 0:
            channels = [ch for ch in channels if (ch.uptime_percent or 0) >= profile.min_uptime_percent]

        # Select best stream per channel
        channel_streams = []
        for ch in channels:
            best = _select_best_stream(ch, profile)
            if best:
                channel_streams.append((ch, best))

        channel_streams.sort(key=lambda x: (x[0].name or "").lower())

        # M3U is generated and cached by the API layer; we just mark the profile as generated
        profile.last_generated = datetime.now(timezone.utc)
        profile.channel_count = len(channel_streams)
        db.commit()

        task_log.status = TaskStatus.SUCCESS
        task_log.message = f"Generated output: {len(channel_streams)} channels"
        task_log.stats = {"channels": len(channel_streams)}
        task_log.completed_at = datetime.now(timezone.utc)
        if task_log.started_at:
            task_log.duration_ms = int((task_log.completed_at - task_log.started_at).total_seconds() * 1000)

    except Exception as e:
        logger.exception(f"Output generation failed: {e}")
        task_log.status = TaskStatus.FAILED
        task_log.message = str(e)
        task_log.completed_at = datetime.now(timezone.utc)

    db.commit()
    return task_log


def _select_best_stream(channel: CanonicalChannel, profile: OutputProfile) -> Optional[SourceStream]:
    streams = [s for s in channel.source_streams if s.deleted_at is None]
    if not streams:
        return None
    streams.sort(key=lambda s: s.source.priority if s.source else 999)
    return streams[0]


def _sort_channels(channel_streams: List[tuple], sort_by=None) -> List[tuple]:
    channel_streams.sort(key=lambda x: (x[0].name or "").lower())
    return channel_streams


def _generate_m3u(channel_streams: List[tuple], profile: OutputProfile) -> str:
    lines = ["#EXTM3U"]
    for channel, stream in channel_streams:
        url = stream.url  # DIRECT mode only
        extinf_parts = ['#EXTINF:-1']
        if channel.tvg_id:
            extinf_parts.append(f'tvg-id="{channel.tvg_id}"')
        if channel.name:
            extinf_parts.append(f'tvg-name="{channel.name}"')
        if channel.logo:
            extinf_parts.append(f'tvg-logo="{channel.logo}"')
        if channel.group:
            extinf_parts.append(f'group-title="{channel.group}"')
        extinf_line = " ".join(extinf_parts) + f",{channel.name or 'Unknown'}"
        lines.append(extinf_line)
        lines.append(url)
    return "\n".join(lines) + "\n"
