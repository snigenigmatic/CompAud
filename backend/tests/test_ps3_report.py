import re

from app.agents.ps3_linker import LinkResult
from app.agents.ps3_pdf import render_report_pdf
from app.agents.ps3_report import build_ps3_report
from app.agents.ps3_quality import evaluate_quality
from app.models.ps3 import Evidence, LinkedEvidence, Requirement

EVD_RE = re.compile(r"(EVD\d+|CT-\S+)")


def _requirement(rid="POL-ENC-001-R1", sla=30):
    return Requirement(
        id=rid,
        policy_id="POL-ENC-001",
        policy_name="Encryption",
        text="Data at rest must be encrypted",
        raw_text="Data at rest must be encrypted",
        evidence_source="AWS KMS Configuration",
        audit_frequency="Monthly",
        frameworks=["NIST", "PCI-DSS"],
        freshness_sla_days=sla,
    )


def _evidence(eid, **kw):
    defaults = dict(framework="NIST", evidence_type="Encryption_Cert", freshness_days=5,
                    confidence_score=0.9, status="Approved", collection_date="2026-05-01", source="bucket")
    defaults.update(kw)
    return Evidence(evidence_id=eid, **defaults)


def _build(requirements, evidence, links):
    result = LinkResult(links=links)
    statuses = evaluate_quality(requirements, evidence, result)
    return build_ps3_report(
        request_id="t", generated_at="2026-06-13", requirements=requirements,
        evidence=evidence, link_result=result, statuses=statuses,
    )


def test_report_validates_and_has_summary_metrics():
    req = _requirement()
    ev = [_evidence("EVD00001")]
    links = [LinkedEvidence(evidence_id="EVD00001", requirement_id=req.id, link_confidence=0.8)]
    report = _build([req], ev, links)

    assert report.summary.total_requirements == 1
    for pct in (report.summary.overall_compliance_pct, report.summary.coverage_pct,
                report.summary.freshness_pct, report.summary.auto_collected_pct):
        assert 0.0 <= pct <= 100.0
    assert report.disclaimer
    assert "anomaly" in report.disclaimer.lower()  # we explain we ignored the labels


def test_fallback_narrative_cites_evidence_ids_when_evidence_exists():
    req = _requirement()
    ev = [_evidence("EVD00042")]
    links = [LinkedEvidence(evidence_id="EVD00042", requirement_id=req.id, link_confidence=0.8)]
    report = _build([req], ev, links)
    narrative = report.requirements[0].narrative
    assert EVD_RE.search(narrative), narrative


def test_gap_requirement_explains_missing_proof():
    req = _requirement()
    report = _build([req], [], [])
    rr = report.requirements[0]
    assert rr.status == "GAP"
    assert rr.gaps
    assert "AWS KMS Configuration" in " ".join(rr.gaps)


def test_pdf_renders_valid_bytes():
    req = _requirement()
    ev = [_evidence("EVD00001")]
    links = [LinkedEvidence(evidence_id="EVD00001", requirement_id=req.id, link_confidence=0.8)]
    report = _build([req], ev, links)
    pdf = render_report_pdf(report)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_compliant_requirement_has_no_gaps():
    req = _requirement()
    ev = [_evidence("EVD00001", status="Approved", freshness_days=3, confidence_score=0.95)]
    links = [LinkedEvidence(evidence_id="EVD00001", requirement_id=req.id, link_confidence=0.85)]
    report = _build([req], ev, links)
    assert report.requirements[0].status == "COMPLIANT"
    assert report.requirements[0].gaps == []
