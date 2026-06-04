# Telifisan v3.0

Self-hosted IPTV playlist lifecycle manager with 70+ files, 34 automated tests, and full CI/CD.

Ingests M3U/Xtream Codes sources, validates streams, applies rules-based filtering and enrichment, and serves cleaned playlists (M3U + XMLTV) to downstream IPTV apps.

## Quick Start

```bash
pip install -r requirements.txt
python -m backend.main
```

API at `http://localhost:8000`. On first boot, an API key is generated and a default admin user created:
- Username: `admin` / Password: `admin`
- Login: `POST /api/v1/auth/login`

## Docker

```bash
docker build -t telifisan .
docker run -p 8000:8000 -v $(pwd)/data:/data telifisan
```

Or with compose:

```bash
docker-compose up -d
```

The Docker image runs as non-root user `telifisan` with a multi-stage build for minimal size.

## CLI

```bash
python -m backend.cli sources list
python -m backend.cli sources ingest <id>
python -m backend.cli channels list --status alive
python -m backend.cli tasks run validate_streams
python -m backend.cli backup
python -m backend.cli rotate-key
```

## Frontend

```bash
cd frontend && npm install && npm run dev
```

Opens at `http://localhost:5173` with Vite proxy to backend. Dark/light theme toggle, 9 pages.

## API

All `/api/v1/` endpoints require `Authorization: Bearer <api_key_or_token>`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness + DB check |
| `GET /dashboard` | Stats overview |
| `GET /proxy-stats` | Live proxy connections |
| `GET /metrics` | Prometheus metrics |
| `POST /api/v1/auth/login` | User login → API token |
| `GET/POST /api/v1/auth/users` | User management |
| `GET/POST /api/v1/sources` | Source CRUD |
| `POST /api/v1/sources/{id}/ingest` | Trigger ingest |
| `GET /api/v1/channels` | Filterable channel list |
| `POST /api/v1/channels/bulk` | Bulk actions |
| `GET/POST /api/v1/rules` | Rule CRUD |
| `GET /api/v1/rules/templates` | Rule templates |
| `POST /api/v1/rules/templates/{id}/import` | Import template |
| `GET/POST /api/v1/profiles` | Profile CRUD |
| `GET /api/v1/profiles/{id}/m3u` | M3U output |
| `GET /api/v1/profiles/{id}/xmltv` | XMLTV output |
| `GET/POST /api/v1/epg-sources` | EPG source CRUD |
| `GET /api/v1/epg-sources/coverage` | EPG coverage report |
| `GET/POST /api/v1/overrides` | Enrichment overrides |
| `GET/PUT /api/v1/config` | System config |
| `GET /api/v1/config/export` | Export all config |
| `POST /api/v1/config/import` | Import config |
| `POST /api/v1/config/backup` | DB backup |
| `POST /api/v1/config/key/rotate` | Rotate API key |
| `GET/POST /api/v1/tasks` | Task management |
| `GET /stream/proxy/{id}` | Stream proxy relay |
| `GET /player_api.php` | Xtream Codes emulation |
| `WS /ws/validate` | WebSocket validation progress |

## Architecture

```
telefisan/
├── backend/
│   ├── main.py              # FastAPI app, CORS, rate limiting, auth
│   ├── models.py            # 13 ORM entities (v3.0)
│   ├── database.py          # SQLite/PostgreSQL + FTS5 search
│   ├── config.py            # YAML + env config
│   ├── cli.py               # CLI management tool
│   ├── alembic.ini          # DB migrations
│   ├── api/                 # 14 API routers
│   ├── services/            # 13 service modules
│   ├── utils/               # 7 utilities
│   └── migrations/          # Alembic migrations
├── frontend/                # React 18+ Vite app (9 pages)
├── tests/                   # 34 pytest tests
├── Dockerfile               # Multi-stage build
├── docker-compose.yml
├── config.yaml
└── .github/workflows/ci.yml # CI/CD pipeline
```

## Processing Pipeline

1. **Ingest** — M3U/Xtream → SourceStreams → CanonicalChannels (tiered matching)
2. **Validate** — HTTP HEAD → HLS manifest → ffprobe → streamlink (20 concurrent)
3. **Enrich** — Name sanitisation, TVDB logos, community DB fallback, category normalisation, country/language, EPG mapping
4. **Rules** — SIMPLE + ADVANCED (condition trees, RestrictedPython scripting, 10 templates)
5. **Output** — M3U/XMLTV per profile (DIRECT/PROXY modes)
6. **Proxy** — Async stream relay with connection + mid-stream failover, ffmpeg transcoding
7. **Xtream** — TiviMate-compatible API emulation
8. **Cleanup** — Orphan removal, data retention, automated daily backups

## Key v3.0 Features

- **PostgreSQL support** — swappable via `database.driver: postgresql`
- **FTS5 full-text search** — 10-100x faster channel search
- **Async proxy** — httpx non-blocking streaming
- **Mid-stream failover** — transparent source switching on connection drop
- **Stream re-encoding** — ffmpeg transcoding with configurable codec/bitrate/resolution
- **Multi-user auth** — admin/viewer roles, token management, audit logs
- **Webhooks** — Slack, Discord, Telegram notifications
- **10 rule templates** — one-click import for common filters
- **Prometheus metrics** — `/metrics` endpoint
- **WebSocket** — real-time validation progress
- **Import/Export** — full config as JSON
- **Alembic migrations** — versioned DB schema

## Configuration

See `config.yaml`. Key sections:

```yaml
database:
  driver: sqlite  # or postgresql
proxy:
  transcode:
    enabled: false
    video_codec: "libx264"
    video_bitrate: "2000k"
security:
  rate_limit_rpm: 300
data_retention:
  validation_records_days: 90
```

Environment overrides: `TELIFISAN_PORT`, `TELIFISAN_DATA_DIR`, `TELIFISAN_DB_URL`, `TELIFISAN_LOG_LEVEL`

## Testing

```bash
cd tests
python -m pytest test_backend.py -v     # 22 unit tests
python -m pytest test_integration.py -v  # 12 integration tests
```
