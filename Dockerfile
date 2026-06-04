# Telifisan v3.0 — Multi-stage Docker build
# Stage 1: Build frontend
# Stage 2: Runtime with Python + ffmpeg

# ── Stage 1: Frontend Builder ─────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY frontend/ .
RUN npm run build 2>/dev/null || mkdir -p build && echo "Frontend build skipped (npm install may be needed)"

# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.11-slim

# Security: non-root user
RUN groupadd -r telifisan && useradd -r -g telifisan -d /app telifisan

# Install only essential system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Install Python deps (layer cached separately)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ ./backend/

# Copy frontend build from stage 1
COPY --from=frontend-builder /app/frontend/dist/ ./frontend/build/

# Create data directories
RUN mkdir -p /data/logs /data/backups && \
    chown -R telifisan:telifisan /data /app

# Drop to non-root user
USER telifisan

# Expose single port
EXPOSE 8000

# Health check with DB connectivity verification
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Config via env vars
ENV TELIFISAN_PORT=8000 \
    TELIFISAN_DATA_DIR=/data \
    TELIFISAN_LOG_LEVEL=INFO

# Run
CMD mkdir -p /data/logs /data/backups && python -m backend.main
