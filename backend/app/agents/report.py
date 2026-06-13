from typing import Any

from app.models.analysis import (
    AgentTraceEntry,
    AnalysisResponse,
    AnalysisSummary,
    ComplianceScores,
    ControlEvidenceFound,
    ControlReportResult,
)
from app.models.auditor import AuditorEvaluation, ControlAuditorResult
from app.models.compliance import (
    ComplianceEvaluation,
    ControlComplianceResult,
    EvidenceElementResult,
)
from app.models.controls import ControlRequirement
from app.models.evidence import EvidenceCitation, EvidencePackage
from app.models.risk import ControlRiskResult, RiskEvaluation


DISCLAIMER = (
    "CompAud is an audit preparation assistant. It is not legal advice or an "
    "official compliance assessment."
)

STATUS_SORT_ORDER = {
    "Needs Prep": 0,
    "Partial": 1,
    "Ready": 2,
}

PRIORITY_SORT_ORDER = {
    "P1": 0,
    "P2": 1,
    "P3": 2,
}

MAX_EVIDENCE_FOUND_PER_CONTROL = 8


def build_analysis_report(
    request_id: str,
    evidence_package: EvidencePackage,
    controls: list[ControlRequirement],
    compliance: ComplianceEvaluation,
    risk: RiskEvaluation,
    auditor: AuditorEvaluation,
    llm_enrichments: dict[str, dict[str, Any]] | None = None,
) -> AnalysisResponse:
    enrichments = llm_enrichments or {}
    control_by_id = {control.id: control for control in controls}
    compliance_by_id = {
        result.control_id: result for result in compliance.control_results
    }
    auditor_by_id = {result.control_id: result for result in auditor.control_results}

    control_reports = [
        _control_report(
            control=control_by_id[risk_result.control_id],
            compliance_result=compliance_by_id[risk_result.control_id],
            risk_result=risk_result,
            auditor_result=auditor_by_id[risk_result.control_id],
            llm_enrichment=enrichments.get(risk_result.control_id),
        )
        for risk_result in risk.control_results
    ]

    return AnalysisResponse(
        request_id=request_id,
        uploaded_filename=evidence_package.uploaded_filename,
        summary=_summary(
            risk_results=risk.control_results,
            auditor_results=auditor.control_results,
        ),
        artifacts=evidence_package.artifacts,
        controls=control_reports,
        agent_trace=_agent_trace(
            evidence_package=evidence_package,
            control_count=len(controls),
            risk_results=risk.control_results,
        ),
        disclaimer=DISCLAIMER,
    )


def _control_report(
    control: ControlRequirement,
    compliance_result: ControlComplianceResult,
    risk_result: ControlRiskResult,
    auditor_result: ControlAuditorResult,
    llm_enrichment: dict[str, Any] | None = None,
) -> ControlReportResult:
    evidence_found = _evidence_found(compliance_result.element_results)
    enrichment = llm_enrichment or {}

    scores = ComplianceScores(
        letter_of_law=enrichment.get("letter_of_law_score", 0),
        spirit_of_law=enrichment.get("spirit_of_law_score", 0),
        compliance_effort=enrichment.get("compliance_effort_score", 0),
    )

    return ControlReportResult(
        id=control.id,
        name=control.name,
        priority=control.priority,
        status=risk_result.status,
        confidence=risk_result.confidence,
        regulation_story=control.regulation_story,
        artifact=", ".join(control.target_artifacts),
        reasoning=_reasoning(compliance_result.element_results),
        reviewer_question=auditor_result.reviewer_question,
        suggestion=auditor_result.suggestion,
        provenance=_provenance(evidence_found),
        risk_summary=auditor_result.risk_summary,
        evidence_found=evidence_found,
        gaps=risk_result.gaps,
        agent_plan=auditor_result.agent_plan,
        tool_trace=auditor_result.tool_trace,
        confidence_rationale=risk_result.confidence_rationale,
        scores=scores,
        llm_reasoning=enrichment.get("reasoning", ""),
        regulatory_citations=enrichment.get("regulatory_citations", []),
    )


