"""Report assembler (PS3 Report Quality, 20 pts).

Builds the auditor-ready PS3ReportResponse from the deterministic pipeline
outputs. The LLM writes narratives + an executive summary in a single batched
call (it only narrates pre-computed facts and must cite evidence ids); a
deterministic, evidence-citing fallback is used whenever the LLM is disabled or
fails. No status/decision is ever made by the LLM.
"""

from __future__ import annotations

import logging

from app.agents.ps3_linker import LinkResult
from app.agents.ps3_quality import COMPLIANT, GAP, PARTIAL, link_flags
from app.config import get_settings
from app.models.ps3 import (
    Evidence,
    PS3LinkedEvidenceView,
    PS3ReportResponse,
    PS3Summary,
    Requirement,
    RequirementReport,
    RequirementStatusResult,
)
from app.models.ps3 import AgentTraceEntry

logger = logging.getLogger(__name__)

MAX_EVIDENCE_PER_REQUIREMENT = 8
DISCLAIMER = (
    "Compliance statuses are derived deterministically from evidence attributes "
    "(freshness vs audit-frequency SLA, confidence, review status) and semantic "
    "linking — not from the dataset's provided anomaly labels, which were found "
    "inconsistent with the underlying evidence. Narratives are LLM-written from "
    "these computed facts. Review with a qualified auditor."
)


def _link_view(link, ev: Evidence | None) -> PS3LinkedEvidenceView:
    return PS3LinkedEvidenceView(
        evidence_id=link.evidence_id,
        type=ev.evidence_type if ev else "",
        framework=ev.framework if ev else "",
        collection_date=ev.collection_date if ev else "",
        freshness_days=ev.freshness_days if ev else 0,
        confidence_score=ev.confidence_score if ev else 0.0,
        link_confidence=link.link_confidence,
        status=ev.status if ev else "",
        flags=link_flags(link),
    )


def _flag_counts(links) -> dict[str, int]:
    keys = ("stale", "low_confidence", "unreviewed", "needs_update", "rejected")
    return {key: sum(1 for link in links if getattr(link, key)) for key in keys}


def _requirement_gaps(req: Requirement, links, status: str) -> list[str]:
    if status == COMPLIANT:
        return []
    if status == GAP and not links:
        return [f"No evidence collected for this requirement. Expected sources: {req.evidence_source or 'n/a'}."]

    counts = _flag_counts(links)
    gaps: list[str] = []
    if status == GAP and counts["rejected"] == len(links) and links:
        gaps.append(f"All {len(links)} linked evidence item(s) were rejected; no usable proof.")
    if counts["stale"]:
        gaps.append(
            f"{counts['stale']} evidence item(s) are stale (older than the "
            f"{req.freshness_sla_days}d {req.audit_frequency} SLA)."
        )
    if counts["low_confidence"]:
        gaps.append(f"{counts['low_confidence']} item(s) below the 0.70 confidence floor.")
    if counts["unreviewed"]:
        gaps.append(f"{counts['unreviewed']} item(s) pending review.")
    if counts["needs_update"]:
        gaps.append(f"{counts['needs_update']} item(s) flagged needs-update.")
    return gaps


def _fallback_narrative(req: Requirement, status_result: RequirementStatusResult, gaps: list[str]) -> str:
    head = {COMPLIANT: "is COMPLIANT", PARTIAL: "is PARTIALLY met", GAP: "is a GAP"}[status_result.status]
    text = f"Requirement {req.id} ({req.text}) {head}. {status_result.confidence_rationale}"
    if gaps:
        text += " " + " ".join(gaps)
    return text


def _sorted_links(links):
    return sorted(links, key=lambda link: (not link.acceptable, -link.link_confidence))


def build_summary(
    requirements: list[Requirement],
    evidence: list[Evidence],
    link_result: LinkResult,
    statuses: dict[str, RequirementStatusResult],
    exec_summary: str,
) -> PS3Summary:
    total = len(requirements) or 1
    compliant = sum(1 for s in statuses.values() if s.status == COMPLIANT)
    partial = sum(1 for s in statuses.values() if s.status == PARTIAL)
    gap = sum(1 for s in statuses.values() if s.status == GAP)
    covered = sum(1 for s in statuses.values() if s.linked_evidence_ids)
    linked = len(link_result.links) or 1
    fresh_links = sum(1 for link in link_result.links if not link.stale)
    auto = sum(1 for e in evidence if e.source.startswith(("bucket", "cloudtrail")))
    frameworks = sorted({fw for req in requirements for fw in req.frameworks})

    return PS3Summary(
        total_requirements=len(requirements),
        compliant_count=compliant,
        partial_count=partial,
        gap_count=gap,
        overall_compliance_pct=round(compliant / total * 100, 1),
        coverage_pct=round(covered / total * 100, 1),
        freshness_pct=round(fresh_links / linked * 100, 1),
        total_evidence=len(evidence),
        linked_evidence_count=len(link_result.links),
        orphan_count=len(link_result.orphan_evidence_ids),
        auto_collected_pct=round(auto / (len(evidence) or 1) * 100, 1),
        frameworks=frameworks,
        exec_summary=exec_summary,
    )


