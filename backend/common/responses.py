"""
Telifisan — Common API response utilities.
Standardized response format for all API endpoints.
"""

from datetime import datetime, timezone
from typing import Any, Optional


class APIError:
    """Standard API error structure."""
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}


def success_response(data: Any = None) -> dict:
    """Create a standardized successful API response."""
    return {
        "success": True,
        "data": data,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    """Create a standardized error API response."""
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
