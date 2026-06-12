# Ship checklist — tcvn-compliance-copilot

## 1. Standards corpus

- [ ] **Acquire the full TCVN/QCVN PDFs** for your target verticals.
  - Sources: <https://tieuchuan.vsqi.gov.vn>, <https://moc.gov.vn> (QCVN),
    Bộ Xây Dựng / Bộ Y Tế / Bộ Công Thương publishing portals.
  - Licensing: TCVN documents are copyrighted by VSQI. **A commercial
    redistribution licence is required** to host them in this service for
    paying customers. For internal-use deployments this is usually OK.
- [ ] **Place PDFs under** `packages/standards-corpus/sources/` per the
      `LABELING_GUIDE.md` naming convention.
- [ ] **Ingest** with `make ingest-corpus` (alembic + chunker + embeddings).
- [ ] **Validate** with `make corpus-stats` — should report >= 3 standards
      and >= 500 chunks for a meaningful pilot.

## 2. AI infrastructure

- [ ] **Embedding model**: `BAAI/bge-m3` is pulled by sentence-transformers
      on first request (~2 GB). Pre-warm with `make warmup-embeddings`.
- [ ] **LLM**: dev defaults to `qwen2.5:7b-instruct`. Production GPU:
      set `LLM_REASONING_MODEL=qwen2.5:32b-instruct` and provision a node
      with ≥ 40 GB GPU RAM (A100, L40S, or 2×L4).
- [ ] **vLLM swap** (optional, GPU only): point `LLM_BASE_URL` at a vLLM
      gateway — drops latency from Ollama's ~3 s to ~300 ms p50.

## 3. Compliance posture

- [ ] **Disclaimer banner** on every report: "AI-assisted review, not a
      replacement for licensed engineer sign-off." Already in the
      `apps/web/src/components/Disclaimer.tsx`.
- [ ] **Per-tenant retention** policy documented (default 365 days for
      reports, 30 days for uploads — `RETENTION_*_DAYS` env vars).
- [ ] **DPA signed** with every customer storing their drawings.

## 4. Storage

- [ ] **S3 bucket** provisioned with versioning + lifecycle rule (move to
      Glacier after 90 days).
- [ ] **Presigned-URL TTL** ≤ 1 hour (current default).

## 5. Smoke before release

```
make smoke PROJECT=tcvn-compliance-copilot
cd apps/api && .venv/bin/pytest -q
```