def build_ps3_report(
    request_id: str,
    generated_at: str,
    requirements: list[Requirement],
    evidence: list[Evidence],
    link_result: LinkResult,
    statuses: dict[str, RequirementStatusResult],
    narratives: dict[str, str] | None = None,
    exec_summary: str | None = None,
    agent_trace: list[AgentTraceEntry] | None = None,
) -> PS3ReportResponse:
    narratives = narratives or {}
    evidence_by_id = {e.evidence_id: e for e in evidence}

    reports: list[RequirementReport] = []
    for req in sorted(requirements, key=lambda r: r.id):
        status_result = statuses[req.id]
        links = link_result.links_for(req.id)
        gaps = _requirement_gaps(req, links, status_result.status)
        views = [
            _link_view(link, evidence_by_id.get(link.evidence_id))
            for link in _sorted_links(links)[:MAX_EVIDENCE_PER_REQUIREMENT]
        ]
        narrative = narratives.get(req.id) or _fallback_narrative(req, status_result, gaps)

        reports.append(
            RequirementReport(
                id=req.id,
                name=req.text,
                text=req.text,
                policy_id=req.policy_id,
                frameworks=req.frameworks,
                status=status_result.status,
                confidence=status_result.confidence,
                freshness_sla_days=req.freshness_sla_days,
                audit_frequency=req.audit_frequency,
                linked_evidence=views,
                narrative=narrative,
                confidence_rationale=status_result.confidence_rationale,
                next_review_date=status_result.next_review_date,
                gaps=gaps,
            )
        )

    summary = build_summary(
        requirements, evidence, link_result, statuses, exec_summary or _fallback_exec_summary(requirements, statuses)
    )

    return PS3ReportResponse(
        request_id=request_id,
        generated_at=generated_at,
        summary=summary,
        requirements=reports,
        orphan_evidence_ids=link_result.orphan_evidence_ids,
        agent_trace=agent_trace or [],
        disclaimer=DISCLAIMER,
    )


def _fallback_exec_summary(requirements, statuses) -> str:
    total = len(requirements) or 1
    compliant = sum(1 for s in statuses.values() if s.status == COMPLIANT)
    partial = sum(1 for s in statuses.values() if s.status == PARTIAL)
    gap = sum(1 for s in statuses.values() if s.status == GAP)
    return (
        f"Of {len(requirements)} policy requirements, {compliant} are COMPLIANT, "
        f"{partial} PARTIALLY met, and {gap} are GAPs "
        f"({round(compliant / total * 100)}% fully compliant). Partial and gap "
        f"requirements are driven by stale or unreviewed evidence; see per-requirement "
        f"detail for the specific proof required."
    )


# --- LLM narrative generation (batched, single call, with deterministic fallback) ---


def generate_report_text(
    requirements: list[Requirement],
    evidence: list[Evidence],
    link_result: LinkResult,
    statuses: dict[str, RequirementStatusResult],
) -> tuple[dict[str, str], str]:
    """Return (narratives_by_requirement_id, executive_summary). Falls back to
    deterministic, evidence-citing text if the LLM is disabled or errors."""
    settings = get_settings()
    fallback_exec = _fallback_exec_summary(requirements, statuses)
    fallback_narr = {
        req.id: _fallback_narrative(
            req, statuses[req.id], _requirement_gaps(req, link_result.links_for(req.id), statuses[req.id].status)
        )
        for req in requirements
    }

    if not (settings.ps3_llm_narratives and settings.openai_enabled and settings.openai_api_key):
        return fallback_narr, fallback_exec

    try:
        from app.llm.client import llm_json
        from app.llm.ps3_prompts import REPORT_SYSTEM, REPORT_USER

        result = llm_json(
            system_prompt=REPORT_SYSTEM,
            user_prompt=REPORT_USER.format(
                summary_block=_summary_block(requirements, evidence, link_result, statuses),
                requirement_blocks=_requirement_blocks(requirements, evidence, link_result, statuses),
            ),
        )
        narratives = {**fallback_narr}
        for rid, text in (result.get("narratives") or {}).items():
            if rid in narratives and isinstance(text, str) and text.strip():
                narratives[rid] = text.strip()
        exec_summary = str(result.get("executive_summary") or "").strip() or fallback_exec
        return narratives, exec_summary
    except Exception:
        logger.warning("LLM report narration failed; using deterministic fallback", exc_info=True)
        return fallback_narr, fallback_exec


def _summary_block(requirements, evidence, link_result, statuses) -> str:
    s = build_summary(requirements, evidence, link_result, statuses, "")
    return (
        f"requirements={s.total_requirements}; compliant={s.compliant_count}; "
        f"partial={s.partial_count}; gap={s.gap_count}; overall_compliance={s.overall_compliance_pct}%; "
        f"coverage={s.coverage_pct}%; freshness={s.freshness_pct}%; "
        f"auto_collected={s.auto_collected_pct}%; frameworks={', '.join(s.frameworks)}"
    )


def _requirement_blocks(requirements, evidence, link_result, statuses) -> str:
    evidence_by_id = {e.evidence_id: e for e in evidence}
    blocks = []
    for req in sorted(requirements, key=lambda r: r.id):
        st = statuses[req.id]
        links = _sorted_links(link_result.links_for(req.id))[:5]
        ev_lines = []
        for link in links:
            ev = evidence_by_id.get(link.evidence_id)
            flags = ",".join(link_flags(link)) or "ok"
            ev_lines.append(
                f"    - {link.evidence_id} ({ev.evidence_type if ev else '?'}, "
                f"{ev.freshness_days if ev else '?'}d, conf {ev.confidence_score if ev else '?'}, [{flags}])"
            )
        blocks.append(
            f"- {req.id}: {req.text}\n"
            f"  frameworks={', '.join(req.frameworks)}; audit={req.audit_frequency} (SLA {req.freshness_sla_days}d); "
            f"status={st.status}; confidence={st.confidence}; expected_sources={req.evidence_source}\n"
            f"  rationale: {st.confidence_rationale}\n"
            f"  linked_evidence:\n" + ("\n".join(ev_lines) if ev_lines else "    (none)")
        )
    return "\n".join(blocks)
