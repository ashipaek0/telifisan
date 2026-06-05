"""
Telifisan v2.0 — System configuration API.

Endpoints: GET/PUT config, backup trigger, API key rotation.
"""

import os
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.config import generate_api_key
from backend.database import get_db
from backend.models import SystemConfig

router = APIRouter(tags=["config"])


@router.get("/config")
def get_system_config(db: Session = Depends(get_db)):
    """Get all system configuration as key-value pairs."""
    configs = db.query(SystemConfig).all()
    data = {c.key: c.value for c in configs}
    # Redact sensitive values
    if "api_key" in data and data["api_key"]:
        key = data["api_key"]
        data["api_key"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
    return {
        "success": True,
        "data": data,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/config")
def update_system_config(body: dict, db: Session = Depends(get_db)):
    """Update system configuration keys. Only whitelisted keys can be updated."""
    allowed_keys = {
        "validation_concurrency", "timeout_ms", "hard_dead_threshold",
        "uptime_window_size", "allow_script_rules",
    }

    for key, value in body.items():
        if key not in allowed_keys:
            continue
        existing = db.query(SystemConfig).filter_by(key=key).first()
        if existing:
            existing.value = value
        else:
            db.add(SystemConfig(key=key, value=value))

    db.commit()
    return {
        "success": True,
        "data": {"updated": list(body.keys())},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Phase 2: Export / Import ──────────────────────────────────

@router.get("/config/export")
def export_config(db: Session = Depends(get_db)):
    """
    Export all configurable entities as a single JSON blob.

    Includes: sources, rules, profiles, EPG sources, overrides, system config.
    Excludes: actual stream data, validation records, task logs, EPG programmes.
    """
    from backend.models import (
        Source, Rule, OutputProfile, EPGSource, EnrichmentOverride,
    )

    now = datetime.now(timezone.utc)

    # Sources (excluding sensitive auth)
    sources = []
    for s in db.query(Source).filter(Source.deleted_at.is_(None)).all():
        sources.append({
            "name": s.name,
            "type": s.type.value if s.type else "M3U_URL",
            "url": s.url,
            "file_path": s.file_path,
            "auth_username": s.auth_username,
            "auth_password": s.auth_password,
            "auth_headers": s.auth_headers,
            "enabled": s.enabled,
            "priority": s.priority,
            "ingest_schedule": s.ingest_schedule,
        })

    # Rules
    rules = []
    for r in db.query(Rule).filter(Rule.deleted_at.is_(None)).all():
        rules.append({
            "name": r.name,
            "rule_type": r.rule_type.value if r.rule_type else "OUTPUT_FILTER",
            "applies_at": r.applies_at.value if r.applies_at else "OUTPUT",
            "enabled": r.enabled,
            "priority": r.priority,
            "complexity": r.complexity.value if r.complexity else "SIMPLE",
            "simple_action": r.simple_action.value if r.simple_action else None,
            "simple_field": r.simple_field.value if r.simple_field else None,
            "simple_operator": r.simple_operator.value if r.simple_operator else None,
            "simple_value": r.simple_value,
            "condition_tree": r.condition_tree,
            "action_json": r.action_json,
            "script_code": r.script_code,
        })

    # Profiles
    profiles = []
    for p in db.query(OutputProfile).filter(OutputProfile.deleted_at.is_(None)).all():
        profiles.append({
            "name": p.name,
            "enabled": p.enabled,
            "mode": p.mode.value if p.mode else "DIRECT",
            "included_sources": p.included_sources,
            "output_filter_rule_ids": p.output_filter_rule_ids,
            "sort_by": p.sort_by.value if p.sort_by else "NAME",
            "group_by": p.group_by.value if p.group_by else "NONE",
            "include_dead_channels": p.include_dead_channels,
            "min_uptime_percent": p.min_uptime_percent,
            "enable_xtream_codes_api": p.enable_xtream_codes_api,
            "xtream_username": p.xtream_username,
            "xtream_password": p.xtream_password,
            "generate_schedule": p.generate_schedule,
        })

    # EPG sources
    epg_sources = []
    for e in db.query(EPGSource).filter(EPGSource.deleted_at.is_(None)).all():
        epg_sources.append({
            "name": e.name,
            "url": e.url,
            "local_file_path": e.local_file_path,
            "enabled": e.enabled,
            "timezone": e.timezone,
            "priority": e.priority,
            "refresh_schedule": e.refresh_schedule,
        })

    # Overrides
    overrides = []
    for o in db.query(EnrichmentOverride).all():
        overrides.append({
            "canonical_channel_name": None,  # resolved below
            "field": o.field.value if o.field else "NAME",
            "locked": o.locked,
            "value": o.value,
        })

    # System config (exclude api_key for security)
    sys_config = {}
    for c in db.query(SystemConfig).all():
        if c.key == "api_key":
            continue
        sys_config[c.key] = c.value

    return {
        "success": True,
        "data": {
            "version": "2.0",
            "exported_at": now.isoformat(),
            "sources": sources,
            "rules": rules,
            "profiles": profiles,
            "epg_sources": epg_sources,
            "overrides": overrides,
            "system_config": sys_config,
        },
        "error": None,
        "timestamp": now.isoformat(),
    }


@router.post("/config/import")
def import_config(body: dict, db: Session = Depends(get_db)):
    """
    Import configuration from a JSON export.

    Uses upsert semantics: entities with matching names are updated,
    new entities are created. Does NOT delete existing entities.
    Returns a summary of what was imported.
    """
    from backend.models import (
        Source, SourceType, Rule, RuleType, RuleAppliesAt, RuleComplexity,
        SimpleAction, SimpleField, SimpleOperator,
        OutputProfile, OutputMode, SortBy, GroupBy,
        EPGSource,
    )

    data = body.get("data", body)
    stats = {"sources": 0, "rules": 0, "profiles": 0, "epg_sources": 0, "overrides": 0, "config_keys": 0}

    # Import sources
    for src in data.get("sources", []):
        try:
            src_type = SourceType(src["type"])
        except (KeyError, ValueError):
            src_type = SourceType.M3U_URL

        existing = db.query(Source).filter(
            Source.name == src["name"], Source.deleted_at.is_(None)
        ).first()

        if existing:
            existing.url = src.get("url", existing.url)
            existing.file_path = src.get("file_path", existing.file_path)
            existing.auth_username = src.get("auth_username", existing.auth_username)
            if src.get("auth_password"):
                existing.auth_password = src["auth_password"]
            existing.auth_headers = src.get("auth_headers", existing.auth_headers)
            existing.enabled = src.get("enabled", existing.enabled)
            existing.priority = src.get("priority", existing.priority)
            existing.ingest_schedule = src.get("ingest_schedule", existing.ingest_schedule)
        else:
            source = Source(
                name=src["name"],
                type=src_type,
                url=src.get("url"),
                file_path=src.get("file_path"),
                auth_username=src.get("auth_username"),
                auth_password=src.get("auth_password"),
                auth_headers=src.get("auth_headers"),
                enabled=src.get("enabled", True),
                priority=src.get("priority", 100),
                ingest_schedule=src.get("ingest_schedule"),
            )
            db.add(source)
        stats["sources"] += 1

    # Import rules
    for r in data.get("rules", []):
        existing = db.query(Rule).filter(
            Rule.name == r["name"], Rule.deleted_at.is_(None)
        ).first()
        try:
            rule_type = RuleType(r.get("rule_type", "OUTPUT_FILTER"))
            applies_at = RuleAppliesAt(r.get("applies_at", "OUTPUT"))
        except ValueError:
            continue

        if existing:
            existing.rule_type = rule_type
            existing.applies_at = applies_at
            existing.enabled = r.get("enabled", existing.enabled)
            existing.priority = r.get("priority", existing.priority)
            if r.get("simple_action"):
                existing.simple_action = SimpleAction(r["simple_action"])
            if r.get("simple_field"):
                existing.simple_field = SimpleField(r["simple_field"])
            if r.get("simple_operator"):
                existing.simple_operator = SimpleOperator(r["simple_operator"])
            existing.simple_value = r.get("simple_value", existing.simple_value)
            existing.condition_tree = r.get("condition_tree", existing.condition_tree)
        else:
            rule = Rule(
                name=r["name"],
                rule_type=rule_type,
                applies_at=applies_at,
                enabled=r.get("enabled", True),
                priority=r.get("priority", 100),
                complexity=RuleComplexity.SIMPLE,
            )
            if r.get("simple_action"):
                rule.simple_action = SimpleAction(r["simple_action"])
            if r.get("simple_field"):
                rule.simple_field = SimpleField(r["simple_field"])
            if r.get("simple_operator"):
                rule.simple_operator = SimpleOperator(r["simple_operator"])
            rule.simple_value = r.get("simple_value")
            rule.condition_tree = r.get("condition_tree")
            db.add(rule)
        stats["rules"] += 1

    # Import profiles
    for p in data.get("profiles", []):
        existing = db.query(OutputProfile).filter(
            OutputProfile.name == p["name"], OutputProfile.deleted_at.is_(None)
        ).first()
        try:
            mode = OutputMode(p.get("mode", "DIRECT"))
        except ValueError:
            mode = OutputMode.DIRECT

        if existing:
            existing.mode = mode
            existing.enabled = p.get("enabled", existing.enabled)
            existing.included_sources = p.get("included_sources", existing.included_sources)
            existing.output_filter_rule_ids = p.get("output_filter_rule_ids", existing.output_filter_rule_ids)
            if p.get("sort_by"):
                try:
                    existing.sort_by = SortBy(p["sort_by"])
                except ValueError:
                    pass
            if p.get("group_by"):
                try:
                    existing.group_by = GroupBy(p["group_by"])
                except ValueError:
                    pass
            existing.include_dead_channels = p.get("include_dead_channels", existing.include_dead_channels)
            existing.min_uptime_percent = p.get("min_uptime_percent", existing.min_uptime_percent)
            existing.enable_xtream_codes_api = p.get("enable_xtream_codes_api", existing.enable_xtream_codes_api)
            existing.xtream_username = p.get("xtream_username", existing.xtream_username)
            if p.get("xtream_password"):
                existing.xtream_password = p["xtream_password"]
            existing.generate_schedule = p.get("generate_schedule", existing.generate_schedule)
        else:
            profile = OutputProfile(
                name=p["name"],
                mode=mode,
                enabled=p.get("enabled", True),
                included_sources=p.get("included_sources"),
                output_filter_rule_ids=p.get("output_filter_rule_ids"),
                include_dead_channels=p.get("include_dead_channels", False),
                min_uptime_percent=p.get("min_uptime_percent", 0),
                enable_xtream_codes_api=p.get("enable_xtream_codes_api", False),
                xtream_username=p.get("xtream_username"),
                xtream_password=p.get("xtream_password"),
                generate_schedule=p.get("generate_schedule"),
                m3u_url_path=f"/output/{p['name'].lower().replace(' ', '-')}.m3u",
                xmltv_url_path=f"/output/{p['name'].lower().replace(' ', '-')}.xmltv",
            )
            if p.get("sort_by"):
                try:
                    profile.sort_by = SortBy(p["sort_by"])
                except ValueError:
                    pass
            if p.get("group_by"):
                try:
                    profile.group_by = GroupBy(p["group_by"])
                except ValueError:
                    pass
            db.add(profile)
        stats["profiles"] += 1

    # Import EPG sources
    for e in data.get("epg_sources", []):
        existing = db.query(EPGSource).filter(
            EPGSource.name == e["name"], EPGSource.deleted_at.is_(None)
        ).first()
        if existing:
            existing.url = e.get("url", existing.url)
            existing.enabled = e.get("enabled", existing.enabled)
            existing.timezone = e.get("timezone", existing.timezone)
            existing.priority = e.get("priority", existing.priority)
        else:
            epg_source = EPGSource(
                name=e["name"],
                url=e.get("url"),
                local_file_path=e.get("local_file_path"),
                enabled=e.get("enabled", True),
                timezone=e.get("timezone", "UTC"),
                priority=e.get("priority", 100),
            )
            db.add(epg_source)
        stats["epg_sources"] += 1

    # Import system config
    for key, value in data.get("system_config", {}).items():
        existing = db.query(SystemConfig).filter_by(key=key).first()
        if existing:
            existing.value = value
        else:
            db.add(SystemConfig(key=key, value=value))
        stats["config_keys"] += 1

    db.commit()

    return {
        "success": True,
        "data": {"imported": stats},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/config/backup")
def trigger_backup(db: Session = Depends(get_db)):
    """Trigger a database backup. Copies the SQLite file to /data/backups/."""
    from backend.config import get_config
    config = get_config()
    data_dir = config["app"]["data_dir"]
    db_path = os.path.join(data_dir, "telifisan.db")
    backup_dir = os.path.join(data_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"telifisan_{timestamp}.db")

    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found")

    try:
        shutil.copy2(db_path, backup_path)
        return {
            "success": True,
            "data": {"backup_path": backup_path},
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": {"code": "BACKUP_FAILED", "message": str(e), "details": {}},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/config/key/rotate")
def rotate_api_key(db: Session = Depends(get_db)):
    """Generate a new API key. Old key is immediately invalidated."""
    config_row = db.query(SystemConfig).filter_by(key="api_key").first()
    new_key = generate_api_key()
    now = datetime.now(timezone.utc)

    if config_row:
        config_row.value = new_key
    else:
        db.add(SystemConfig(key="api_key", value=new_key))

    # Update rotation timestamp
    rotated = db.query(SystemConfig).filter_by(key="api_key_rotated_at").first()
    if rotated:
        rotated.value = now.isoformat()
    else:
        db.add(SystemConfig(key="api_key_rotated_at", value=now.isoformat()))

    db.commit()

    return {
        "success": True,
        "data": {
            "api_key": new_key,
            "rotated_at": now.isoformat(),
            "note": "Store this key immediately. It will not be shown again.",
        },
        "error": None,
        "timestamp": now.isoformat(),
    }


@router.get("/config/scheduler")
def get_scheduler_config(db: Session = Depends(get_db)):
    """Return the current scheduler intervals per task."""
    from backend.services.scheduler import get_schedule_config
    intervals = get_schedule_config(db)
    return {
        "success": True,
        "data": intervals,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/config/scheduler")
def update_scheduler_config(body: dict, db: Session = Depends(get_db)):
    """Update a scheduler interval. Body: {"task_name": "ingest_sources", "hours": 4}"""
    task_name = body.get("task_name")
    hours = body.get("hours")
    if not task_name or not hours:
        raise HTTPException(status_code=400, detail="task_name and hours required")
    from backend.services.scheduler import set_schedule_interval
    ok = set_schedule_interval(task_name, int(hours), db)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid task or hours. Valid: ingest_sources, validate_streams, generate_outputs")
    return {"success": True, "data": {"task_name": task_name, "hours": hours}, "error": None, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/config/log-level")
def set_log_level_endpoint(body: dict, db: Session = Depends(get_db)):
    """Toggle debug logging at runtime. Body: {"level": "DEBUG"|"INFO"|"WARNING"|"ERROR"}"""
    level = body.get("level", "INFO").upper()
    valid = {"DEBUG", "INFO", "WARNING", "ERROR"}
    if level not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid level. Use: {', '.join(sorted(valid))}")

    from backend.utils.logger import set_log_level
    set_log_level(level)

    return {
        "success": True,
        "data": {"log_level": level},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/config/key")
def get_public_api_key(db: Session = Depends(get_db)):
    """Return the system API key (public endpoint, no auth required)."""
    from backend.models import SystemConfig
    row = db.query(SystemConfig).filter_by(key="api_key").first()
    return {
        "success": True,
        "data": {"api_key": row.value if row else None},
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
