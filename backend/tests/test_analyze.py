from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import app


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


def _sse_event_names(stream_text: str) -> list[str]:
    return [
        line.removeprefix("event: ")
        for line in stream_text.splitlines()
        if line.startswith("event: ")
    ]


def test_analyze_demo_zip_upload_returns_analysis_response() -> None:
    client = TestClient(app)
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"

    response = client.post(
        "/analyze",
        files={
            "file": (
                "rakshak-demo-evidence.zip",
                evidence_zip.read_bytes(),
                "application/zip",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["request_id"])
    assert body["request_id"] != "demo-golden"
    assert body["uploaded_filename"] == "rakshak-demo-evidence.zip"
    assert body["summary"]["total_controls"] == 7
    assert body["summary"]["ready_count"] == 2
    assert body["summary"]["partial_count"] == 2
    assert body["summary"]["needs_prep_count"] == 3
    assert {control["id"]: control["status"] for control in body["controls"]} == EXPECTED_STATUSES


def test_demo_golden_stream_returns_progress_and_final_response() -> None:
    client = TestClient(app)

    response = client.get("/demo/golden/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_event_names(response.text)
    assert events[0] == "analysis.started"
    assert "analysis.progress" in events
    assert events[-1] == "analysis.complete"
    assert '"step":"llm_enrichment"' in response.text
    assert '"request_id":"demo-golden"' in response.text


def test_analyze_stream_accepts_demo_zip_upload() -> None:
    client = TestClient(app)
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"

    response = client.post(
        "/analyze/stream",
        files={
            "file": (
                "rakshak-demo-evidence.zip",
                evidence_zip.read_bytes(),
                "application/zip",
            )
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_event_names(response.text)
    assert events[0] == "analysis.started"
    assert events[-1] == "analysis.complete"
    assert '"uploaded_filename":"rakshak-demo-evidence.zip"' in response.text


def test_analyze_accepts_single_csv_upload() -> None:
    client = TestClient(app)
    iam_users = REPO_ROOT / "docs" / "sample-evidence" / "iam-users.csv"

    response = client.post(
        "/analyze",
        files={
            "file": (
                "iam-users.csv",
                iam_users.read_bytes(),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["request_id"])
    assert body["uploaded_filename"] == "iam-users.csv"
    assert body["artifacts"] == [
        {"name": "iam-users.csv", "extension": ".csv", "chunk_count": 4}
    ]
    assert len(body["controls"]) == 7


def test_analyze_rejects_empty_upload() -> None:
    client = TestClient(app)

    response = client.post(
        "/analyze",
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "EMPTY_UPLOAD",
            "message": "Uploaded evidence file is empty.",
        }
    }


def test_analyze_rejects_unsupported_file_type() -> None:
    client = TestClient(app)

    response = client.post(
        "/analyze",
        files={"file": ("README.md", b"# unsupported", "text/markdown")},
    )

    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_EVIDENCE_TYPE"
    assert "Unsupported evidence file type" in body["error"]["message"]


def test_analyze_rejects_unsafe_zip_path() -> None:
    client = TestClient(app)
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("../evil.txt", "do not parse")

    response = client.post(
        "/analyze",
        files={"file": ("unsafe.zip", archive_bytes.getvalue(), "application/zip")},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "UNSAFE_ARCHIVE_PATH"
    assert "Unsafe ZIP member path" in body["error"]["message"]
