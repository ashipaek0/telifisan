# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telifisan is a self-hosted IPTV playlist lifecycle manager. It ingests raw M3U playlists and Xtream Codes API sources from multiple providers, validates streams, applies rules-based filtering and enrichment, and serves cleaned, enriched playlists (M3U and XMLTV) to downstream IPTV apps.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (async), SQLite, Alembic, APScheduler
- **Frontend:** React 18+ with Vite, Tailwind CSS (dark theme default), React Router, Axios, Recharts
- **Deployment:** Docker (single-container), Docker Compose, SQLite on mounted `/data` volume
- **External tools:** ffmpeg/ffprobe, streamlink

## Architecture

The app follows a service-layer architecture with FastAPI routers delegating to services:

- **`backend/main.py`** — FastAPI app entry point on port 8000
- **`backend/models.py`** — SQLAlchemy ORM models (all entities, Base = declarative_base())
- **`backend/database.py`** — DB init, session management; FastAPI dependency `get_db()` yields sessions
- **`backend/config.py`** — Config loading from YAML + env vars
- **`backend/api/`** — FastAPI routers per entity: sources, channels, rules, profiles, epg, tasks, proxy, xtream, config, health
- **`backend/services/`** — Business logic: ingest, validation, rules, enrichment, epg, output, proxy, xtream, scheduler
- **`backend/utils/`** — Helpers: m3u_parser, xmltv_parser, ffmpeg wrapper, streamlink wrapper, logos, fuzzy_match, logger
- **`backend/migrations/`** — Alembic migrations

## Database Schema

SQLAlchemy ORM with SQLite. Key entities and relationships:

- **Source** — M3U_URL, M3U_FILE, or XTREAM_CODES_API. Has many SourceStreams.
- **SourceStream** — Each raw stream copy from a source. Links to CanonicalChannel (nullable initially).
- **CanonicalChannel** — Deduplicated logical channel. Linked from SourceStreams, ValidationRecords, EPGProgrammes.
- **ValidationRecord** — History of stream checks (ffprobe, streamlink, HTTP HEAD). Indexed by `(source_stream_id, checked_at DESC)`.
- **Rule** — SIMPLE or ADVANCED mode. Applies at INGEST or OUTPUT. Has priority ordering.
- **OutputProfile** — M3U/XMLTV output config. DIRECT or PROXY mode. Generated on schedule.
- **EPGSource** / **EPGProgramme** — XMLTV sources and cached programme data.
- **EnrichmentOverride** — Manual field locks that prevent auto-enrichment from overwriting.
- **TaskLog** — Audit trail for background task executions with stats JSON.
- **SystemConfig** — Key-value store for app settings.

## API Response Format

All endpoints return: `{success: bool, data: ..., error: {code, message, details}, timestamp}`

Error codes: 400 (validation), 404 (not found), 409 (conflict), 500 (internal).

## Core Processing Pipeline

1. **Ingest** — Fetch M3U/XMLTV/Xtream, parse, create SourceStreams, link to CanonicalChannels
2. **Validate** — Concurrent ffprobe/streamlink checks; produces ValidationRecords; updates uptime% and ALIVE/SOFT_DEAD/HARD_DEAD status
3. **Enrich** — Name sanitisation, logo resolution (source → community DB → TVDB → placeholder), category normalisation, country/language tagging, EPG fuzzy matching
4. **Rules** — SIMPLE (field/operator/value) or ADVANCED (nested condition tree + Python scripts). Source rules filter at INGEST; output rules filter at OUTPUT.
5. **Output** — Select best SourceStream per channel (prefer ALIVE, fallback to SOFT_DEAD, skip HARD_DEAD), apply rules, sort/group, generate M3U (DIRECT or PROXY URL rewrite) + XMLTV
6. **Proxy** — Relay streams in PROXY mode with transparent failover across source copies
7. **Xtream Codes** — Emulate Xtream Codes API for apps like TiviMate (categories, streams, EPG)

## Names and Style

- Classes: PascalCase; functions/methods: snake_case; constants: UPPER_SNAKE_CASE
- DB tables: snake_case plural (e.g., `source_streams`)
- API endpoints: kebab-case paths under `/api/v1/`
- Frontend components: PascalCase, files match component name
- Commit messages: `[module] description` (e.g., `[ingest] add Xtream Codes support`)

## Implementation Build Order (from spec)

1. `models.py` → `database.py` → `config.py` → `main.py`
2. `services/ingest.py` → `api/sources.py`
3. `services/validation.py`
4. `services/rules.py` (SIMPLE mode first)
5. `services/enrichment.py`
6. `services/epg.py`
7. `services/output.py`
8. `services/proxy.py`
9. `services/xtream.py`
10. `services/scheduler.py`
11. Frontend pages in parallel with backend services

## Key Design Decisions

- **Stream status:** SOFT_DEAD = last check failed but passed before; HARD_DEAD = N consecutive failures (default 3). This prevents transient network hiccups from permanently removing channels.
- **EnrichmentOverride.locked=true** prevents any auto-enrichment from overwriting that field. Manual changes stick.
- **PROXY mode** rewrites all stream URLs in M3U to `/stream/proxy/{stream_id}` so clients connect through Telifisan with failover support.
- **Validation concurrency** default 20 parallel ffprobe processes, 30s timeout per stream.
- **EPG timezone:** Store as UTC in DB; apply source timezone on parse, reverse on serve.
- **Soft-delete** for removed streams (not hard-delete by default) to preserve history.
