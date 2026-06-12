# ADR 0002: Deterministic rules first, LLM judgment second

- **Status**: Accepted
- **Date**: 2026-05-14
- **Deciders**: Founding team

## Context

Quantitative TCVN/QCVN requirements ("hành lang ≥ 1,4 m", "ram ≤ 1/12") are
trivial for code and *not* trivial for LLMs to do reliably. Qualitative
requirements ("phù hợp với chức năng sử dụng", "cấu tạo bảo đảm an toàn") are
the opposite.

## Decision

Two-pass compliance engine:

1. **Rules pass** — hand-coded Python in `domain/compliance/rules.py`.
   Each rule binds to one specific clause and tests one specific numeric
   threshold. Output is a `RuleResult` with `clause_id`, `severity`, `confidence`,
   and reproducible `values`.
2. **LLM pass** — for each design-concern bucket, RAG retrieves the most
   relevant clauses (minus those the rules already covered) and asks the
   self-hosted OSS LLM (Qwen 2.5 by default, OpenAI-compatible endpoint)
   to judge. Output is parsed into the same `Finding` schema.

## Consequences

**Positive**
- Quantitative violations are auditable: the rule, the threshold, the
  observed value are all in the row's `raw` field.
- Cost: rules don't call the API. The LLM only judges what rules can't.
- Tests: rules are pure async functions with one fake-session fixture.
- Determinism on the same input — engineering review can reproduce the report.

**Negative**
- Two pipelines means two places to maintain.
- Rule coverage is sparse on day one; we lean heavily on the LLM until rules
  are filled out.

## Migration path

Each new deterministic rule shrinks the LLM-judged surface. Aim is for the
top 20 most-cited clauses to have rules within 6 months; the rest stay
LLM-judged.
