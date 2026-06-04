"""
Telifisan — Task Scheduler.
Only runs ingest → validate → output on cron.
"""

import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from backend.config import get_config
from backend.database import get_session
from backend.models import TaskLog, TaskStatus
from backend.utils.logger import write_log

logger = logging.getLogger("telifisan.scheduler")

_scheduler: BackgroundScheduler | None = None
_task_locks: dict[str, threading.Lock] = {}
_lock_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

# ── Real-time progress tracking ──────────────────────────
_task_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()


def set_progress(task_name: str, current: int, total: int, message: str = ""):
    """Update progress for a running task. Thread-safe."""
    with _progress_lock:
        _task_progress[task_name] = {
            "current": current,
            "total": total,
            "percent": round(current / total * 100, 1) if total > 0 else 0,
            "message": message,
            "task_name": task_name,
        }


def get_progress(task_name: str | None = None) -> dict | list:
    """Get progress for a specific task or all running tasks."""
    with _progress_lock:
        if task_name:
            return _task_progress.get(task_name, {})
        return dict(_task_progress)


def clear_progress(task_name: str):
    """Remove progress entry for a completed task."""
    with _progress_lock:
        _task_progress.pop(task_name, None)


def _acquire_lock(name: str) -> bool:
    with _lock_lock:
        if name not in _task_locks:
            _task_locks[name] = threading.Lock()
        return _task_locks[name].acquire(blocking=False)


def _release_lock(name: str):
    with _lock_lock:
        if name in _task_locks:
            try:
                _task_locks[name].release()
            except RuntimeError:
                pass


def cancel_task(task_name: str) -> bool:
    """Signal a running task to stop. Returns True if task was running."""
    with _cancel_lock:
        if task_name in _cancel_events:
            _cancel_events[task_name].set()
            write_log("INFO", "telifisan.scheduler", f"Cancelling {task_name}...")
            return True
    return False


def _was_cancelled(task_name: str) -> bool:
    """Check if this task was asked to stop. Returns True and cleans up if so."""
    with _cancel_lock:
        if task_name in _cancel_events and _cancel_events[task_name].is_set():
            del _cancel_events[task_name]
            write_log("INFO", "telifisan.scheduler", f"{task_name}: cancelled by user")
            return True
    return False


def _register_cancel(task_name: str):
    """Register a cancellation event for a task before it starts."""
    with _cancel_lock:
        _cancel_events[task_name] = threading.Event()


def _cleanup_cancel(task_name: str):
    """Remove cancellation event after task completes."""
    with _cancel_lock:
        _cancel_events.pop(task_name, None)


def _run_ingest_sources():
    """Ingest all enabled sources."""
    if not _acquire_lock("ingest_sources"):
        write_log("INFO", "telifisan.scheduler", "Ingest: skipped — already running")
        return

    db = get_session()
    try:
        from backend.models import Source
        sources = db.query(Source).filter(Source.enabled.is_(True), Source.deleted_at.is_(None)).all()
        write_log("INFO", "telifisan.scheduler", f"Ingest: starting, {len(sources)} source(s)")
        for i, src in enumerate(sources):
            if _was_cancelled("ingest_sources"):
                write_log("INFO", "telifisan.scheduler", f"Ingest: cancelled after {i} source(s)")
                return
            set_progress("ingest_sources", i + 1, len(sources), f"[{i+1}/{len(sources)}] '{src.name}'...")
            from backend.services.ingest import ingest_source
            result = ingest_source(src.id, db)
            write_log("INFO", "telifisan.scheduler", f"Ingest: '{src.name}' done — {result.stats}")
        clear_progress("ingest_sources")
        write_log("INFO", "telifisan.scheduler", f"Ingest: complete — {len(sources)} source(s)")
    except Exception as e:
        write_log("ERROR", "telifisan.scheduler", f"Ingest: failed — {e}")
        logger.exception(f"Ingest failed: {e}")
    finally:
        db.close()
        _release_lock("ingest_sources")


