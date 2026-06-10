# ─────────────────────────────────────────────────────────────────────────
# AEGIS — single-image deploy: Next.js dashboard (static) + FastAPI backend.
# Stage 1 builds the dashboard to static files; stage 2 runs the Python API,
# which serves those files on the same origin. One service, one public URL.
# ─────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the dashboard into static files (dashboard/out) ──────────
FROM node:20-alpine AS dashboard
WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
ENV STATIC_EXPORT=1
RUN npm run build          # -> /app/dashboard/out

# ── Stage 2: the Python backend (serves the API + the built dashboard) ──────
FROM python:3.12-slim AS app
WORKDIR /app

# System certs only; no build toolchain needed (all deps ship wheels).
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_PROVIDER=mock \
    MODEL_CACHE=true

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY --from=dashboard /app/dashboard/out ./dashboard/out

EXPOSE 8000
# Render (and most PaaS) inject $PORT; default to 8000 for plain `docker run`.
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
