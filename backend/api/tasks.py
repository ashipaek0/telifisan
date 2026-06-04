"""
Telifisan — Task listing and manual trigger API.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import TaskLog

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db)):
    task_names = db.query(TaskLog.task_name).distinct().all()
    tasks = []
    for row in task_names:
        name = row[0] if hasattr(row, '__getitem__') else row
        latest = db.query(TaskLog).filter(TaskLog.task_name == name).order_by(desc(TaskLog.created_at)).first()
        if latest:
            tasks.append({
                "task_name": name, "status": latest.status.value if latest.status else None,
                "last_run": latest.started_at.isoformat() if latest.started_at else None,
                "last_duration_ms": latest.duration_ms, "last_message": latest.message,
            })
    return {"success": True, "data": tasks, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/tasks/{task_name}")
def get_task(task_name: str, db: Session = Depends(get_db)):
    latest = db.query(TaskLog).filter(TaskLog.task_name == task_name).order_by(desc(TaskLog.created_at)).first()
    if not latest:
        raise HTTPException(status_code=404, detail=f"Task '{task_name}' not found")
    return {
        "success": True,
        "data": {"task_name": task_name, "status": latest.status.value if latest.status else None, "last_run": latest.started_at.isoformat() if latest.started_at else None, "duration_ms": latest.duration_ms, "message": latest.message, "stats": latest.stats},
        "error": None, "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/tasks/{task_name}/logs")
def get_task_logs(task_name: str, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    per_page = min(per_page, 200)
    total = db.query(TaskLog).filter(TaskLog.task_name == task_name).count()
    logs = db.query(TaskLog).filter(TaskLog.task_name == task_name).order_by(desc(TaskLog.created_at)).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "success": True,
        "data": [{"id": log.id, "task_name": log.task_name, "status": log.status.value if log.status else None, "started_at": log.started_at.isoformat() if log.started_at else None, "completed_at": log.completed_at.isoformat() if log.completed_at else None, "duration_ms": log.duration_ms, "message": log.message, "stats": log.stats} for log in logs],
        "pagination": {"page": page, "per_page": per_page, "total": total, "pages": max(1, (total + per_page - 1) // per_page)},
        "error": None, "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/tasks/{task_name}/run")
def trigger_task(task_name: str, db: Session = Depends(get_db)):
    from backend.services.scheduler import run_task_now
    try:
        log_entry = run_task_now(task_name, db)
        return {
            "success": True,
            "data": {"task_name": task_name, "log_id": log_entry.id if log_entry else None, "status": log_entry.status.value if log_entry and log_entry.status else "PENDING"},
            "error": None, "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
