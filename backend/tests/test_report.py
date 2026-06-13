from fastapi.testclient import TestClient

from app.agents.report import DISCLAIMER
from app.main import app
from app.models.analysis import AnalysisResponse, ControlReportResult
from app.services.analysis_service import DEMO_REQUEST_ID, analyze_demo_evidence


EXPECTED_STATUSES = {
    "FT-IAM-01": "Needs Prep",
    "FT-IAM-02": "Needs Prep",
    "FT-DPDP-01": "Partial",
    "FT-DPDP-02": "Ready",
    "FT-VAPT-01": "Needs Prep",
    "FT-LOG-01": "Partial",
    "FT-IR-01": "Ready",
}


def _control(response: AnalysisResponse, control_id: str) -> ControlReportResult:
    return next(control for control in response.controls if control.id == control_id)


def test_report_summary_counts_and_top_questions() -> None:
    response = analyze_demo_evidence()

    assert response.request_id == DEMO_REQUEST_ID
    assert response.uploaded_filename == "rakshak-demo-evidence.zip"
    assert response.summary.total_controls == 7
    assert response.summary.ready_count == 2
    assert response.summary.partial_count == 2
    assert response.summary.needs_prep_count == 3
    assert response.summary.total_gap_count == 6
    assert response.summary.top_auditor_questions == [
        "Why is an active developer account present with MFA disabled?",
        "Can you show evidence that privileged service accounts and database admin roles were reviewed separately from normal employee access?",
        "Why is CVE-2026-3089 still unpatched 13 days after detection?",
    ]
    assert response.disclaimer == DISCLAIMER


def test_report_preserves_current_control_status_story() -> None:
    response = analyze_demo_evidence()

    assert {control.id: control.status for control in response.controls} == EXPECTED_STATUSES


def test_report_includes_artifacts_and_control_level_provenance() -> None:
    response = analyze_demo_evidence()
    mfa = _control(response, "FT-IAM-01")

    assert len(response.artifacts) == 8
    assert response.artifacts[0].name == "iam-users.csv"
    assert response.artifacts[0].chunk_count == 4

    assert mfa.artifact == "iam-users.csv"
    assert mfa.reasoning
    assert mfa.reviewer_question
    assert mfa.suggestion
    assert mfa.risk_summary
    assert mfa.evidence_found
    assert mfa.gaps == ["At least one active account lacks MFA evidence."]
    assert "iam-users.csv" in mfa.provenance
    assert "hash" in mfa.provenance
    assert mfa.confidence_rationale


def test_report_evidence_found_excludes_raw_excerpts() -> None:
    response = analyze_demo_evidence()
    serialized = response.model_dump()

    assert "excerpt" not in str(serialized)
    assert all(
        set(evidence.keys()) == {"claim", "artifact", "location", "hash"}
        for control in serialized["controls"]
        for evidence in control["evidence_found"]
    )


def test_report_agent_trace_is_safe_summary_only() -> None:
    response = analyze_demo_evidence()

    assert [entry.agent for entry in response.agent_trace] == [
        "evidence_agent.extract",
        "compliance_agent.map",
        "llm_enrichment.run",
        "risk_agent.score",
        "auditor_agent.questions",
        "report_agent.assemble",
    ]

    trace_text = " ".join(
        f"{entry.agent} {entry.status} {entry.summary}"
        for entry in response.agent_trace
    )
    assert "dev_priya" not in trace_text
    assert "CUST-3088" not in trace_text
    assert "fin-admin@fintech.co.in" not in trace_text


def test_demo_golden_endpoint_returns_analysis_response() -> None:
    client = TestClient(app)

    response = client.get("/demo/golden")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == DEMO_REQUEST_ID
    assert body["summary"]["total_controls"] == 7
    assert body["summary"]["needs_prep_count"] == 3
    assert {control["id"]: control["status"] for control in body["controls"]} == EXPECTED_STATUSES
