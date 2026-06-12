"""Compliance engine.

Two layers:
  1. **Deterministic rules** — hand-coded checks over extracted design data.
     Fast, cheap, auditable; cover the high-confidence quantitative cases
     (e.g. corridor width >= 1.4 m, ramp slope <= 1/12).
  2. **LLM-judged checks** — for clauses the rules can't decide, we retrieve
     the relevant clauses and ask a self-hosted OSS LLM (Qwen 2.5 by default,
     served via Ollama/vLLM) to judge with full citations.

Both produce `Finding` records that get persisted by the worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tcvn_copilot.core.logging import get_logger
from tcvn_copilot.db.models.compliance import FindingSeverity, FindingStatus
from tcvn_copilot.domain.compliance.rules import RULES, RuleResult
from tcvn_copilot.rag.llm import complete_json
from tcvn_copilot.rag.prompts.compliance import SYSTEM_PROMPT_VI, build_user_message
from tcvn_copilot.rag.retriever import retrieve

log = get_logger(__name__)


@dataclass(slots=True)
class Finding:
    clause_id: UUID
    status: FindingStatus
    severity: FindingSeverity
    confidence: float
    summary: str
    rationale: str
    remediation: str | None
    location: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class EngineInput:
    design_data: dict[str, Any]
    drawing_ids: list[UUID] = field(default_factory=list)
    standard_codes: list[str] = field(default_factory=list)


async def run_compliance(session: AsyncSession, payload: EngineInput) -> list[Finding]:
    findings: list[Finding] = []

    # --- 1. Deterministic rules pass --------------------------------------
    rule_findings = await _run_rules(session, payload)
    findings.extend(rule_findings)
    rule_clause_ids = {f.clause_id for f in rule_findings}

    # --- 2. LLM-judged pass ----------------------------------------------
    queries = _build_retrieval_queries(payload.design_data)
    for query in queries:
        clauses = await retrieve(
            session,
            query=query,
            standard_codes=payload.standard_codes or None,
        )
        if not clauses:
            continue
        # Don't re-evaluate clauses we already decided deterministically.
        clauses = [c for c in clauses if c.clause_id not in rule_clause_ids]
        if not clauses:
            continue

        llm_payload = {
            "query": query,
            "design_data": payload.design_data,
        }
        clause_blocks = [
            {
                "clause_id": str(c.clause_id),
                "standard_code": c.standard_code,
                "clause_number": c.clause_number,
                "title": c.title,
                "text": c.text,
            }
            for c in clauses
        ]

        try:
            result = await complete_json(
                system=SYSTEM_PROMPT_VI,
                messages=[
                    {
                        "role": "user",
                        "content": build_user_message(
                            design_data=llm_payload, clauses=clause_blocks
                        ),
                    }
                ],
                role="reasoning",
            )
        except Exception as exc:
            log.warning("llm_judge_failed", query=query, error=str(exc))
            continue

        for raw in result.get("findings", []):
            try:
                findings.append(_parse_llm_finding(raw))
            except (KeyError, ValueError) as exc:
                log.warning("llm_finding_invalid", error=str(exc), raw=raw)

    return findings


async def _run_rules(session: AsyncSession, payload: EngineInput) -> list[Finding]:
    out: list[Finding] = []
    for rule in RULES:
        if payload.standard_codes and rule.standard_code not in payload.standard_codes:
            continue
        results: list[RuleResult] = await rule.evaluate(session, payload.design_data)
        for r in results:
            out.append(
                Finding(
                    clause_id=r.clause_id,
                    status=r.status,
                    severity=r.severity,
                    confidence=r.confidence,
                    summary=r.summary,
                    rationale=r.rationale,
                    remediation=r.remediation,
                    location=r.location,
                    raw={"rule": rule.id, "values": r.values},
                )
            )
    return out


def _build_retrieval_queries(design_data: dict[str, Any]) -> list[str]:
    """Generate scoped retrieval queries from extracted design data.

    Strategy: one query per design-concern bucket so retrieval recall stays
    high and we don't shove an entire 50-page extraction into a single embed.
    """
    queries: list[str] = []
    if design_data.get("egress"):
        queries.append("yêu cầu thoát nạn, lối thoát nạn, cầu thang, hành lang, chiều rộng")
    if design_data.get("fire_systems"):
        queries.append("hệ thống phòng cháy chữa cháy, báo cháy, chữa cháy tự động, hút khói")
    if design_data.get("accessibility"):
        queries.append("tiếp cận người khuyết tật, ram dốc, thang máy, nhà vệ sinh tiếp cận")
    if design_data.get("structural_loads"):
        queries.append("tải trọng tác động, tĩnh tải, hoạt tải, tải gió, động đất")
    if design_data.get("rooms"):
        queries.append("diện tích phòng tối thiểu, chiều cao thông thủy, công năng")
    if not queries:
        queries.append("tổng quát yêu cầu kỹ thuật công trình")
    return queries


def _parse_llm_finding(raw: dict[str, Any]) -> Finding:
    return Finding(
        clause_id=UUID(raw["clause_id"]),
        status=FindingStatus(raw["status"]),
        severity=FindingSeverity(raw["severity"]),
        confidence=float(raw.get("confidence", 0.5)),
        summary=str(raw["summary"])[:1024],
        rationale=str(raw["rationale"]),
        remediation=raw.get("remediation"),
        location=raw.get("location"),
        raw=raw,
    )
