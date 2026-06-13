from fastapi.testclient import TestClient

from app.main import app
from app.services.control_catalog_service import (
    CONTROL_REQUIREMENTS_SOURCE,
    load_control_requirements,
)


EXPECTED_CONTROL_IDS = [
    "FT-IAM-01",
    "FT-IAM-02",
    "FT-DPDP-01",
    "FT-DPDP-02",
    "FT-VAPT-01",
    "FT-LOG-01",
    "FT-IR-01",
]


def test_control_catalog_loads_current_controls() -> None:
    controls = load_control_requirements()

    assert [control.id for control in controls] == EXPECTED_CONTROL_IDS
    assert all(control.target_artifacts for control in controls)
    assert all(control.required_evidence_elements for control in controls)
    assert all(control.common_reviewer_questions for control in controls)


def test_controls_endpoint_returns_valid_catalog() -> None:
    client = TestClient(app)

    response = client.get("/controls")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == CONTROL_REQUIREMENTS_SOURCE
    assert body["count"] == 7
    assert [control["id"] for control in body["controls"]] == EXPECTED_CONTROL_IDS

    mfa_control = body["controls"][0]
    assert mfa_control["name"] == "Multi-Factor Authentication"
    assert mfa_control["required_evidence_elements"][0]["critical"] is True
    assert mfa_control["required_evidence_elements"][0]["negative_terms"] == []
