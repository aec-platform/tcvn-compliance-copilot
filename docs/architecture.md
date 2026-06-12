# Architecture

This document describes how the TCVN Compliance Copilot is put together. It
assumes you've read the top-level [README](../README.md).

## High-level

```
┌───────────────┐   HTTPS   ┌────────────────┐   gRPC/HTTP   ┌─────────────────┐
│   Next.js UI  │ ────────▶ │   FastAPI API  │ ───────────▶ │  Anthropic API  │
└───────────────┘           └──────┬─────────┘               └─────────────────┘
                                   │
                ┌──────────────────┼───────────────────┐
                ▼                  ▼                   ▼
        ┌──────────────┐   ┌──────────────┐    ┌─────────────────┐
        │  Postgres    │   │  Redis       │    │  Object storage │
        │  + pgvector  │   │ (broker+cache)│    │   (S3 / MinIO)  │
        └──────────────┘   └──────┬───────┘    └─────────────────┘
                                  │
                            ┌─────▼──────────┐
                            │  Celery workers│  ◀── async drawing parse,
                            └────────────────┘      compliance runs, reports
```

## Component responsibilities

### `apps/api` — FastAPI service

- HTTP surface for the web app and any future SaaS integrations.
- Validates input, authenticates the caller, owns the DB session.
- Returns fast: anything that takes >1s is dispatched to a worker.
- Health (`/healthz`), readiness (`/readyz`), Prometheus (`/metrics`).

### `apps/api` — Celery worker

- Same image, different command (`celery worker`).
- Two task families:
  - `drawings.extract`: PDF/OCR/vision-LLM extraction.
  - `compliance.run`: deterministic rules + RAG-judged checks, then renders the report.
- Tasks are idempotent on the `id` of the record being processed.

### Postgres + pgvector

- One database, two roles:
  - **Operational store** for users, projects, drawings, runs, findings.
  - **Vector store** (`pgvector` HNSW) for standard-clause embeddings.
- Schema is managed by Alembic. Embedding dim is wired from `Settings.embedding_dim`.

### Redis

- Celery broker + result backend.
- Application cache (planned: presigned URL cache, embedding cache).

### Object storage (S3 / MinIO)

- Uploaded drawings (private).
- Rendered reports (private; access via short-lived presigned URLs).

### Self-hosted OSS LLM (OpenAI-compatible)

- Default reasoning model: `qwen2.5:32b-instruct` (Apache-2.0, strong VN + JSON).
- Default extraction model: `qwen2.5:7b-instruct` (fast triage, structured output).
- Served via Ollama (dev/CPU) or vLLM / SGLang (production GPU). Both speak
  OpenAI-compatible `/chat/completions` — swap via `LLM_BASE_URL`, no code change.
- Prefix / KV-cache reuse is implicit: the standards-corpus system prompt is
  identical across calls, so the inference server pays the prefill cost ~once
  per server restart. vLLM/SGLang report cache hits in
  `usage.prompt_tokens_details.cached_tokens`.
- **Data sovereignty**: design files never leave operator infrastructure — the
  project mandates OSS, self-hostable models only.

## Request: kicking off a compliance review

1. User uploads a drawing → `POST /uploads`
2. API streams it to object storage, inserts a `Drawing` row, enqueues `drawings.extract`.
3. Worker downloads the file, runs OCR + vision LLM, persists `extracted` JSON.
4. User starts a run → `POST /compliance/runs`
5. API inserts a `ComplianceRun` row (status=`queued`), enqueues `compliance.run`.
6. Worker:
   - Merges `extracted.summary` across all the project's ready drawings.
   - Runs `RULES` (deterministic) — produces high-confidence findings.
   - For each design-concern bucket: hybrid retrieve clauses → ask the OSS LLM to judge.
   - Persists findings; renders PDF+JSON; uploads to object storage.
7. User polls `GET /compliance/runs/{id}` until `status=succeeded`.
8. User fetches `GET /compliance/runs/{id}/report` → 307 to a presigned URL.

## Why pgvector (not Qdrant / Weaviate)?

- One fewer service to operate.
- Standards corpus is ~10k-50k clauses; well within `pgvector` HNSW comfort.
- Cross-joins with relational data (clause ↔ standard ↔ tags) stay in SQL.

We can swap to Qdrant later by adding a `VectorStore` abstraction over
`tcvn_copilot.rag.retriever`. Not premature here.

## Why hybrid retrieval?

Vietnamese standards are dense with domain jargon ("hệ thống ống đứng",
"giới hạn chịu lửa REI 90"). Pure dense retrieval misses exact-term matches;
pure lexical misses paraphrased queries. Reciprocal Rank Fusion of dense
(`pgvector` cosine) + lexical (`pg_trgm` similarity) wins both.

## Determinism: rules first, LLM second

LLMs are not great at "is 1.2 m < 1.4 m". They are great at "this corridor is
described as a means of egress; QCVN 06 article 3.3.5 applies; with width
1.0 m it is non-compliant; rationale: …".

We split:

- **Quantitative checks** → coded in `domain/compliance/rules.py`. Fast, cheap,
  unit-testable.
- **Qualitative / contextual checks** → retrieved + LLM-judged. Cited.

## Observability

- **Logs**: structlog JSON, request_id-scoped.
- **Traces**: OpenTelemetry → OTLP collector → Tempo/Jaeger.
- **Metrics**: Prometheus at `/metrics`.
- **Errors**: Sentry (FastAPI + SQLAlchemy integrations).

All three are best-effort: if the collector / Sentry is unreachable, the API
logs a warning at startup and continues.

## Security posture

- Containers run as non-root (uid 1000), read-only rootfs, no privileges, all caps dropped.
- Argon2id password hashes, short-lived access tokens, longer-lived refresh tokens.
- Baseline security headers via middleware.
- Pre-commit secret scan + CI gitleaks job + CodeQL.
- Dependency scanning (Dependabot weekly, pip-audit + pnpm audit in CI).
- See [SECURITY.md](../SECURITY.md) for disclosure policy.
