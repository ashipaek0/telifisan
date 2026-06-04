"""
Telifisan v2.0 — Stream Validation Engine.

Checks if streams are playable using HTTP HEAD, HLS manifest validation,
ffprobe, and streamlink. Updates CanonicalChannel validation status.
"""

import logging
import random
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from backend.config import get_config
from backend.models import (
    SourceStream, CanonicalChannel, ValidationRecord,
    ValidationStatus, CheckerTool, TaskLog, TaskStatus,
)
from backend.utils.logger import write_log

logger = logging.getLogger("telifisan.validation")

# ── Per-domain rate limiting ──────────────────────────────────
_domain_semaphores: dict[str, threading.BoundedSemaphore] = {}
_domain_sem_lock = threading.Lock()


def _get_domain(url: str) -> str:
    """Extract hostname from a URL for per-domain rate limiting."""
    try:
        return urlparse(url).hostname or "unknown"
    except Exception:
        return "unknown"


def _get_domain_semaphore(domain: str, max_per_domain: int) -> threading.BoundedSemaphore:
    """Get or create a semaphore for a domain."""
    with _domain_sem_lock:
        if domain not in _domain_semaphores:
            _domain_semaphores[domain] = threading.BoundedSemaphore(max_per_domain)
        return _domain_semaphores[domain]


def _try_broadcast_progress(checked: int, total: int, alive: int, dead: int, errors: int):
    """Log validation progress directly (thread-safe, no websocket dependency)."""
    if checked % 10 == 0 or checked == total:
        write_log("INFO", "telifisan.validation",
                  f"Validate: {checked}/{total} ({alive} alive, {dead} dead, {errors} err)")


def _validate_stream_by_id(stream_id: str) -> ValidationRecord | None:
    """Validate a single stream in its own DB session (thread-safe)."""
    from backend.database import get_session
    config = get_config()
    per_domain = config.get("validation", {}).get("per_domain_concurrency", 4)

    worker_db = get_session()
    try:
        stream = worker_db.query(SourceStream).filter_by(id=stream_id).first()
        if not stream:
            return None

        # Respect per-domain rate limits
        domain = _get_domain(stream.url)
        sem = _get_domain_semaphore(domain, per_domain)

        acquired = sem.acquire(timeout=60)
        if not acquired:
            logger.warning(f"Skipping {stream.url}: domain rate limit saturated for {domain}")
            return None  # Skip this stream, it'll be retried next cycle

        try:
            record = check_stream(stream, worker_db)
            if record:
                worker_db.expunge(record)
            return record
        finally:
            sem.release()
    finally:
        worker_db.close()


