import logging
import re
from collections import OrderedDict
from typing import Any

from app.models.compliance import (
    ComplianceEvaluation,
    ControlComplianceResult,
    EvidenceElementResult,
)
from app.models.controls import ControlRequirement, RequiredEvidenceElement
from app.models.evidence import EvidenceChunk, EvidenceCitation

logger = logging.getLogger(__name__)


ANY_TERM_ELEMENT_IDS = {
    "retention_180_days",
    "revocation_evidence",
}


def evaluate_compliance(
    controls: list[ControlRequirement],
    chunks: list[EvidenceChunk],
) -> ComplianceEvaluation:
    return ComplianceEvaluation(
        control_results=[
            evaluate_control_compliance(control=control, chunks=chunks)
            for control in controls
        ]
    )


def evaluate_control_compliance(
    control: ControlRequirement,
    chunks: list[EvidenceChunk],
) -> ControlComplianceResult:
    target_artifacts = set(control.target_artifacts)
    target_chunks = [
        chunk for chunk in chunks if chunk.artifact in target_artifacts
    ]

    return ControlComplianceResult(
        control_id=control.id,
        control_name=control.name,
        target_artifacts=control.target_artifacts,
        target_chunk_count=len(target_chunks),
        element_results=[
            evaluate_evidence_element(
                control_id=control.id,
                element=element,
                chunks=target_chunks,
            )
            for element in control.required_evidence_elements
        ],
    )


def evaluate_evidence_element(
    control_id: str,
    element: RequiredEvidenceElement,
    chunks: list[EvidenceChunk],
) -> EvidenceElementResult:
    citations = _find_citations(element.search_terms, chunks)
    negative_hits = _find_citations(element.negative_terms, chunks)
    matched_terms = _ordered_matched_terms(citations)
    matched_term_set = set(matched_terms)
    if element.id in ANY_TERM_ELEMENT_IDS:
        missing_terms = [] if matched_terms else element.search_terms
    else:
        missing_terms = [
            term for term in element.search_terms if term not in matched_term_set
        ]

    return EvidenceElementResult(
        control_id=control_id,
        element_id=element.id,
        label=element.label,
        critical=element.critical,
        satisfied=not missing_terms and not negative_hits,
        matched_terms=matched_terms,
        missing_terms=missing_terms,
        citations=citations,
        negative_hits=negative_hits,
        reviewer_gap=element.reviewer_gap,
    )


def _find_citations(
    terms: list[str],
    chunks: list[EvidenceChunk],
) -> list[EvidenceCitation]:
    if not terms:
        return []

    citation_by_chunk: OrderedDict[str, EvidenceCitation] = OrderedDict()
    for chunk in chunks:
        matched_terms = [term for term in terms if _term_matches_chunk(term, chunk)]
        if not matched_terms:
            continue

        key = f"{chunk.artifact}:{chunk.location}:{chunk.hash}"
        citation_by_chunk[key] = EvidenceCitation(
            artifact=chunk.artifact,
            location=chunk.location,
            hash=chunk.hash,
            excerpt=chunk.text,
            matched_terms=matched_terms,
        )

    return list(citation_by_chunk.values())


def _ordered_matched_terms(citations: list[EvidenceCitation]) -> list[str]:
    matched_terms: list[str] = []
    for citation in citations:
        for term in citation.matched_terms:
            if term not in matched_terms:
                matched_terms.append(term)
    return matched_terms


def _term_matches_chunk(term: str, chunk: EvidenceChunk) -> bool:
    normalized_term = _normalize_text(term)
    if normalized_term in chunk.normalized_text:
        return True

    return _compact_text(term) in _compact_text(chunk.text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def enrich_compliance_with_llm(
    control: ControlRequirement,
    compliance_result: ControlComplianceResult,
    chunks: list[EvidenceChunk],
    regulatory_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Use LLM to produce letter/spirit-of-law scores and regulatory citations."""
    from app.llm.client import llm_json
    from app.llm.prompts import COMPLIANCE_SYSTEM, COMPLIANCE_USER

    target_artifacts = set(control.target_artifacts)
    target_chunks = [c for c in chunks if c.artifact in target_artifacts]

    evidence_text = "\n".join(
        f"[{c.artifact} | {c.location}] {c.text[:300]}"
        for c in target_chunks[:30]
    )

    reg_lines = []
    for r in regulatory_context[:15]:
        reg_lines.append(
            f"- [{r.get('rule_id', '?')}] {r.get('framework', '?')} "
            f"§{r.get('clause_reference', '?')}: {r.get('rule_text', '')[:200]}"
        )
    reg_text = "\n".join(reg_lines) or "No regulatory context available."

    elements = compliance_result.element_results
    satisfied = sum(1 for e in elements if e.satisfied)
    missing = [
        t for e in elements for t in e.missing_terms
    ]
    negatives = [
        t for e in elements for hit in e.negative_hits for t in hit.matched_terms
    ]

    user_prompt = COMPLIANCE_USER.format(
        control_id=control.id,
        control_name=control.name,
        priority=control.priority,
        mission=control.mission,
        regulatory_context=reg_text,
        evidence_text=evidence_text or "No evidence chunks found for this control.",
        satisfied_count=satisfied,
        total_count=len(elements),
        missing_terms=", ".join(missing[:20]) or "None",
        negative_signals=", ".join(negatives[:10]) or "None",
    )

    try:
        return llm_json(system_prompt=COMPLIANCE_SYSTEM, user_prompt=user_prompt)
    except Exception:
        logger.warning("LLM enrichment failed for %s, using defaults", control.id, exc_info=True)
        return {
            "letter_of_law_score": int(satisfied / max(len(elements), 1) * 100),
            "spirit_of_law_score": int(satisfied / max(len(elements), 1) * 100),
            "compliance_effort_score": int(satisfied / max(len(elements), 1) * 100),
            "reasoning": "LLM unavailable — scores derived from term matching only.",
            "key_findings": [],
            "gaps_identified": [e.reviewer_gap for e in elements if not e.satisfied],
            "regulatory_citations": [],
        }
