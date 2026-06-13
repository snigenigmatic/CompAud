from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.agents.evidence import (
    UnsafeEvidenceArchiveError,
    UnsupportedEvidenceTypeError,
    parse_evidence_upload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_ARTIFACTS = [
    "iam-users.csv",
    "access-review.csv",
    "dpdp-consent-records.csv",
    "dpdp-processing-events.log",
    "cloud-logging-export.log",
    "incident-response-policy.txt",
    "vapt-summary.txt",
    "dpdp-encryption-policy.txt",
]


def test_parse_demo_evidence_zip_preserves_artifacts_and_chunks() -> None:
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"

    package = parse_evidence_upload(
        "rakshak-demo-evidence.zip",
        evidence_zip.read_bytes(),
    )

    assert package.uploaded_filename == "rakshak-demo-evidence.zip"
    assert [artifact.name for artifact in package.artifacts] == EXPECTED_ARTIFACTS
    assert [artifact.chunk_count for artifact in package.artifacts] == [
        4,
        3,
        3,
        3,
        4,
        14,
        20,
        15,
    ]
    assert len(package.chunks) == 66


def test_parse_csv_chunks_include_stable_provenance_and_fields() -> None:
    evidence_zip = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"
    package = parse_evidence_upload(
        "rakshak-demo-evidence.zip",
        evidence_zip.read_bytes(),
    )

    iam_gap = next(
        chunk
        for chunk in package.chunks
        if chunk.artifact == "iam-users.csv" and chunk.location == "row 3"
    )

    assert iam_gap.parsed_fields["username"] == "dev_priya"
    assert iam_gap.parsed_fields["role"] == "Developer"
    assert iam_gap.parsed_fields["mfa_enabled"] == "false"
    assert "mfa_enabled=false" in iam_gap.text
    assert iam_gap.normalized_text == iam_gap.text.lower()
    assert len(iam_gap.hash) == 12


def test_parse_log_chunks_keep_original_line_numbers() -> None:
    content = (
        REPO_ROOT / "docs" / "sample-evidence" / "dpdp-processing-events.log"
    ).read_bytes()

    package = parse_evidence_upload("dpdp-processing-events.log", content)

    assert [chunk.location for chunk in package.chunks] == ["line 1", "line 2", "line 3"]
    assert "after_revocation=true" in package.chunks[2].text


def test_parse_json_upload_creates_json_chunks() -> None:
    package = parse_evidence_upload(
        "events.json",
        b'[{"event":"login","status":"ok"},{"event":"logout","status":"ok"}]',
    )

    assert [chunk.location for chunk in package.chunks] == ["item 1", "item 2"]
    assert package.chunks[0].parsed_fields == {"event": "login", "status": "ok"}


def test_rejects_zip_path_traversal() -> None:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("../evil.txt", "do not parse")

    with pytest.raises(UnsafeEvidenceArchiveError):
        parse_evidence_upload("unsafe.zip", archive_bytes.getvalue())


def test_rejects_unsupported_zip_member_type() -> None:
    archive_bytes = BytesIO()
    with ZipFile(archive_bytes, "w") as archive:
        archive.writestr("README.md", "# unsupported")

    with pytest.raises(UnsupportedEvidenceTypeError):
        parse_evidence_upload("unsupported.zip", archive_bytes.getvalue())
