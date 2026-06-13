"""Evidence-quality + freshness engine (PS3).

Replaces the provided (noise) anomaly_marker with transparent, auditable rules
derived from the REAL columns: freshness_days vs the requirement's audit-frequency
SLA, confidence_score, and status. Produces per-requirement COMPLIANT / PARTIAL /
GAP with an explainable rationale and a next_review_date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.config import get_settings
from app.models.ps3 import Evidence, LinkedEvidence, Requirement, RequirementStatusResult
from app.agents.ps3_linker import LinkResult

COMPLIANT = "COMPLIANT"
PARTIAL = "PARTIAL"
GAP = "GAP"

_TODAY = date(2026, 6, 13)  # evaluation "now"; overridable via evaluate_quality(today=...)


def _flag_link(link: LinkedEvidence, ev: Evidence, req: Requirement, confidence_floor: float) -> None:
    link.stale = ev.freshness_days > req.freshness_sla_days
    link.low_confidence = ev.confidence_score < confidence_floor
    link.unreviewed = ev.status == "Pending_Review"
    link.rejected = ev.status == "Rejected"
    link.needs_update = ev.status == "Needs_Update"
    link.acceptable = ev.status == "Approved" and not link.stale and not link.low_confidence


def link_flags(link: LinkedEvidence) -> list[str]:
    flags = []
    if link.acceptable:
        flags.append("acceptable")
    if link.stale:
        flags.append("stale")
    if link.low_confidence:
        flags.append("low_confidence")
    if link.unreviewed:
        flags.append("unreviewed")
    if link.rejected:
        flags.append("rejected")
    if link.needs_update:
        flags.append("needs_update")
    return flags


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def evaluate_quality(
    requirements: list[Requirement],
    evidence: list[Evidence],
    link_result: LinkResult,
    today: date | None = None,
) -> dict[str, RequirementStatusResult]:
    """Flag every link in place and return per-requirement status results."""
    settings = get_settings()
    confidence_floor = settings.confidence_floor
    today = today or _TODAY

    evidence_by_id = {ev.evidence_id: ev for ev in evidence}
    requirement_by_id = {req.id: req for req in requirements}

    for link in link_result.links:
        ev = evidence_by_id.get(link.evidence_id)
        req = requirement_by_id.get(link.requirement_id)
        if ev and req:
            _flag_link(link, ev, req, confidence_floor)

    statuses: dict[str, RequirementStatusResult] = {}
    for req in requirements:
        links = link_result.links_for(req.id)
        statuses[req.id] = _evaluate_requirement(req, links, evidence_by_id, today)
    return statuses


def _evaluate_requirement(
    req: Requirement,
    links: list[LinkedEvidence],
    evidence_by_id: dict[str, Evidence],
    today: date,
) -> RequirementStatusResult:
    acceptable = [link for link in links if link.acceptable]
    caveated = [link for link in links if not link.acceptable and not link.rejected]

    if acceptable:
        status = COMPLIANT
        status_factor = 1.0
        best = max(acceptable, key=lambda link: link.link_confidence)
    elif caveated:
        status = PARTIAL
        status_factor = 0.55
        best = max(caveated, key=lambda link: link.link_confidence)
    else:
        status = GAP
        status_factor = 0.15
        best = max(links, key=lambda link: link.link_confidence) if links else None

    confidence, rationale = _confidence_and_rationale(
        req, status, status_factor, best, links, evidence_by_id
    )
    next_review = _next_review_date(req, acceptable or links, evidence_by_id, today)

    return RequirementStatusResult(
        requirement_id=req.id,
        status=status,
        confidence=confidence,
        confidence_rationale=rationale,
        next_review_date=next_review.isoformat(),
        linked_evidence_ids=[link.evidence_id for link in links],
    )


def _confidence_and_rationale(req, status, status_factor, best, links, evidence_by_id):
    if best is None:
        return 0.1, (
            f"GAP: no evidence links to this requirement. "
            f"Expected sources: {req.evidence_source or 'n/a'}."
        )

    ev = evidence_by_id.get(best.evidence_id)
    evidence_quality = ev.confidence_score if ev else 0.5
    link_quality = best.link_confidence
    freshness_factor = 1.0
    if ev and req.freshness_sla_days > 0:
        freshness_factor = max(0.0, min(1.0, req.freshness_sla_days / max(ev.freshness_days, 1)))

    confidence = round(
        status_factor * (0.5 * evidence_quality + 0.5 * link_quality) * (0.5 + 0.5 * freshness_factor),
        2,
    )

    age = ev.freshness_days if ev else "?"
    if status == COMPLIANT:
        rationale = (
            f"COMPLIANT: {best.evidence_id} is Approved, {age}d old "
            f"(within {req.freshness_sla_days}d {req.audit_frequency} SLA), "
            f"confidence {evidence_quality:.2f}, link {link_quality:.2f}."
        )
    elif status == PARTIAL:
        issues = ", ".join(link_flags(best)) or "caveated"
        rationale = (
            f"PARTIAL: best evidence {best.evidence_id} is not fully acceptable "
            f"({issues}); {age}d old vs {req.freshness_sla_days}d SLA, confidence {evidence_quality:.2f}."
        )
    else:
        rejected = sum(1 for link in links if link.rejected)
        rationale = (
            f"GAP: {len(links)} linked item(s) but none acceptable "
            f"({rejected} rejected); no Approved, fresh, confident evidence."
        )
    return confidence, rationale


def _next_review_date(req, links, evidence_by_id, today):
    dates = []
    for link in links:
        ev = evidence_by_id.get(link.evidence_id)
        parsed = _parse_date(ev.collection_date) if ev else None
        if parsed:
            dates.append(parsed)
    anchor = max(dates) if dates else today
    return anchor + timedelta(days=req.freshness_sla_days)
