from pathlib import Path

from app.agents.analysis_graph import graph_node_names, run_analysis_graph
from app.services.analysis_service import analyze_evidence_bytes


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_STATUSES = {
    "FT-IAM-01": "Needs Prep",
    "FT-IAM-02": "Needs Prep",
    "FT-DPDP-01": "Partial",
    "FT-DPDP-02": "Ready",
    "FT-VAPT-01": "Needs Prep",
    "FT-LOG-01": "Partial",
    "FT-IR-01": "Ready",
}


def test_analysis_graph_has_expected_agent_order() -> None:
    assert graph_node_names() == [
        "load_controls",
        "evidence_agent",
        "compliance_agent",
        "llm_enrichment",
        "risk_agent",
        "auditor_agent",
        "report_agent",
    ]


def test_analysis_graph_returns_frontend_ready_response() -> None:
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"

    response = run_analysis_graph(
        filename="rakshak-demo-evidence.zip",
        content=evidence_zip.read_bytes(),
        request_id="graph-test",
    )

    assert response.request_id == "graph-test"
    assert response.summary.total_controls == 7
    assert response.summary.needs_prep_count == 3
    assert {control.id: control.status for control in response.controls} == EXPECTED_STATUSES


def test_public_analysis_entrypoint_uses_graph_response_shape() -> None:
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"

    response = analyze_evidence_bytes(
        filename="rakshak-demo-evidence.zip",
        content=evidence_zip.read_bytes(),
        request_id="entrypoint-test",
    )

    assert response.request_id == "entrypoint-test"
    assert response.agent_trace[-1].agent == "report_agent.assemble"
    assert response.disclaimer.startswith("CompAud is an audit preparation assistant.")
