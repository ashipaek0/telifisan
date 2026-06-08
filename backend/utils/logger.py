"""
Telifisan v2.0 — Structured JSON logger.
Log viewer reads the log file directly (guaranteed to capture all output).
"""

import json as _json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_config

# ── Direct file writer (bypasses Python logging for background threads) ──
_log_write_lock = threading.Lock()


def write_log(level: str, logger_name: str, message: str):
    """Thread-safe direct write to the log file. Works from any thread."""
    try:
        config = get_config()
        log_file = Path(config["app"]["log_dir"]) / "telifisan.log"
        entry = _json.dumps({
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "level": level.upper(),
            "logger": logger_name,
            "message": message,
        })
        with _log_write_lock:
            with open(log_file, "a") as f:
                f.write(entry + "\n")
        # Also print to stderr for Docker logging
        print(entry, flush=True)
    except Exception:
        pass  # failing to log should never kill the app


def read_log_file(lines: int = 200, level: str = "DEBUG") -> list[dict]:
    """Read recent log entries from the persistent log file."""
    levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = levels.get(level.upper(), 0)

    config = get_config()
    log_file = Path(config["app"]["log_dir"]) / "telifisan.log"
    if not log_file.exists():
        return []

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines * 4:]

        result = []
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except (_json.JSONDecodeError, ValueError):
                entry = {"message": line, "level": "INFO", "timestamp": ""}

            lvl = levels.get(entry.get("level", "INFO"), 99)
            if lvl >= min_level:
                result.append(entry)

        return result[-lines:]
    except Exception:
        return []


def clear_log_file():
    """Truncate the persistent log file."""
    config = get_config()
    log_file = Path(config["app"]["log_dir"]) / "telifisan.log"
    if log_file.exists():
        log_file.write_text("")


def setup_logging():
    """Configure structured JSON logging."""
    config = get_config()
    log_config = config.get("logging", {})
    level_name = log_config.get("level", "DEBUG")
    level = getattr(logging, level_name.upper(), logging.DEBUG)

    log_dir = Path(config["app"]["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)

    log_file = log_dir / "telifisan.log"
    file_handler = logging.FileHandler(str(log_file))
    file_handler.setLevel(level)

    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    console.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_log_level(level_name: str):
    """Change the log level at runtime (DEBUG, INFO, WARNING, ERROR)."""
    level = getattr(logging, level_name.upper(), None)
    if level is None:
        return
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)
    config = get_config()
    config.setdefault("logging", {})["level"] = level_name.upper()
    root.info(f"Log level changed to {level_name.upper()}")
