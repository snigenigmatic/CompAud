from pathlib import Path

from app.agents.compliance import evaluate_compliance
from app.agents.evidence import parse_evidence_upload
from app.models.compliance import ComplianceEvaluation, ControlComplianceResult
from app.services.control_catalog_service import load_control_requirements


REPO_ROOT = Path(__file__).resolve().parents[2]


def _demo_compliance_evaluation() -> ComplianceEvaluation:
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"
    evidence_package = parse_evidence_upload(
        "rakshak-demo-evidence.zip",
        evidence_zip.read_bytes(),
    )
    return evaluate_compliance(
        controls=load_control_requirements(),
        chunks=evidence_package.chunks,
    )


def _control(
    evaluation: ComplianceEvaluation,
    control_id: str,
) -> ControlComplianceResult:
    return next(
        result for result in evaluation.control_results if result.control_id == control_id
    )


def test_compliance_evaluates_all_current_controls() -> None:
    evaluation = _demo_compliance_evaluation()

    assert [result.control_id for result in evaluation.control_results] == [
        "FT-IAM-01",
        "FT-IAM-02",
        "FT-DPDP-01",
        "FT-DPDP-02",
        "FT-VAPT-01",
        "FT-LOG-01",
        "FT-IR-01",
    ]


def test_mfa_element_is_blocked_by_disabled_active_user() -> None:
    evaluation = _demo_compliance_evaluation()
    iam = _control(evaluation, "FT-IAM-01")
    mfa_element = next(
        result
        for result in iam.element_results
        if result.element_id == "mfa_enabled_all_active"
    )

    assert iam.target_artifacts == ["iam-users.csv"]
    assert iam.target_chunk_count == 4
    assert mfa_element.matched_terms == ["mfa_enabled", "true"]
    assert mfa_element.missing_terms == []
    assert mfa_element.satisfied is False
    assert len(mfa_element.negative_hits) == 1
    assert mfa_element.negative_hits[0].artifact == "iam-users.csv"
    assert mfa_element.negative_hits[0].location == "row 3"
    assert "mfa_enabled=false" in mfa_element.negative_hits[0].matched_terms


def test_privileged_access_review_reports_missing_categories() -> None:
    evaluation = _demo_compliance_evaluation()
    access_review = _control(evaluation, "FT-IAM-02")
    privileged_roles = next(
        result
        for result in access_review.element_results
        if result.element_id == "privileged_roles_reviewed"
    )

    assert privileged_roles.satisfied is False
    assert privileged_roles.matched_terms == ["FinanceAdmin"]
    assert privileged_roles.missing_terms == [
        "ProductionAdmin",
        "DatabaseAdmin",
        "ServiceAccount",
        "privileged",
    ]
    assert privileged_roles.negative_hits == []


def test_revocation_evidence_accepts_alternative_terms() -> None:
    evaluation = _demo_compliance_evaluation()
    access_review = _control(evaluation, "FT-IAM-02")
    revocation = next(
        result
        for result in access_review.element_results
        if result.element_id == "revocation_evidence"
    )

    assert revocation.satisfied is True
    assert revocation.missing_terms == []
    assert revocation.matched_terms == ["Revoked", "resigned"]


def test_encryption_control_elements_are_satisfied() -> None:
    evaluation = _demo_compliance_evaluation()
    encryption = _control(evaluation, "FT-DPDP-02")

    assert encryption.target_artifacts == ["dpdp-encryption-policy.txt"]
    assert all(result.satisfied for result in encryption.element_results)
    assert all(not result.negative_hits for result in encryption.element_results)


def test_vapt_asv_status_is_blocked_by_failed_scan() -> None:
    evaluation = _demo_compliance_evaluation()
    vapt = _control(evaluation, "FT-VAPT-01")
    asv_status = next(
        result
        for result in vapt.element_results
        if result.element_id == "asv_scan_status"
    )

    assert asv_status.satisfied is False
    assert asv_status.missing_terms == []
    assert asv_status.negative_hits
    assert asv_status.negative_hits[0].artifact == "vapt-summary.txt"
    assert "Scan Status: FAILED" in asv_status.negative_hits[0].matched_terms


def test_log_retention_is_missing_180_days_and_hits_90_day_negative() -> None:
    evaluation = _demo_compliance_evaluation()
    logging = _control(evaluation, "FT-LOG-01")
    retention = next(
        result
        for result in logging.element_results
        if result.element_id == "retention_180_days"
    )

    assert retention.satisfied is False
    assert retention.matched_terms == []
    assert retention.missing_terms == ["retention_days=180", "180 days", "six months"]
    assert len(retention.negative_hits) == 1
    assert retention.negative_hits[0].location == "line 1"
    assert retention.negative_hits[0].matched_terms == ["retention_days=90"]
