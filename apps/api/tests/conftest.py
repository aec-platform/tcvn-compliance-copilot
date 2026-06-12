"""Shared pytest fixtures.

We split unit (no I/O) from integration (postgres + redis). Integration tests
are gated by `pytest -m integration` and `INTEGRATION_DB_URL` in the env.

Env vars must be set BEFORE any tcvn_copilot module is imported — several
modules eagerly read settings at import time (e.g. the pgvector dim binding
in `db/models/standard.py`). The file-level `ruff: noqa: E402` above
acknowledges that the late imports below are intentional.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tcvn:tcvn@localhost:5432/tcvn_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_REASONING_MODEL", "qwen2.5:7b-instruct")
os.environ.setdefault("LLM_EXTRACTION_MODEL", "qwen2.5:7b-instruct")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-with-enough-entropy")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI test client against the FastAPI app."""
    from tcvn_copilot.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
