"""
Telifisan v2.0 — Source Ingestion Engine.

Fetches M3U/XMLTV/Xtream from sources, parses, creates SourceStreams,
and links to CanonicalChannels using tiered matching algorithm.
"""

import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

import requests
from sqlalchemy.orm import Session

from backend.config import get_config
from backend.models import (
    Source, SourceStream, CanonicalChannel, SourceType,
    IngestStatus, ValidationStatus, TaskLog, TaskStatus,
)
from backend.utils.m3u_parser import parse_m3u


def _normalize_name(name: str) -> str:
    """Simple name normalization for channel matching."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"\[hd\]|\[fhd\]|\[uhd\]|\|.*?\||\(.*?\)|\bhd\b|\bfhd\b|\buhd\b|\bhevc\b", "", n)
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r"\s+", " ", n)
    return n.strip()

logger = logging.getLogger("telifisan.ingest")


def ingest_source(source_id: str, db: Session) -> TaskLog:
    """
    Ingest a single source: fetch, parse, create/update streams, link to canonical channels.

    Returns the TaskLog entry for this ingest run.
    """
    task_log = TaskLog(
        task_name="ingest_source",
        status=TaskStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(task_log)
    db.commit()

    # B5: invalidate channel index cache at start of each ingest
    global _channel_index_cache
    _channel_index_cache = None

    source = db.query(Source).filter_by(id=source_id).first()
    if not source:
        task_log.status = TaskStatus.FAILED
        task_log.message = f"Source {source_id} not found"
        task_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        return task_log

    try:
        raw_streams, stats = _fetch_source_data(source)

        # Parse error threshold check — only if we actually got content
        total_lines = stats.get("total_lines", 0)
        fetch_errors = stats.get("errors", 0)

        if total_lines > 0:
            error_rate = fetch_errors / total_lines
            if error_rate > 0.05:
                task_log.status = TaskStatus.FAILED
                task_log.message = f"Parse error rate {error_rate:.1%} exceeds 5% threshold"
                task_log.stats = stats
                task_log.completed_at = datetime.now(timezone.utc)
                db.commit()
                return task_log

        # B2 fix: if fetch returned zero streams AND had errors, the source
        # itself is unreachable — don't delete existing streams.
        if not raw_streams and fetch_errors > 0:
            task_log.status = TaskStatus.FAILED
            task_log.message = "Source fetch failed — no data returned (network/auth error?)"
            task_log.stats = stats
            task_log.completed_at = datetime.now(timezone.utc)
            source.last_ingest_status = IngestStatus.FAILED
            source.last_ingest_error = "Source fetch returned zero streams"
            source.last_ingest = datetime.now(timezone.utc)
            db.commit()
            return task_log

        new_count = 0
        updated_count = 0
        deleted_count = 0

        # Track current stream URLs for soft-delete detection
        current_urls = {s["url"] for s in raw_streams}

        # B13 fix: only soft-delete AFTER processing all new streams,
        # so a mid-batch crash doesn't orphan data
        existing_streams = (
            db.query(SourceStream)
            .filter(SourceStream.source_id == source_id, SourceStream.deleted_at.is_(None))
            .all()
        )

        # Process each stream first
        for raw in raw_streams:
            stream = _upsert_source_stream(db, source_id, raw)
            if stream:
                if stream.created_at == stream.updated_at:
                    new_count += 1
                else:
                    updated_count += 1

                # Link to canonical channel
                _link_to_canonical(db, stream)

        # B12 fix: single commit after all streams are processed
        db.commit()

        # Then soft-delete streams that disappeared from the source
        for stream in existing_streams:
            if stream.url not in current_urls:
                stream.deleted_at = datetime.now(timezone.utc)
                deleted_count += 1

        # Update source stats
        source.last_ingest = datetime.now(timezone.utc)
        source.last_ingest_status = IngestStatus.SUCCESS
        source.stream_count = (
            db.query(SourceStream)
            .filter(SourceStream.source_id == source_id, SourceStream.deleted_at.is_(None))
            .count()
        )
        source.last_ingest_error = None

        task_log.status = TaskStatus.SUCCESS
        task_log.message = f"Ingested {new_count} new, {updated_count} updated, {deleted_count} deleted"
        task_log.stats = {
            **stats,
            "new": new_count,
            "updated": updated_count,
            "deleted": deleted_count,
        }

    except Exception as e:
        logger.exception(f"Ingest failed for source {source_id}: {e}")
        source.last_ingest_status = IngestStatus.FAILED
        source.last_ingest_error = str(e)
        source.last_ingest = datetime.now(timezone.utc)
        task_log.status = TaskStatus.FAILED
        task_log.message = str(e)

    task_log.completed_at = datetime.now(timezone.utc)
    if task_log.started_at:
        # Normalize both to UTC-aware to handle DB round-trip timezone stripping
        start = task_log.started_at
        end = task_log.completed_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        task_log.duration_ms = int((end - start).total_seconds() * 1000)
    db.commit()

    return task_log


def _fetch_source_data(source: Source) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Fetch and parse data from a source."""
    if source.type == SourceType.M3U_URL:
        headers = source.auth_headers or {}
        resp = requests.get(source.url, headers=headers, timeout=30)
        resp.raise_for_status()
        return parse_m3u(resp.text)

    elif source.type == SourceType.M3U_FILE:
        with open(source.file_path, "r", encoding="utf-8") as f:
            return parse_m3u(f.read())

    elif source.type == SourceType.XTREAM_CODES_API:
        return _fetch_xtream(source)

    return [], {}