def _summary(
    risk_results: list[ControlRiskResult],
    auditor_results: list[ControlAuditorResult],
) -> AnalysisSummary:
    auditor_by_id = {result.control_id: result for result in auditor_results}
    ranked_risk_results = sorted(
        enumerate(risk_results),
        key=lambda item: (
            STATUS_SORT_ORDER.get(item[1].status, 99),
            PRIORITY_SORT_ORDER.get(item[1].priority, 99),
            item[0],
        ),
    )

    top_questions = [
        auditor_by_id[result.control_id].reviewer_question
        for _, result in ranked_risk_results
        if result.status != "Ready"
    ][:3]

    return AnalysisSummary(
        total_controls=len(risk_results),
        ready_count=sum(1 for result in risk_results if result.status == "Ready"),
        partial_count=sum(1 for result in risk_results if result.status == "Partial"),
        needs_prep_count=sum(
            1 for result in risk_results if result.status == "Needs Prep"
        ),
        total_gap_count=sum(len(result.gaps) for result in risk_results),
        top_auditor_questions=top_questions,
    )


def _reasoning(elements: list[EvidenceElementResult]) -> list[str]:
    reasoning: list[str] = []
    for element in elements:
        if element.satisfied:
            reasoning.append(f"{element.label} is supported by cited evidence.")
        elif element.negative_hits:
            reasoning.append(f"{element.label} has conflicting evidence: {element.reviewer_gap}")
        else:
            reasoning.append(f"{element.label} is incomplete: {element.reviewer_gap}")

    return reasoning


def _evidence_found(elements: list[EvidenceElementResult]) -> list[ControlEvidenceFound]:
    evidence: list[ControlEvidenceFound] = []
    seen: set[tuple[str, str, str, str]] = set()

    for element in elements:
        for citation in element.citations:
            _append_evidence(
                evidence=evidence,
                seen=seen,
                claim=f"{element.label}: matched {', '.join(citation.matched_terms)}.",
                citation=citation,
            )
        for negative_hit in element.negative_hits:
            _append_evidence(
                evidence=evidence,
                seen=seen,
                claim=(
                    f"{element.label}: negative signal matched "
                    f"{', '.join(negative_hit.matched_terms)}."
                ),
                citation=negative_hit,
            )

    return evidence[:MAX_EVIDENCE_FOUND_PER_CONTROL]


def _append_evidence(
    evidence: list[ControlEvidenceFound],
    seen: set[tuple[str, str, str, str]],
    claim: str,
    citation: EvidenceCitation,
) -> None:
    key = (claim, citation.artifact, citation.location, citation.hash)
    if key in seen:
        return

    evidence.append(
        ControlEvidenceFound(
            claim=claim,
            artifact=citation.artifact,
            location=citation.location,
            hash=citation.hash,
        )
    )
    seen.add(key)


def _provenance(evidence_found: list[ControlEvidenceFound]) -> str:
    if not evidence_found:
        return "No cited evidence."

    return "; ".join(
        f"{evidence.artifact} ({evidence.location}, hash {evidence.hash})"
        for evidence in evidence_found[:3]
    )


def _agent_trace(
    evidence_package: EvidencePackage,
    control_count: int,
    risk_results: list[ControlRiskResult],
) -> list[AgentTraceEntry]:
    gap_count = sum(len(result.gaps) for result in risk_results)

    return [
        AgentTraceEntry(
            agent="evidence_agent.extract",
            status="completed",
            summary=(
                f"{len(evidence_package.artifacts)} artifact(s), "
                f"{len(evidence_package.chunks)} chunk(s)"
            ),
        ),
        AgentTraceEntry(
            agent="compliance_agent.map",
            status="completed",
            summary=f"{control_count} control(s) evaluated",
        ),
        AgentTraceEntry(
            agent="llm_enrichment.run",
            status="completed",
            summary=f"{control_count} control(s) enriched with LLM + knowledge graph",
        ),
        AgentTraceEntry(
            agent="risk_agent.score",
            status="completed",
            summary=f"{gap_count} gap(s) across {control_count} control(s)",
        ),
        AgentTraceEntry(
            agent="auditor_agent.questions",
            status="completed",
            summary=f"{control_count} reviewer question(s) generated by LLM",
        ),
        AgentTraceEntry(
            agent="report_agent.assemble",
            status="completed",
            summary="Analysis response assembled",
        ),
    ]
