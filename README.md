# Telifisan

Self-hosted IPTV playlist manager. Ingest M3U/Xtream sources, validate streams, serve a clean M3U of live channels.

## Quick Start

```bash
mkdir telifisan-data && cd telifisan-data
curl -O https://raw.githubusercontent.com/irunmole/telifisan/main/docker-compose.yml
docker compose up -d
```

Open `http://localhost:8000` — API key is logged to the container output.

```
docker logs telifisan | grep "API key"
```

## M3U Output

```
http://localhost:8000/output/default.m3u
```

No auth required. Paste into any IPTV app (TiviMate, Plex, Kodi).

## Frontend

```
http://localhost:8000
```

Dashboard, Sources, and Channels pages. Write operations (ingest, delete) require the API key in the Authorization header.

## API

| Method | Endpoint | Auth |
|--------|----------|------|
| GET | `/health` | No |
| GET | `/dashboard` | No |
| GET | `/output/default.m3u` | No |
| GET/POST/PUT/DELETE | `/api/v1/sources` | Write ops |
| POST | `/api/v1/sources/{id}/ingest` | Yes |
| GET/DELETE | `/api/v1/channels` | Write ops |
| GET/POST | `/api/v1/tasks` | Yes |
| POST | `/api/v1/tasks/{name}/stop` | Yes |
| POST | `/api/v1/config/log-level` | Yes |

## Configuration

See `config.yaml`:

```yaml
validation:
  concurrency: 20
  timeout_ms: 30000
  hard_dead_threshold: 3

logging:
  level: DEBUG
```

Environment: `TELIFISAN_PORT`, `TELIFISAN_DATA_DIR`, `TELIFISAN_DB_URL`, `TELIFISAN_LOG_LEVEL`

## Development

```bash
pip install -r requirements.txt
python -m backend.main

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Tests: `python -m pytest tests/`
