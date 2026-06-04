# Telifisan

Self-hosted IPTV playlist manager. Ingest M3U/Xtream sources, validate streams, and serve a clean M3U of live channels.

Pipeline: **Sources → Ingest → Validate → Output → Serve**

## Quick Start

```bash
pip install -r requirements.txt
python -m backend.main
```

API at `http://localhost:8000`. On first boot, a default output profile is created and an API key is logged to stdout. GET requests are public; POST/PUT/DELETE require `Authorization: Bearer <api_key>`.

## Frontend

```bash
cd frontend && npm install && npm run dev
```

Opens at `http://localhost:5173` with Vite proxy to backend. Pages: Dashboard, Sources, Channels.

## M3U Output

`http://localhost:8000/output/default.m3u` — no auth required. Paste into any IPTV app (TiviMate, Plex, Kodi).

## API

| Method | Endpoint | Auth |
|--------|----------|------|
| GET | `/health` | No |
| GET | `/dashboard` | No |
| GET | `/output/default.m3u` | No |
| GET | `/api/v1/logs` | No |
| GET | `/api/v1/config/key` | No |
| GET/POST/PUT/DELETE | `/api/v1/sources` | Write ops only |
| POST | `/api/v1/sources/{id}/ingest` | Yes |
| GET/DELETE | `/api/v1/channels` | Write ops only |
| GET/POST/PUT/DELETE | `/api/v1/profiles` | Write ops only |
| POST | `/api/v1/profiles/{id}/generate` | Yes |
| GET | `/api/v1/profiles/{id}/m3u` | No |
| GET/POST | `/api/v1/tasks` | Yes |
| POST | `/api/v1/config/log-level` | Yes |

## Scheduled Tasks

Running automatically via APScheduler:

- **ingest_sources** — every 6 hours
- **validate_streams** — every 2 hours
- **generate_outputs** — every 1 hour

Manual trigger: `POST /api/v1/tasks/{name}/run` or via Dashboard Quick Actions.

## Processing Pipeline

1. **Ingest** — Fetch M3U URL / Xtream API, parse streams, deduplicate into canonical channels by tvg_id and name
2. **Validate** — HTTP HEAD → ffprobe → streamlink. Concurrent (20 workers). Per-domain rate limiting (4 concurrent). Stale lock timeout 30 min
3. **Output** — Filter dead channels, pick best source stream by priority, generate `#EXTM3U` format playlist

## Configuration

See `config.yaml`:

```yaml
validation:
  concurrency: 20
  per_domain_concurrency: 4
  timeout_ms: 30000
  hard_dead_threshold: 3

logging:
  level: DEBUG
```

Environment: `TELIFISAN_PORT`, `TELIFISAN_DATA_DIR`, `TELIFISAN_DB_URL`, `TELIFISAN_LOG_LEVEL`

## Tests

```bash
python -m pytest tests/ -q
```

16 tests covering ingest, validation, output, and HTTP head checks.

## Docker

```bash
docker build -t telifisan .
docker run -p 8000:8000 -v $(pwd)/data:/data telifisan
```
