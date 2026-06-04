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
            write_log("INFO", "telifisan.scheduler", f"Ingest: [{i+1}/{len(sources)}] '{src.name}'...")
            from backend.services.ingest import ingest_source
            result = ingest_source(src.id, db)
            write_log("INFO", "telifisan.scheduler", f"Ingest: '{src.name}' done — {result.stats}")
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
        from backend.services.validation import validate_all_streams
        result = validate_all_streams(db)
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
        write_log("INFO", "telifisan.scheduler", f"Output: generating {len(profiles)} profile(s)...")
        for p in profiles:
            write_log("INFO", "telifisan.scheduler", f"Output: '{p.name}'...")
            generate_profile_output(p.id, db)
            write_log("INFO", "telifisan.scheduler", f"Output: '{p.name}' done — {p.channel_count} channels")
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
    task_log = TaskLog(task_name=task_name, status=TaskStatus.RUNNING, started_at=datetime.now(timezone.utc))
    db.add(task_log)
    db.commit()

    try:
        func()
        task_log.status = TaskStatus.SUCCESS
        task_log.completed_at = datetime.now(timezone.utc)
        task_log.message = f"Task {task_name} completed"
    except Exception as e:
        task_log.status = TaskStatus.FAILED
        task_log.completed_at = datetime.now(timezone.utc)
        task_log.message = str(e)
        task_log.error_details = str(e)

    if task_log.started_at:
        task_log.duration_ms = int((task_log.completed_at - task_log.started_at).total_seconds() * 1000)
    db.commit()
    return task_log
