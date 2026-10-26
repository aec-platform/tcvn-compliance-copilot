# syntax=docker/dockerfile:1.7

# =========================================================================
# Stage 1 — base: Python + system deps for OCR / PDF / CAD parsing
# =========================================================================
FROM python:3.15-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        # PDF & image processing
        poppler-utils \
        libmagic1 \
        libjpeg62-turbo \
        libpng16-16 \
        # OCR — Tesseract + Vietnamese language pack
        tesseract-ocr \
        tesseract-ocr-vie \
        tesseract-ocr-eng \
        # CAD / IFC build deps
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# =========================================================================
# Stage 2 — deps: resolve & install dependencies
# =========================================================================
FROM base AS deps

COPY pyproject.toml uv.lock* ./
# `uv sync --frozen` is reproducible; falls back to resolve if no lock yet.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project; \
    else uv sync --no-dev --no-install-project; fi

# =========================================================================
# Stage 3 — dev: full toolchain + source mounted at runtime
# =========================================================================
FROM deps AS dev

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then uv sync --frozen --no-install-project; \
    else uv sync --no-install-project; fi

COPY . .
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "tcvn_copilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =========================================================================
# Stage 4 — prod: minimal runtime, non-root, healthcheck
# =========================================================================
FROM deps AS prod

# Drop build tools to shrink the image
RUN apt-get purge -y --auto-remove build-essential && rm -rf /var/lib/apt/lists/*

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN groupadd --system --gid 1000 tcvn \
    && useradd --system --uid 1000 --gid tcvn --create-home tcvn \
    && chown -R tcvn:tcvn /app
USER tcvn

ENV PYTHONPATH=/app/src
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "tcvn_copilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
