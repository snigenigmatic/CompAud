from pathlib import Path

from app.agents.auditor import prepare_auditor_output
from app.agents.compliance import evaluate_compliance
from app.agents.evidence import parse_evidence_upload
from app.agents.risk import assess_risk
from app.models.auditor import AuditorEvaluation, ControlAuditorResult
from app.services.control_catalog_service import load_control_requirements


REPO_ROOT = Path(__file__).resolve().parents[2]


def _demo_auditor_evaluation() -> AuditorEvaluation:
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
    risk = assess_risk(controls=controls, compliance=compliance)
    return prepare_auditor_output(
        controls=controls,
        compliance=compliance,
        risk=risk,
    )


def _control(
    evaluation: AuditorEvaluation,
    control_id: str,
) -> ControlAuditorResult:
    return next(
        result for result in evaluation.control_results if result.control_id == control_id
    )


def test_auditor_agent_evaluates_all_current_controls() -> None:
    evaluation = _demo_auditor_evaluation()

    assert [result.control_id for result in evaluation.control_results] == [
        "FT-IAM-01",
        "FT-IAM-02",
        "FT-DPDP-01",
        "FT-DPDP-02",
        "FT-VAPT-01",
        "FT-LOG-01",
        "FT-IR-01",
    ]


def test_mfa_auditor_guidance_is_actionable() -> None:
    evaluation = _demo_auditor_evaluation()
    result = _control(evaluation, "FT-IAM-01")

    assert (
        result.reviewer_question
        == "Why is an active developer account present with MFA disabled?"
    )
    assert result.suggestion == (
        "Enable MFA for dev_priya or upload an approved exception with "
        "compensating controls and expiry date."
    )
    assert result.risk_summary == (
        "One active developer account lacks MFA, creating a direct audit gap "
        "for production access readiness."
    )
    assert result.agent_plan[0] == "Load FT-IAM-01 requirements."
    assert result.tool_trace[0].tool == "parse_csv"
    assert result.tool_trace[0].input == "iam-users.csv"


def test_ready_encryption_control_uses_cardholder_data_question() -> None:
    evaluation = _demo_auditor_evaluation()
    result = _control(evaluation, "FT-DPDP-02")

    assert result.reviewer_question == (
        "Can you prove raw PAN is not stored and CVV/CVC is never retained "
        "after authorization?"
    )
    assert result.risk_summary == (
        "Encryption and cardholder data protection policy evidence is "
        "review-ready for the demo scope."
    )
    assert result.tool_trace[1].result == (
        "no gaps; preserve evidence and strengthen with execution proof"
    )


def test_vapt_auditor_guidance_prioritizes_failed_asv_and_patch_evidence() -> None:
    evaluation = _demo_auditor_evaluation()
    result = _control(evaluation, "FT-VAPT-01")

    assert result.reviewer_question == (
        "Why is CVE-2026-3089 still unpatched 13 days after detection?"
    )
    assert result.suggestion == (
        "Upload a patch ticket, exception approval, compensating control, "
        "updated retest report, and passing quarterly ASV scan after remediation."
    )
    assert result.risk_summary == (
        "A high-risk vulnerability is active beyond the demo SLA and has caused "
        "the quarterly PCI-DSS ASV scan to fail."
    )
    assert result.tool_trace[1].result == (
        "Quarterly ASV scan evidence is missing or failed."
    )


def test_auditor_tool_trace_does_not_include_raw_evidence_excerpts() -> None:
    evaluation = _demo_auditor_evaluation()
    all_trace_text = " ".join(
        f"{entry.tool} {entry.input} {entry.result}"
        for result in evaluation.control_results
        for entry in result.tool_trace
    )

    assert "dev_priya" not in all_trace_text
    assert "CUST-3088" not in all_trace_text
    assert "fin-admin@fintech.co.in" not in all_trace_text
