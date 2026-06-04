"""
Telifisan v2.0 — M3U Playlist Parser.

Parses #EXTM3U playlists with #EXTINF tags. Handles malformed
entries with skip-and-log strategy. Reports parse error stats.
"""

import re
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger("telifisan.m3u_parser")


def parse_m3u(content: str) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Parse an M3U playlist string.

    Returns:
        (streams, stats) where streams is a list of dicts with keys:
        name, url, group, tvg_id, tvg_name, logo, duration, extra_attributes
        and stats is {total_lines, parsed, skipped, errors}.
    """
    streams: List[Dict[str, Any]] = []
    stats = {"total_lines": 0, "parsed": 0, "skipped": 0, "errors": 0}

    lines = content.splitlines()
    stats["total_lines"] = len(lines)

    current_attrs: Dict[str, Any] = {}
    current_name = ""

    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        if not line or line.startswith("#EXTM3U"):
            continue

        if line.startswith("#EXTINF:"):
            # Parse EXTINF: -1 tvg-id="xxx" tvg-name="yyy" group-title="zzz",Channel Name
            try:
                current_attrs = _parse_extinf(line)
                current_name = current_attrs.get("name", "Unknown")
            except Exception as e:
                logger.warning(f"Line {line_num}: Failed to parse EXTINF: {e}")
                stats["errors"] += 1
                current_attrs = {}
                current_name = ""

        elif line.startswith("#"):
            # Comment line, skip
            continue

        elif current_name or current_attrs:
            # This is a URL line following an EXTINF
            url = line
            if not _is_valid_url(url):
                logger.warning(f"Line {line_num}: Invalid URL: {url[:80]}")
                stats["errors"] += 1
                current_attrs = {}
                current_name = ""
                continue

            stream = {
                "name": current_name or "Unknown",
                "url": url,
                "group": current_attrs.get("group", ""),
                "tvg_id": current_attrs.get("tvg_id", ""),
                "tvg_name": current_attrs.get("tvg_name", ""),
                "logo": current_attrs.get("logo", ""),
                "duration": current_attrs.get("duration", -1),
                "extra_attributes": current_attrs.get("extra", {}),
            }
            streams.append(stream)
            stats["parsed"] += 1
            current_attrs = {}
            current_name = ""

        else:
            # URL without preceding EXTINF
            logger.warning(f"Line {line_num}: URL without EXTINF tag, skipping")
            stats["skipped"] += 1

    return streams, stats


def _parse_extinf(line: str) -> Dict[str, Any]:
    """Parse a single #EXTINF line into a dict."""
    result: Dict[str, Any] = {
        "name": "",
        "group": "",
        "tvg_id": "",
        "tvg_name": "",
        "logo": "",
        "duration": -1,
        "extra": {},
    }

    # Remove #EXTINF: prefix
    content = line[8:].strip()

    # Extract duration (-1 or numeric)
    duration_match = re.match(r"(-?\d+)", content)
    if duration_match:
        result["duration"] = int(duration_match.group(1))
        content = content[duration_match.end():].strip()

    # Parse attributes: key="value" pairs
    attr_pattern = re.compile(r'([\w-]+)="([^"]*)"')
    known_attrs = {"tvg-id": "tvg_id", "tvg-name": "tvg_name",
                   "group-title": "group", "tvg-logo": "logo"}

    for match in attr_pattern.finditer(content):
        key = match.group(1)
        value = match.group(2)
        if key in known_attrs:
            result[known_attrs[key]] = value
        else:
            result["extra"][key] = value

    # Remove parsed attributes from content
    content = attr_pattern.sub("", content)

    # What remains after the first comma is the channel name
    comma_idx = content.find(",")
    if comma_idx >= 0:
        result["name"] = content[comma_idx + 1:].strip()
    elif content.strip():
        result["name"] = content.strip()

    return result


def _is_valid_url(url: str) -> bool:
    """Check if a string is a valid HTTP/RTMP/HLS URL."""
    url = url.strip()
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https", "rtmp", "rtmps") and bool(parsed.netloc)
