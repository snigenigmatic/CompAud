from app.agents.ps3_policy_parser import parse_policy_text, sla_days_for_frequency
from app.config import PS3_POLICY_DOCUMENTS_PATH
from app.services.ps3_requirement_service import load_requirements

# Ground truth from policy_documents.txt (3 policies, 9 requirements).
EXPECTED = {
    "POL-ENC-001-R1": ("Monthly", 30, {"GDPR", "NIST", "PCI-DSS"}),
    "POL-ENC-001-R2": ("Quarterly", 90, {"NIST", "ISO27001"}),
    "POL-ENC-001-R3": ("Continuous", 1, {"GDPR", "NIST"}),
    "POL-AC-001-R1": ("Daily", 1, {"NIST", "CIS"}),
    "POL-AC-001-R2": ("Quarterly", 90, {"NIST", "SOX"}),
    "POL-AC-001-R3": ("Monthly", 30, {"NIST", "CIS"}),
    "POL-AUD-001-R1": ("Daily", 1, {"GDPR", "NIST", "SOX"}),
    "POL-AUD-001-R2": ("Monthly", 30, {"NIST", "PCI-DSS"}),
    "POL-AUD-001-R3": ("Weekly", 7, {"NIST", "ISO27001"}),
}


def _parsed():
    return parse_policy_text(PS3_POLICY_DOCUMENTS_PATH.read_text(encoding="utf-8"))


def test_parses_exactly_nine_requirements():
    requirements = _parsed()
    assert len(requirements) == 9
    assert {r.id for r in requirements} == set(EXPECTED)


def test_audit_frequency_frameworks_and_sla_match_ground_truth():
    by_id = {r.id: r for r in _parsed()}
    for rid, (frequency, sla, frameworks) in EXPECTED.items():
        req = by_id[rid]
        assert req.audit_frequency == frequency, rid
        assert req.freshness_sla_days == sla, rid
        assert set(req.frameworks) == frameworks, rid


def test_labeled_fields_populated():
    by_id = {r.id: r for r in _parsed()}
    assert by_id["POL-ENC-001-R1"].responsible == "Infrastructure Security"
    assert by_id["POL-ENC-001-R1"].evidence_source == "AWS KMS Configuration, Database Settings"
    # POL-ENC-001-R2 uses a lowercase "scope:" label — case-insensitive capture must work.
    assert by_id["POL-ENC-001-R2"].scope == "All encryption keys"
    assert "AES-256" in by_id["POL-ENC-001-R1"].text


def test_sla_mapping():
    assert sla_days_for_frequency("Continuous") == 1
    assert sla_days_for_frequency("Daily") == 1
    assert sla_days_for_frequency("Weekly") == 7
    assert sla_days_for_frequency("Monthly") == 30
    assert sla_days_for_frequency("Quarterly") == 90
    assert sla_days_for_frequency("Unknown") == 90  # fallback


def test_service_loads_requirements():
    requirements = load_requirements()
    assert len(requirements) == 9
    assert all(r.policy_id and r.text for r in requirements)
