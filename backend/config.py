"""
Telifisan v2.0 — Configuration loading.

Loads from config.yaml with environment variable overrides.
"""

import os
import secrets
from pathlib import Path
from typing import Any, Dict

import yaml

_DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "telifisan",
        "version": "1.0",
        "port": 8000,
        "data_dir": "./data",
        "log_dir": "./data/logs",
    },
    "database": {
        "driver": "sqlite",
    },
    "validation": {
        "concurrency": 20,
        "per_domain_concurrency": 4,
        "timeout_ms": 30000,
        "hard_dead_threshold": 3,
        "uptime_window_size": 10,
        "inter_stream_delay_ms": 50,
    },
    "security": {
        "api_key_length": 48,
    },
    "logging": {
        "level": "DEBUG",
    },
}

_config: Dict[str, Any] | None = None


def _find_config_file() -> Path | None:
    """Search for config.yaml in standard locations."""
    candidates = [
        Path("config.yaml"),
        Path("/data/config.yaml"),
        Path(os.environ.get("TELIFISAN_CONFIG_DIR", "")) / "config.yaml" if os.environ.get("TELIFISAN_CONFIG_DIR") else None,
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides to config."""
    env_map = {
        "TELIFISAN_PORT": ("app", "port", int),
        "TELIFISAN_DATA_DIR": ("app", "data_dir", str),
        "TELIFISAN_DB_URL": ("database", "url", str),
        "TELIFISAN_TVDB_API_KEY": ("enrichment", "tvdb_api_key", str),
        "TELIFISAN_LOG_LEVEL": ("logging", "level", str),
    }
    for env_var, (section, key, cast) in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            config.setdefault(section, {})[key] = cast(value)
    return config


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load configuration from file + env overrides."""
    global _config

    config = _DEFAULT_CONFIG.copy()

    # Load from file
    if config_path is None:
        config_path = _find_config_file()

    if config_path and config_path.exists():
        with open(config_path, "r") as f:
            file_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, file_config)

    # Apply env overrides
    config = _apply_env_overrides(config)

    # Ensure data directories exist
    data_dir = config["app"]["data_dir"]
    log_dir = config["app"]["log_dir"]
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "logos"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "backups"), exist_ok=True)

    _config = config
    return config


def get_config() -> Dict[str, Any]:
    """Get the current configuration, loading if needed."""
    global _config
    if _config is None:
        load_config()
    return _config  # type: ignore[return-value]


def generate_api_key() -> str:
    """Generate a new API key."""
    length = get_config().get("security", {}).get("api_key_length", 48)
    return secrets.token_urlsafe(length)