def _fetch_xtream(source: Source) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Fetch streams from Xtream Codes API."""
    base_url = source.url.rstrip("/")
    username = source.auth_username or ""
    password = source.auth_password or ""

    streams: List[Dict[str, Any]] = []
    stats = {"total_lines": 0, "parsed": 0, "skipped": 0, "errors": 0}

    try:
        # Get categories
        cat_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_live_categories"
        cat_resp = requests.get(cat_url, timeout=30)
        cat_resp.raise_for_status()
        categories = cat_resp.json()
        stats["total_lines"] = len(categories)

        # Get streams per category
        for cat in categories:
            cat_id = cat.get("category_id", "")
            cat_name = cat.get("category_name", "")
            stream_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_live_streams&category_id={cat_id}"
            stream_resp = requests.get(stream_url, timeout=30)
            stream_resp.raise_for_status()
            cat_streams = stream_resp.json()

            for s in cat_streams:
                streams.append({
                    "name": s.get("name", "Unknown"),
                    "url": f"{base_url}/{username}/{password}/{s.get('stream_id', '')}",
                    "group": cat_name,
                    "tvg_id": s.get("epg_channel_id", ""),
                    "tvg_name": s.get("name", ""),
                    "logo": s.get("stream_icon", ""),
                    "duration": -1,
                    "extra_attributes": {},
                })
                stats["parsed"] += 1

    except Exception as e:
        logger.error(f"Xtream API error: {e}")
        stats["errors"] += 1

    return streams, stats


def _upsert_source_stream(db: Session, source_id: str, raw: Dict[str, Any]) -> SourceStream | None:
    """Create or update a SourceStream from parsed data."""
    if not raw.get("url"):
        return None

    existing = (
        db.query(SourceStream)
        .filter(SourceStream.source_id == source_id, SourceStream.url == raw["url"])
        .first()
    )

    now = datetime.now(timezone.utc)

    if existing:
        existing.name = raw.get("name", existing.name)
        existing.group = raw.get("group", existing.group)
        existing.tvg_id = raw.get("tvg_id", existing.tvg_id)
        existing.tvg_name = raw.get("tvg_name", existing.tvg_name)
        existing.logo = raw.get("logo", existing.logo)
        existing.duration = raw.get("duration", existing.duration)
        existing.extra_attributes = raw.get("extra_attributes", existing.extra_attributes)
        existing.deleted_at = None  # Un-soft-delete if it was previously removed
        existing.updated_at = now
        return existing

    stream = SourceStream(
        source_id=source_id,
        name=raw.get("name", "Unknown"),
        url=raw["url"],
        group=raw.get("group", ""),
        tvg_id=raw.get("tvg_id", ""),
        tvg_name=raw.get("tvg_name", ""),
        logo=raw.get("logo", ""),
        duration=raw.get("duration", -1),
        extra_attributes=raw.get("extra_attributes", {}),
    )
    db.add(stream)
    return stream


# B5 fix: channel index built once per ingest batch, not per stream
_channel_index_cache: dict | None = None


def _build_channel_index(db: Session) -> dict:
    """Build a lookup index of all canonical channels for fast matching."""
    global _channel_index_cache
    channels = db.query(CanonicalChannel).all()
    index = {
        "by_tvg_id": {},
        "by_norm_name": {},
    }
    for ch in channels:
        if ch.tvg_id:
            index["by_tvg_id"][ch.tvg_id] = ch
        norm = _normalize_name(ch.name_original or ch.name or "")
        if norm:
            index["by_norm_name"][norm] = ch
    index["all"] = channels  # for fallback
    _channel_index_cache = index
    return index


def _get_channel_index(db: Session) -> dict:
    """Get or build the channel index cache."""
    global _channel_index_cache
    if _channel_index_cache is None:
        return _build_channel_index(db)
    return _channel_index_cache


def _link_to_canonical(db: Session, stream: SourceStream) -> CanonicalChannel:
    """
    Tiered canonical channel matching:
    1. tvg_id exact match (indexed O(1))
    2. Exact normalized name match (indexed O(1))
    3. Fuzzy match (falls back to full scan — rare)
    4. Create new
    """
    idx = _get_channel_index(db)

    # 1. tvg_id match — O(1) dict lookup
    if stream.tvg_id and stream.tvg_id in idx["by_tvg_id"]:
        match = idx["by_tvg_id"][stream.tvg_id]
        stream.canonical_channel_id = match.id
        return match

    # 2. Exact normalized name match — O(1) dict lookup
    norm_name = _normalize_name(stream.name)
    if norm_name and norm_name in idx["by_norm_name"]:
        match = idx["by_norm_name"][norm_name]
        stream.canonical_channel_id = match.id
        return match

    # 3. Simple fallback: try case-insensitive exact match on original name
    all_channels = idx["all"]
    for ch in all_channels:
        if stream.name.lower() == (ch.name_original or ch.name or "").lower():
            stream.canonical_channel_id = ch.id
            idx["by_norm_name"][norm_name] = ch
            if ch.tvg_id:
                idx["by_tvg_id"][ch.tvg_id] = ch
            return ch

    # 4. Create new CanonicalChannel
    channel = CanonicalChannel(
        name=stream.name,
        name_original=stream.name,
        group=stream.group,
        tvg_id=stream.tvg_id or None,
    )
    db.add(channel)
    db.flush()  # persist to DB so refresh works
    db.refresh(channel)

    # B5: add to index so next matching stream finds it O(1)
    if stream.tvg_id:
        idx["by_tvg_id"][stream.tvg_id] = channel
    if norm_name:
        idx["by_norm_name"][norm_name] = channel
    idx["all"].append(channel)

    stream.canonical_channel_id = channel.id
    return channel
