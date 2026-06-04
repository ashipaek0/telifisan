#!/usr/bin/env python3
"""
Telifisan v2.0 — CLI management tool (Phase 2).

Usage:
  telifisan sources list
  telifisan sources ingest <id>
  telifisan channels list [--status alive] [--search bbc]
  telifisan channels revalidate <id>
  telifisan tasks run <name>
  telifisan tasks list
  telifisan config get [key]
  telifisan config set <key> <value>
  telifisan backup
  telifisan rotate-key
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.config import load_config, get_config, generate_api_key
from backend.database import init_db, get_session
from backend.models import (
    Source, SourceStream, CanonicalChannel, Rule,
    OutputProfile, EPGSource, TaskLog, SystemConfig,
    TaskStatus,
)


def _get_api_key() -> str:
    session = get_session()
    try:
        row = session.query(SystemConfig).filter_by(key="api_key").first()
        return row.value if row else ""
    finally:
        session.close()


def cmd_sources_list(args):
    session = get_session()
    try:
        sources = session.query(Source).filter(Source.deleted_at.is_(None)).all()
        for s in sources:
            status = s.last_ingest_status.value if s.last_ingest_status else "N/A"
            print(f"  {s.id[:8]}  {s.name:<30} type={s.type.value:<15} streams={s.stream_count:<6} status={status}")
        print(f"\n{session.query(Source).filter(Source.deleted_at.is_(None)).count()} sources total")
    finally:
        session.close()


def cmd_sources_ingest(args):
    session = get_session()
    try:
        source = session.query(Source).filter_by(id=args.id).first()
        if not source:
            print(f"Source {args.id} not found")
            return
        print(f"Ingesting {source.name}...")
        from backend.services.ingest import ingest_source
        task_log = ingest_source(args.id, session)
        print(f"  Status: {task_log.status.value}")
        print(f"  Message: {task_log.message}")
        if task_log.stats:
            for k, v in task_log.stats.items():
                print(f"  {k}: {v}")
    finally:
        session.close()


def cmd_channels_list(args):
    session = get_session()
    try:
        query = session.query(CanonicalChannel)
        if args.status:
            from backend.models import ValidationStatus
            query = query.filter(CanonicalChannel.validation_status == ValidationStatus(args.status.upper()))
        if args.search:
            query = query.filter(CanonicalChannel.name.ilike(f"%{args.search}%"))
        channels = query.limit(100).all()
        for ch in channels:
            status = ch.validation_status.value if ch.validation_status else "UNKNOWN"
            print(f"  {ch.id[:8]}  {ch.name or 'N/A':<40} status={status:<10} uptime={(ch.uptime_percent or 0):.1f}%")
        print("\nShowing up to 100 channels")
    finally:
        session.close()


def cmd_channels_revalidate(args):
    session = get_session()
    try:
        ch = session.query(CanonicalChannel).filter_by(id=args.id).first()
        if not ch:
            print(f"Channel {args.id} not found")
            return
        print(f"Revalidating {ch.name}...")
        from backend.services.validation import check_stream
        for stream in ch.source_streams:
            if stream.deleted_at is None:
                check_stream(stream, session)
        session.refresh(ch)
        print(f"  Status: {ch.validation_status.value if ch.validation_status else 'N/A'}")
    finally:
        session.close()


def cmd_tasks_list(args):
    session = get_session()
    try:
        tasks = session.query(TaskLog.task_name).distinct().all()
        for (name,) in tasks:
            latest = session.query(TaskLog).filter(TaskLog.task_name == name).order_by(TaskLog.created_at.desc()).first()
            if latest:
                print(f"  {name:<30} status={latest.status.value if latest.status else 'N/A':<10} message={latest.message or 'N/A'}")
    finally:
        session.close()


def cmd_tasks_run(args):
    session = get_session()
    try:
        from backend.services.scheduler import run_task_now
        print(f"Running task {args.name}...")
        task_log = run_task_now(args.name, session)
        if task_log:
            print(f"  Status: {task_log.status.value}")
            print(f"  Message: {task_log.message}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()


def cmd_config_get(args):
    session = get_session()
    try:
        if args.key:
            row = session.query(SystemConfig).filter_by(key=args.key).first()
            if row:
                print(f"  {args.key} = {row.value}")
            else:
                print(f"  Key '{args.key}' not found")
        else:
            configs = session.query(SystemConfig).all()
            for c in configs:
                val = c.value
                if c.key == "api_key" and val and len(str(val)) > 12:
                    val = f"{str(val)[:8]}...{str(val)[-4:]}"
                print(f"  {c.key} = {val}")
    finally:
        session.close()


def cmd_config_set(args):
    session = get_session()
    try:
        row = session.query(SystemConfig).filter_by(key=args.key).first()
        if row:
            row.value = args.value
        else:
            session.add(SystemConfig(key=args.key, value=args.value))
        session.commit()
        print(f"  {args.key} = {args.value}")
    finally:
        session.close()


def cmd_backup(args):
    from backend.config import get_config as _get_config
    config = _get_config()
    data_dir = config["app"]["data_dir"]
    db_path = os.path.join(data_dir, "telifisan.db")
    backup_dir = os.path.join(data_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"telifisan_{timestamp}.db")

    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Backup saved to {backup_path}")


def cmd_rotate_key(args):
    session = get_session()
    try:
        row = session.query(SystemConfig).filter_by(key="api_key").first()
        new_key = generate_api_key()
        if row:
            row.value = new_key
        else:
            session.add(SystemConfig(key="api_key", value=new_key))
        session.commit()
        print(f"New API key: {new_key}")
        print("Store this key immediately!")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Telifisan CLI")
    sub = parser.add_subparsers(dest="command")

    # Sources
    src = sub.add_parser("sources", help="Manage sources")
    src_sub = src.add_subparsers(dest="subcommand")
    src_sub.add_parser("list", help="List sources").set_defaults(func=cmd_sources_list)
    ingest_p = src_sub.add_parser("ingest", help="Ingest a source")
    ingest_p.add_argument("id", help="Source ID")

    # Channels
    ch = sub.add_parser("channels", help="Manage channels")
    ch_sub = ch.add_subparsers(dest="subcommand")
    ch_list = ch_sub.add_parser("list", help="List channels")
    ch_list.add_argument("--status", help="Filter by status")
    ch_list.add_argument("--search", help="Search by name")
    ch_rev = ch_sub.add_parser("revalidate", help="Revalidate a channel")
    ch_rev.add_argument("id", help="Channel ID")

    # Tasks
    tsk = sub.add_parser("tasks", help="Manage tasks")
    tsk_sub = tsk.add_subparsers(dest="subcommand")
    tsk_sub.add_parser("list", help="List tasks").set_defaults(func=cmd_tasks_list)
    tsk_run = tsk_sub.add_parser("run", help="Run a task")
    tsk_run.add_argument("name", help="Task name")

    # Config
    cfg = sub.add_parser("config", help="Manage config")
    cfg_sub = cfg.add_subparsers(dest="subcommand")
    cfg_get = cfg_sub.add_parser("get", help="Get config")
    cfg_get.add_argument("key", nargs="?", help="Config key")
    cfg_set = cfg_sub.add_parser("set", help="Set config")
    cfg_set.add_argument("key", help="Config key")
    cfg_set.add_argument("value", help="Config value")

    # Backup
    sub.add_parser("backup", help="Create backup").set_defaults(func=cmd_backup)
    sub.add_parser("rotate-key", help="Rotate API key").set_defaults(func=cmd_rotate_key)

    args = parser.parse_args()

    # Init DB and config
    load_config()
    init_db()

    # Route to handler
    if args.command == "sources":
        if args.subcommand == "list":
            cmd_sources_list(args)
        elif args.subcommand == "ingest":
            cmd_sources_ingest(args)
        else:
            parser.print_help()
    elif args.command == "channels":
        if args.subcommand == "list":
            cmd_channels_list(args)
        elif args.subcommand == "revalidate":
            cmd_channels_revalidate(args)
        else:
            parser.print_help()
    elif args.command == "tasks":
        if args.subcommand == "list":
            cmd_tasks_list(args)
        elif args.subcommand == "run":
            cmd_tasks_run(args)
        else:
            parser.print_help()
    elif args.command == "config":
        if args.subcommand == "get":
            cmd_config_get(args)
        elif args.subcommand == "set":
            cmd_config_set(args)
        else:
            parser.print_help()
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "rotate-key":
        cmd_rotate_key(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
