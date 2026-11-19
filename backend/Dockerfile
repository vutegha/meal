FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Connexions lentes ou instables : délai plus long, moins de téléchargements simultanés et
# nouvelles tentatives, pour que la construction n'échoue pas sur un gros paquet.
ENV UV_HTTP_TIMEOUT=600 UV_CONCURRENT_DOWNLOADS=2 UV_HTTP_RETRIES=5

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Mesures Prometheus partagées entre les processus de l'API (voir app/core/observability.py).
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/metrics API_WORKERS=2

EXPOSE 8000
# Migrations : service `migrate` de docker-compose.yml, avec le compte propriétaire des tables.
# Plusieurs processus (API_WORKERS) : un export ou un pic d'usage n'arrête pas les autres.
CMD ["sh", "-c", "mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"$API_WORKERS\" --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