def _run_validate_streams():
    """Validate all streams."""
    if not _acquire_lock("validate_streams"):
        write_log("INFO", "telifisan.scheduler", "Validate: skipped — already running")
        return

    db = get_session()
    try:
        write_log("INFO", "telifisan.scheduler", "Validate: starting...")
        set_progress("validate_streams", 0, 1, "Starting...")
        from backend.services.validation import validate_all_streams
        if _was_cancelled("validate_streams"):
            clear_progress("validate_streams")
            write_log("INFO", "telifisan.scheduler", "Validate: cancelled")
            return
        result = validate_all_streams(db)
        clear_progress("validate_streams")
        if result:
            write_log("INFO", "telifisan.scheduler", f"Validate: done — {result.message}")
    except Exception as e:
        write_log("ERROR", "telifisan.scheduler", f"Validate: failed — {e}")
        logger.exception(f"Validate failed: {e}")
    finally:
        db.close()
        _release_lock("validate_streams")


def _run_generate_outputs():
    """Generate output for all enabled profiles."""
    if not _acquire_lock("generate_outputs"):
        write_log("INFO", "telifisan.scheduler", "Output: skipped — already running")
        return

    db = get_session()
    try:
        from backend.models import OutputProfile
        from backend.services.output import generate_profile_output
        profiles = db.query(OutputProfile).filter(OutputProfile.enabled.is_(True), OutputProfile.deleted_at.is_(None)).all()
        set_progress("generate_outputs", 0, len(profiles), "Starting...")
        write_log("INFO", "telifisan.scheduler", f"Output: generating {len(profiles)} profile(s)...")
        for i, p in enumerate(profiles):
            if _was_cancelled("generate_outputs"):
                clear_progress("generate_outputs")
                return
            set_progress("generate_outputs", i + 1, len(profiles), f"[{i+1}/{len(profiles)}] {p.name}")
            write_log("INFO", "telifisan.scheduler", f"Output: '{p.name}'...")
            generate_profile_output(p.id, db)
            write_log("INFO", "telifisan.scheduler", f"Output: '{p.name}' done — {p.channel_count} channels")
        clear_progress("generate_outputs")
        write_log("INFO", "telifisan.scheduler", f"Output: complete — {len(profiles)} profile(s)")
    except Exception as e:
        write_log("ERROR", "telifisan.scheduler", f"Output: failed — {e}")
        logger.exception(f"Output failed: {e}")
    finally:
        db.close()
        _release_lock("generate_outputs")


TASK_FUNCTIONS = {
    "ingest_sources": _run_ingest_sources,
    "validate_streams": _run_validate_streams,
    "generate_outputs": _run_generate_outputs,
}


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_ingest_sources, "interval", hours=6, id="ingest_sources")
    _scheduler.add_job(_run_validate_streams, "interval", hours=2, id="validate_streams")
    _scheduler.add_job(_run_generate_outputs, "interval", hours=1, id="generate_outputs")
    _scheduler.start()
    logger.info("Scheduler started (ingest=6h, validate=2h, output=1h)")


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        _scheduler = None


def run_task_now(task_name: str, db: Session) -> TaskLog | None:
    if task_name not in TASK_FUNCTIONS:
        raise ValueError(f"Unknown task: {task_name}")

    func = TASK_FUNCTIONS[task_name]
    _register_cancel(task_name)

    task_log = TaskLog(task_name=task_name, status=TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))
    db.add(task_log)
    db.commit()

    try:
        func()
        if _was_cancelled(task_name):
            task_log.status = TaskStatus.FAILED
            task_log.message = "Cancelled by user"
        else:
            task_log.status = TaskStatus.SUCCESS
            task_log.completed_at = datetime.now(timezone.utc)
            task_log.message = f"Task {task_name} completed"
    except Exception as e:
        task_log.status = TaskStatus.FAILED
        task_log.completed_at = datetime.now(timezone.utc)
        task_log.message = str(e)
        task_log.error_details = str(e)
    finally:
        _cleanup_cancel(task_name)

    if task_log.started_at and task_log.completed_at:
        task_log.duration_ms = int((task_log.completed_at - task_log.started_at).total_seconds() * 1000)
    db.commit()
    return task_log
