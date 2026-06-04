# Telifisan — Multi-stage Docker build

# ── Stage 1: Frontend Builder ─────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist/ ./frontend/build/
RUN mkdir -p /data/logs

EXPOSE 8000
ENV TELIFISAN_PORT=8000 TELIFISAN_DATA_DIR=/data TELIFISAN_LOG_LEVEL=DEBUG

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "-m", "backend.main"]
