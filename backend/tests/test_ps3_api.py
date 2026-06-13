import os

import pytest
from fastapi.testclient import TestClient

# Keep API tests deterministic/offline: no LLM narration.
os.environ.setdefault("PS3_LLM_NARRATIVES", "false")

from app.main import app

client = TestClient(app)


def test_get_requirements_returns_nine():
    response = client.get("/ps3/requirements")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 9
    assert len(body["requirements"]) == 9


def test_get_single_requirement():
    response = client.get("/ps3/requirements/POL-ENC-001-R1")
    assert response.status_code == 200
    assert response.json()["requirements"][0]["id"] == "POL-ENC-001-R1"


def test_get_unknown_requirement_404():
    response = client.get("/ps3/requirements/NOPE")
    assert response.status_code == 404


@pytest.mark.slow
def test_analyze_returns_valid_envelope():
    response = client.post("/ps3/analyze")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_requirements"] == 9
    assert len(body["requirements"]) == 9
    assert "agent_trace" in body


@pytest.mark.slow
def test_report_pdf_endpoint():
    response = client.get("/ps3/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