def validate_all_streams(db: Session) -> TaskLog:
    """Validate all non-deleted streams and update channel statuses."""
    task_log = TaskLog(
        task_name="validate_streams",
        status=TaskStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(task_log)
    db.commit()

    config = get_config()
    val_config = config.get("validation", {})
    concurrency = val_config.get("concurrency", 20)

    streams = (
        db.query(SourceStream)
        .filter(SourceStream.deleted_at.is_(None))
        .all()
    )

    checked = 0
    alive = 0
    dead = 0
    errors = 0

    # Each worker opens its own session — prevents thread-safety issues
    # Shuffle to spread requests across domains
    random.shuffle(streams)

    total_streams = len(streams)
    stagger_ms = val_config.get("inter_stream_delay_ms", 50) / 1000.0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for s in streams:
            futures[executor.submit(_validate_stream_by_id, s.id)] = s
            if stagger_ms > 0:
                time.sleep(stagger_ms)  # stagger submissions to avoid thundering herd

        for future in as_completed(futures):
            try:
                result = future.result()
                checked += 1
                if result and result.success:
                    alive += 1
                elif result:
                    dead += 1
                else:
                    errors += 1

                # Log progress periodically
                _try_broadcast_progress(checked, total_streams, alive, dead, errors)
            except Exception as e:
                logger.error(f"Validation worker error: {e}")
                errors += 1

    # Update all canonical channel statuses
    _update_channel_statuses(db)

    task_log.status = TaskStatus.SUCCESS
    task_log.message = f"Checked {checked} streams: {alive} alive, {dead} dead, {errors} errors"
    task_log.stats = {"checked": checked, "alive": alive, "dead": dead, "errors": errors}
    task_log.completed_at = datetime.now(timezone.utc)
    if task_log.started_at:
        task_log.duration_ms = int(
            (task_log.completed_at - task_log.started_at).total_seconds() * 1000
        )
    db.commit()

    return task_log


def check_stream(stream: SourceStream, db: Session) -> ValidationRecord | None:
    """Check a single stream and record the result."""
    config = get_config()
    timeout_ms = config.get("validation", {}).get("timeout_ms", 30000)
    timeout_sec = timeout_ms / 1000
    require_head = config.get("validation", {}).get("require_head_ok", False)

    start_time = time.time()
    url = stream.url

    try:
        # Step 1: HTTP HEAD check — fast pre-check
        reachable, head_ok = _http_head_check(url, timeout_sec)
        logger.debug(f"  HEAD: reachable={reachable}, ok={head_ok} — {stream.name}")

        # Only skip ffprobe if the server is completely unreachable (DNS/connection failure)
        if not reachable:
            write_log("INFO", "telifisan.validation", f"  SKIP: server unreachable — {stream.name}")
            record = _create_record(stream, False, CheckerTool.HTTP_HEAD,
                                    "Server unreachable (DNS/connection failed)",
                                    start_time=start_time)
            db.add(record)
            db.commit()
            return record

        # If require_head_ok is set and HEAD explicitly failed, mark dead
        if require_head and not head_ok:
            write_log("INFO", "telifisan.validation", f"  SKIP: HEAD rejected (require_head_ok) — {stream.name}")
            record = _create_record(stream, False, CheckerTool.HTTP_HEAD,
                                    "HTTP HEAD rejected and require_head_ok is set",
                                    start_time=start_time)
            db.add(record)
            db.commit()
            return record

        # Step 2: ffprobe (does a real GET-based connection)
        logger.debug(f"  ffprobe: checking — {stream.name}")
        ffprobe_result = _ffprobe_check(url, timeout_sec)
        if ffprobe_result.get("success"):
            res = ffprobe_result.get("resolution", "?")
            codec = ffprobe_result.get("codec", "?")
            write_log("INFO", "telifisan.validation", f"  ffprobe OK: {res}, {codec} — {stream.name}")
            record = _create_record(stream, True, CheckerTool.FFPROBE,
                                    metadata=ffprobe_result, start_time=start_time)
            db.add(record)
            db.commit()
            return record
        else:
            logger.debug(f"  ffprobe FAILED: {ffprobe_result.get('error', '?')[:60]} — {stream.name}")

        # Step 3: HLS manifest check for m3u8 URLs
        if url.endswith(".m3u8"):
            hls_ok = _hls_manifest_check(url, timeout_sec)
            logger.debug(f"  HLS: {'OK' if hls_ok else 'FAILED'} — {stream.name}")

        # Step 4: streamlink fallback
        logger.debug(f"  streamlink: trying — {stream.name}")
        sl_result = _streamlink_check(url, timeout_sec)
        if sl_result.get("success"):
            write_log("INFO", "telifisan.validation", f"  streamlink OK — {stream.name}")
            record = _create_record(stream, True, CheckerTool.STREAMLINK,
                                    metadata=sl_result, start_time=start_time)
            db.add(record)
            db.commit()
            return record
        else:
            logger.debug(f"  streamlink FAILED — {stream.name}")

        # All checks failed
        error_msg = "All checks failed"
        if not head_ok:
            error_msg = "HEAD denied + ffprobe/streamlink failed"
        write_log("INFO", "telifisan.validation", f"  DEAD: {error_msg} — {stream.name}")
        record = _create_record(stream, False, CheckerTool.FFPROBE, error_msg,
                                start_time=start_time)
        db.add(record)
        db.commit()
        return record

    except Exception as e:
        write_log("ERROR", "telifisan.validation", f"  ERROR: {e} — {stream.name}")
        record = _create_record(stream, False, CheckerTool.FFPROBE, str(e),
                                start_time=start_time)
        db.add(record)
        db.commit()
        return record


def _http_head_check(url: str, timeout: float) -> tuple[bool, bool]:
    """
    Check if a URL is reachable via HTTP HEAD.

    Returns (reachable, head_ok):
      - (True, True)  — HEAD returned 2xx/3xx, stream is likely alive
      - (True, False) — Server reachable but HEAD denied (4xx); still worth trying ffprobe
      - (False, False) — Connection error / timeout; server is truly unreachable
    """
    try:
        resp = requests.head(url, timeout=min(timeout, 10), allow_redirects=True,
                             headers={"User-Agent": "Telifisan/2.0"})
        if resp.status_code < 400:
            return (True, True)
        elif resp.status_code < 500:
            logger.debug(f"    HEAD got {resp.status_code} — server reachable, HEAD denied")
            return (True, False)  # 4xx: HEAD not allowed, but server is there
        else:
            logger.debug(f"    HEAD got {resp.status_code} — server error, still trying ffprobe")
            return (True, False)
    except requests.ConnectionError as e:
        logger.debug(f"    HEAD ConnectionError: {e}")
        return (False, False)
    except requests.Timeout:
        logger.debug(f"    HEAD timeout after {timeout}s")
        return (False, False)
    except requests.RequestException as e:
        logger.debug(f"    HEAD exception: {e} — still trying ffprobe")
        return (True, False)


def _hls_manifest_check(url: str, timeout: float) -> bool:
    """Validate HLS manifest has at least one segment."""
    try:
        resp = requests.get(url, timeout=min(timeout, 10))
        if resp.status_code != 200:
            return False
        content = resp.text
        # Check for EXTINF or EXT-X-STREAM-INF markers
        if "#EXTINF:" in content or "#EXT-X-STREAM-INF:" in content:
            return True
        return False
    except requests.RequestException:
        return False


def _ffprobe_check(url: str, timeout: float) -> dict:
    """Run ffprobe on a stream URL."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams",
            "-timeout", str(int(timeout * 1000000)),  # microseconds
            url,
        ]
        logger.debug(f"    ffprobe cmd: {' '.join(cmd[:6])} <url>")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )

        if result.returncode != 0:
            stderr = result.stderr[:200] if result.stderr else "no output"
            logger.debug(f"    ffprobe exit code {result.returncode}: {stderr}")
            return {"success": False, "error": stderr}

        import json
        data = json.loads(result.stdout)

        video_stream = None
        audio_streams = []
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
            elif s.get("codec_type") == "audio":
                audio_streams.append(s)

        fmt = data.get("format", {})

        return {
            "success": True,
            "codec": video_stream.get("codec_name", "") if video_stream else "",
            "resolution": f"{video_stream.get('width', '')}x{video_stream.get('height', '')}" if video_stream else "",
            "bitrate": int(int(fmt.get("bit_rate", 0)) / 1000) if fmt.get("bit_rate") else None,
            "audio_tracks": len(audio_streams),
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ffprobe timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def _streamlink_check(url: str, timeout: float) -> dict:
    """Try to resolve a stream URL via streamlink."""
    try:
        cmd = ["streamlink", "--stream-url", url, "best"]
        logger.debug(f"    streamlink cmd: streamlink <url> best")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.debug(f"    streamlink resolved: {result.stdout.strip()[:60]}")
            return {"success": True, "resolved_url": result.stdout.strip()}
        stderr = result.stderr[:200] if result.stderr else "no output"
        logger.debug(f"    streamlink failed: {stderr}")
        return {"success": False, "error": stderr}
    except subprocess.TimeoutExpired:
        logger.debug(f"    streamlink timeout")
        return {"success": False, "error": "streamlink timeout"}
    except Exception as e:
        logger.debug(f"    streamlink error: {e}")
        return {"success": False, "error": str(e)[:200]}


def _create_record(
    stream: SourceStream,
    success: bool,
    tool: CheckerTool,
    error: str = "",
    metadata: dict | None = None,
    start_time: float = 0,
) -> ValidationRecord:
    """Create a ValidationRecord."""
    duration_ms = int((time.time() - start_time) * 1000) if start_time else 0
    meta = metadata or {}

    return ValidationRecord(
        source_stream_id=stream.id,
        checked_at=datetime.now(timezone.utc),
        success=success,
        codec=meta.get("codec", ""),
        resolution=meta.get("resolution", ""),
        bitrate=meta.get("bitrate"),
        audio_tracks=meta.get("audio_tracks"),
        error_message=error if not success else None,
        checker_tool=tool,
        duration_ms=duration_ms,
    )


def _update_channel_statuses(db: Session):
    """Recalculate validation status and uptime for all canonical channels."""
    config = get_config()
    val_config = config.get("validation", {})
    hard_dead_threshold = val_config.get("hard_dead_threshold", 3)
    uptime_window = val_config.get("uptime_window_size", 10)

    channels = db.query(CanonicalChannel).all()

    # B22: intermediate commits every 100 channels to avoid losing all progress
    for idx, channel in enumerate(channels):
        # Get streams for this channel
        stream_ids = [
            s.id for s in channel.source_streams
            if s.deleted_at is None
        ]

        if not stream_ids:
            channel.validation_status = ValidationStatus.HARD_DEAD
            channel.uptime_percent = 0
            continue

        # Get recent validation records
        latest_records = {}
        for sid in stream_ids:
            records = (
                db.query(ValidationRecord)
                .filter(ValidationRecord.source_stream_id == sid)
                .order_by(ValidationRecord.checked_at.desc())
                .limit(uptime_window)
                .all()
            )
            latest_records[sid] = records

        # Calculate uptime
        all_records = []
        for records in latest_records.values():
            all_records.extend(records)

        if all_records:
            success_count = sum(1 for r in all_records if r.success)
            channel.uptime_percent = (success_count / len(all_records)) * 100
        else:
            channel.uptime_percent = 0

        # Determine status from the most recent check per stream
        most_recent = []
        for sid in stream_ids:
            latest = (
                db.query(ValidationRecord)
                .filter(ValidationRecord.source_stream_id == sid)
                .order_by(ValidationRecord.checked_at.desc())
                .first()
            )
            if latest:
                most_recent.append(latest)

        if not most_recent:
            channel.validation_status = ValidationStatus.UNKNOWN
        elif all(r.success for r in most_recent):
            channel.validation_status = ValidationStatus.ALIVE
        else:
            # Check consecutive failures for HARD_DEAD
            all_failed = all(not r.success for r in most_recent)
            if all_failed:
                # Count consecutive failures across all streams
                consecutive = 0
                for sid in stream_ids:
                    records = (
                        db.query(ValidationRecord)
                        .filter(ValidationRecord.source_stream_id == sid)
                        .order_by(ValidationRecord.checked_at.desc())
                        .limit(hard_dead_threshold)
                        .all()
                    )
                    if records and all(not r.success for r in records):
                        consecutive += 1

                if consecutive >= len(stream_ids):
                    channel.validation_status = ValidationStatus.HARD_DEAD
                else:
                    channel.validation_status = ValidationStatus.SOFT_DEAD
            else:
                channel.validation_status = ValidationStatus.SOFT_DEAD

        channel.last_validation = datetime.now(timezone.utc)

        # Auto-set preferred_source_id
        if not channel.preferred_source_id:
            _auto_set_preferred_source(db, channel)

        # B22: commit every 100 channels to avoid losing all progress on DB error
        if (idx + 1) % 100 == 0:
            db.commit()

    db.commit()


def _auto_set_preferred_source(db: Session, channel: CanonicalChannel):
    """Set the preferred SourceStream for a canonical channel."""
    best_stream = None
    best_priority = 999

    for stream in channel.source_streams:
        if stream.deleted_at is not None:
            continue
        if stream.source.priority < best_priority:
            best_stream = stream
            best_priority = stream.source.priority

    if best_stream:
        channel.preferred_source_id = best_stream.id