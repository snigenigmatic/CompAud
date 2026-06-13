from app.models.compliance import (
    ComplianceEvaluation,
    ControlComplianceResult,
    EvidenceElementResult,
)
from app.models.controls import ControlRequirement
from app.models.risk import ControlRiskResult, RiskEvaluation


SERIOUS_NEGATIVE_ELEMENTS = {
    ("FT-IAM-01", "mfa_enabled_all_active"),
    ("FT-VAPT-01", "asv_scan_status"),
    ("FT-VAPT-01", "sla_compliance"),
}


def assess_risk(
    controls: list[ControlRequirement],
    compliance: ComplianceEvaluation,
) -> RiskEvaluation:
    control_by_id = {control.id: control for control in controls}

    return RiskEvaluation(
        control_results=[
            assess_control_risk(
                control=control_by_id[compliance_result.control_id],
                compliance_result=compliance_result,
            )
            for compliance_result in compliance.control_results
        ]
    )


def assess_control_risk(
    control: ControlRequirement,
    compliance_result: ControlComplianceResult,
) -> ControlRiskResult:
    elements = compliance_result.element_results
    critical_elements = [element for element in elements if element.critical]
    unsatisfied_elements = [element for element in elements if not element.satisfied]
    unsatisfied_critical_elements = [
        element for element in critical_elements if not element.satisfied
    ]
    critical_missing_elements = [
        element for element in unsatisfied_critical_elements if element.missing_terms
    ]
    serious_negative_elements = [
        element
        for element in elements
        if element.negative_hits
        and (compliance_result.control_id, element.element_id)
        in SERIOUS_NEGATIVE_ELEMENTS
    ]

    status = _status_for_control(
        control=control,
        unsatisfied_elements=unsatisfied_elements,
        critical_missing_elements=critical_missing_elements,
        serious_negative_elements=serious_negative_elements,
    )
    gaps = _gaps_for_elements(unsatisfied_elements)
    confidence = _confidence_for_control(
        status=status,
        elements=elements,
        critical_elements=critical_elements,
        critical_missing_elements=critical_missing_elements,
        serious_negative_elements=serious_negative_elements,
    )

    return ControlRiskResult(
        control_id=control.id,
        control_name=control.name,
        priority=control.priority,
        status=status,
        confidence=confidence,
        total_elements=len(elements),
        satisfied_elements=sum(1 for element in elements if element.satisfied),
        critical_elements=len(critical_elements),
        satisfied_critical_elements=sum(
            1 for element in critical_elements if element.satisfied
        ),
        negative_hit_count=sum(len(element.negative_hits) for element in elements),
        gaps=gaps,
        confidence_rationale=_confidence_rationale(
            status=status,
            confidence=confidence,
            gaps=gaps,
            elements=elements,
            critical_elements=critical_elements,
        ),
    )


def _status_for_control(
    control: ControlRequirement,
    unsatisfied_elements: list[EvidenceElementResult],
    critical_missing_elements: list[EvidenceElementResult],
    serious_negative_elements: list[EvidenceElementResult],
) -> str:
    if serious_negative_elements:
        return "Needs Prep"

    if control.priority in {"P1", "P2"} and critical_missing_elements:
        return "Needs Prep"

    if unsatisfied_elements:
        return "Partial"

    return "Ready"


def _gaps_for_elements(elements: list[EvidenceElementResult]) -> list[str]:
    gaps: list[str] = []
    for element in elements:
        if element.reviewer_gap not in gaps:
            gaps.append(element.reviewer_gap)
    return gaps


def _confidence_for_control(
    status: str,
    elements: list[EvidenceElementResult],
    critical_elements: list[EvidenceElementResult],
    critical_missing_elements: list[EvidenceElementResult],
    serious_negative_elements: list[EvidenceElementResult],
) -> float:
    if not elements:
        return 0.25

    satisfied_elements = sum(1 for element in elements if element.satisfied)
    satisfied_critical = sum(1 for element in critical_elements if element.satisfied)
    critical_coverage = (
        satisfied_critical / len(critical_elements) if critical_elements else 1.0
    )
    total_coverage = satisfied_elements / len(elements)
    negative_element_count = sum(1 for element in elements if element.negative_hits)
    non_serious_negative_count = max(
        0,
        negative_element_count - len(serious_negative_elements),
    )

    confidence = 0.35
    confidence += 0.35 * critical_coverage
    confidence += 0.20 * total_coverage
    confidence -= 0.08 * len(critical_missing_elements)
    confidence -= 0.03 * len(serious_negative_elements)
    confidence -= 0.03 * non_serious_negative_count

    if status == "Ready":
        confidence += 0.03
    elif status == "Needs Prep":
        confidence += 0.02

    return round(min(0.95, max(0.25, confidence)), 2)


def _confidence_rationale(
    status: str,
    confidence: float,
    gaps: list[str],
    elements: list[EvidenceElementResult],
    critical_elements: list[EvidenceElementResult],
) -> str:
    satisfied_elements = sum(1 for element in elements if element.satisfied)
    satisfied_critical = sum(1 for element in critical_elements if element.satisfied)

    if status == "Ready":
        return (
            f"{satisfied_elements}/{len(elements)} evidence elements and "
            f"{satisfied_critical}/{len(critical_elements)} critical elements are "
            f"supported by cited evidence; confidence is {confidence:.2f}."
        )

    return (
        f"{satisfied_elements}/{len(elements)} evidence elements and "
        f"{satisfied_critical}/{len(critical_elements)} critical elements are "
        f"supported; {len(gaps)} gap(s) remain, so status is {status} with "
        f"confidence {confidence:.2f}."
    )
