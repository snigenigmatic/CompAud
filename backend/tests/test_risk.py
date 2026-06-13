from pathlib import Path

from app.agents.compliance import evaluate_compliance
from app.agents.evidence import parse_evidence_upload
from app.agents.risk import assess_risk
from app.models.risk import ControlRiskResult, RiskEvaluation
from app.services.control_catalog_service import load_control_requirements


REPO_ROOT = Path(__file__).resolve().parents[2]


def _demo_risk_evaluation() -> RiskEvaluation:
    controls = load_control_requirements()
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"
    evidence_package = parse_evidence_upload(
        "rakshak-demo-evidence.zip",
        evidence_zip.read_bytes(),
    )
    compliance = evaluate_compliance(
        controls=controls,
        chunks=evidence_package.chunks,
    )
    return assess_risk(controls=controls, compliance=compliance)


def _control(evaluation: RiskEvaluation, control_id: str) -> ControlRiskResult:
    return next(
        result for result in evaluation.control_results if result.control_id == control_id
    )


def test_risk_agent_matches_demo_status_story() -> None:
    evaluation = _demo_risk_evaluation()

    assert {
        result.control_id: result.status for result in evaluation.control_results
    } == {
        "FT-IAM-01": "Needs Prep",
        "FT-IAM-02": "Needs Prep",
        "FT-DPDP-01": "Partial",
        "FT-DPDP-02": "Ready",
        "FT-VAPT-01": "Needs Prep",
        "FT-LOG-01": "Partial",
        "FT-IR-01": "Ready",
    }


def test_mfa_risk_is_needs_prep_with_gap_and_confidence() -> None:
    evaluation = _demo_risk_evaluation()
    result = _control(evaluation, "FT-IAM-01")

    assert result.status == "Needs Prep"
    assert result.total_elements == 3
    assert result.satisfied_elements == 2
    assert result.critical_elements == 3
    assert result.satisfied_critical_elements == 2
    assert result.negative_hit_count == 1
    assert result.confidence == 0.71
    assert result.gaps == ["At least one active account lacks MFA evidence."]
    assert "2/3 critical elements" in result.confidence_rationale


def test_privileged_access_missing_categories_are_needs_prep() -> None:
    evaluation = _demo_risk_evaluation()
    result = _control(evaluation, "FT-IAM-02")

    assert result.status == "Needs Prep"
    assert result.satisfied_critical_elements == 1
    assert result.critical_elements == 2
    assert result.satisfied_elements == 2
    assert result.confidence == 0.6
    assert result.gaps == [
        "No cited evidence proves service accounts or database admin roles were reviewed."
    ]


def test_consent_negative_signal_stays_partial_for_demo() -> None:
    evaluation = _demo_risk_evaluation()
    result = _control(evaluation, "FT-DPDP-01")

    assert result.status == "Partial"
    assert result.satisfied_critical_elements == 2
    assert result.critical_elements == 3
    assert result.negative_hit_count == 1
    assert result.confidence == 0.69
    assert result.gaps == [
        "Processing evidence indicates activity after consent revocation and needs investigation."
    ]


def test_ready_controls_have_no_gaps() -> None:
    evaluation = _demo_risk_evaluation()

    encryption = _control(evaluation, "FT-DPDP-02")
    incident_response = _control(evaluation, "FT-IR-01")

    assert encryption.status == "Ready"
    assert encryption.gaps == []
    assert encryption.confidence == 0.93

    assert incident_response.status == "Ready"
    assert incident_response.gaps == []
    assert incident_response.confidence == 0.93


def test_vapt_failed_asv_is_needs_prep() -> None:
    evaluation = _demo_risk_evaluation()
    result = _control(evaluation, "FT-VAPT-01")

    assert result.status == "Needs Prep"
    assert result.satisfied_critical_elements == 2
    assert result.critical_elements == 4
    assert result.negative_hit_count == 4
    assert result.confidence == 0.58
    assert result.gaps == [
        "Quarterly ASV scan evidence is missing or failed.",
        "A high-risk vulnerability remains unpatched beyond the demo SLA and causes ASV failure.",
    ]


def test_log_retention_risk_is_partial_not_needs_prep() -> None:
    evaluation = _demo_risk_evaluation()
    result = _control(evaluation, "FT-LOG-01")

    assert result.status == "Partial"
    assert result.satisfied_critical_elements == 2
    assert result.critical_elements == 3
    assert result.negative_hit_count == 1
    assert result.confidence == 0.61
    assert result.gaps == [
        "Logging evidence shows active logs, but retention proof does not meet 180 days."
    ]
