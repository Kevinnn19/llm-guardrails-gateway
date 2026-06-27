# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install uv==0.4.30

WORKDIR /app

# ---- deps layer (cached unless pyproject.toml / uv.lock change) ----
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

# ---- runtime image ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv
COPY app/ ./app/
COPY policies/ ./policies/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
