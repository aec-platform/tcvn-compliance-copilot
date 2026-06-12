# Deployment

This document covers the three supported deployment modes.

## 1. Local docker-compose (development)

```bash
cp .env.example .env
# review .env: LLM defaults to the bundled Ollama service (no API key needed).
# For GPU production, point LLM_BASE_URL at a vLLM/SGLang gateway instead.
make bootstrap   # build + migrate + seed corpus manifests
make up
make logs
```

Services:
- `http://localhost:3000` — Next.js
- `http://localhost:8000` — FastAPI (`/docs` for Swagger)
- `http://localhost:9001` — MinIO console (`minio_admin`/`minio_admin_password`)
- `localhost:5432` — Postgres
- `localhost:6379` — Redis

## 2. Kubernetes (production)

```bash
# 1) Create the namespace + apply secrets out-of-band (ExternalSecrets / Sealed)
kubectl create namespace tcvn-copilot

# 2) Apply base via Kustomize overlay
kubectl apply -k infra/k8s/overlays/prod

# 3) Wait for rollout
kubectl -n tcvn-copilot rollout status deploy/api
kubectl -n tcvn-copilot rollout status deploy/web
kubectl -n tcvn-copilot rollout status deploy/worker

# 4) One-time DB migration + corpus ingest
kubectl -n tcvn-copilot run --rm -it api-migrate \
  --image=ghcr.io/sophie-nguyenthuthuy/tcvn-compliance-copilot/api:v0.1.0 \
  --env-from=configmap/tcvn-config --env-from=secret/tcvn-secrets \
  --command -- alembic upgrade head
```

### Pre-flight checklist

- [ ] Managed Postgres 16 with `pgvector` available
- [ ] Managed Redis 7+
- [ ] S3 bucket(s) with lifecycle rules matching `UPLOAD_RETENTION_DAYS` /
      `REPORT_RETENTION_DAYS`
- [ ] Anthropic API key with sufficient quota
- [ ] cert-manager (or equivalent) for ingress TLS
- [ ] Standards corpus pre-populated in the operator's storage (see
      `docs/standards.md`)

## 3. Bare metal / VM (not recommended for prod, fine for pilots)

The same `apps/api` image runs anywhere Docker does. Wire it to an external
Postgres + Redis + S3, then put a reverse proxy in front:

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  ghcr.io/sophie-nguyenthuthuy/tcvn-compliance-copilot/api:v0.1.0
```

## Rollback

Releases are tagged `vX.Y.Z` and built immutably. To roll back:

```bash
kubectl -n tcvn-copilot set image deploy/api api=ghcr.io/sophie-nguyenthuthuy/tcvn-compliance-copilot/api:vPREV
```

Migrations are designed to be forward-compatible across one minor version,
but always test a rollback in staging first.

## Backups

- **Postgres**: daily logical backup (`pg_dump`), 30-day retention.
- **Object storage**: versioned bucket + cross-region replication for reports;
  uploads are user-supplied and not part of the operator's recovery scope.
- **Standards corpus**: source of truth is the manifest + raw files; embeddings
  can be regenerated from those with `make corpus-ingest --force`.
