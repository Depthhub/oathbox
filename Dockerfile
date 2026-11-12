# Oathbox: one container serving the API and the built web app.
#   docker build -t oathbox .
#   docker run -p 8000:8000 --env-file .env -v oathbox-data:/data oathbox

# 1. Build the web app
FROM node:20-bookworm-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ ./
RUN npm run build

# 2. Python runtime
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OATHBOX_STATE_DIR=/data
WORKDIR /app

# Exact tested dependency versions first (cached layer), then the app itself
COPY backend/requirements.lock backend/requirements.lock
RUN pip install -r backend/requirements.lock
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/oathbox backend/oathbox
RUN pip install --no-deps -e backend

COPY sample-dataroom sample-dataroom
# Public attestation reports for receipts made before this deployment
COPY attestations attestations
COPY --from=web /app/web/dist web/dist

# Runs as root on purpose: hosts mount the persistent disk at /data owned by root.
RUN mkdir -p /data

EXPOSE 8000
# --proxy-headers: behind the host's load balancer, rate limits see the real visitor address
CMD ["sh", "-c", "uvicorn oathbox.app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
