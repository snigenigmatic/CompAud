from app.agents.ps3_linker import LinkResult
from app.agents.ps3_quality import COMPLIANT, GAP, PARTIAL, evaluate_quality
from app.models.ps3 import Evidence, LinkedEvidence, Requirement


def _req(rid="R1", sla=30, frameworks=("NIST",)):
    return Requirement(
        id=rid,
        policy_id="POL",
        policy_name="Test",
        text="requirement text",
        raw_text="requirement text",
        evidence_source="Some Source",
        audit_frequency="Monthly",
        frameworks=list(frameworks),
        freshness_sla_days=sla,
    )


def _ev(eid, *, freshness=5, confidence=0.9, status="Approved", date="2026-05-01"):
    return Evidence(
        evidence_id=eid,
        framework="NIST",
        evidence_type="Encryption_Cert",
        freshness_days=freshness,
        confidence_score=confidence,
        status=status,
        collection_date=date,
    )


def _link(eid, rid="R1", cos=0.8):
    return LinkedEvidence(evidence_id=eid, requirement_id=rid, link_confidence=cos)


def _evaluate(req, pairs):
    """pairs: list of (Evidence, LinkedEvidence)."""
    evidence = [e for e, _ in pairs]
    result = LinkResult(links=[l for _, l in pairs])
    statuses = evaluate_quality([req], evidence, result)
    return statuses[req.id], result


def test_compliant_with_approved_fresh_confident_evidence():
    req = _req(sla=30)
    status, _ = _evaluate(req, [(_ev("EVD1", freshness=5, confidence=0.9, status="Approved"), _link("EVD1"))])
    assert status.status == COMPLIANT
    assert status.confidence > 0.6
    assert "EVD1" in status.confidence_rationale


def test_partial_when_only_stale_evidence():
    req = _req(sla=30)
    status, result = _evaluate(req, [(_ev("EVD1", freshness=120, status="Approved"), _link("EVD1"))])
    assert status.status == PARTIAL
    assert result.links[0].stale is True
    assert result.links[0].acceptable is False


def test_partial_when_low_confidence():
    req = _req(sla=30)
    status, result = _evaluate(req, [(_ev("EVD1", freshness=5, confidence=0.55, status="Approved"), _link("EVD1"))])
    assert status.status == PARTIAL
    assert result.links[0].low_confidence is True


def test_partial_when_pending_review_is_unreviewed():
    req = _req(sla=30)
    status, result = _evaluate(req, [(_ev("EVD1", status="Pending_Review"), _link("EVD1"))])
    assert status.status == PARTIAL
    assert result.links[0].unreviewed is True


def test_gap_when_no_links():
    req = _req()
    statuses = evaluate_quality([req], [], LinkResult())
    assert statuses[req.id].status == GAP
    assert statuses[req.id].confidence <= 0.25
    assert "no evidence" in statuses[req.id].confidence_rationale.lower()


def test_gap_when_all_rejected():
    req = _req()
    status, result = _evaluate(req, [(_ev("EVD1", status="Rejected"), _link("EVD1"))])
    assert status.status == GAP
    assert result.links[0].rejected is True


def test_needs_update_flag_set():
    req = _req()
    _, result = _evaluate(req, [(_ev("EVD1", status="Needs_Update"), _link("EVD1"))])
    assert result.links[0].needs_update is True


def test_freshness_sla_drives_stale_continuous():
    # Continuous SLA = 1 day: 40-day-old evidence must be stale.
    req = _req(sla=1)
    _, result = _evaluate(req, [(_ev("EVD1", freshness=40, status="Approved"), _link("EVD1"))])
    assert result.links[0].stale is True


def test_next_review_date_is_collection_plus_sla():
    req = _req(sla=30)
    status, _ = _evaluate(req, [(_ev("EVD1", date="2026-05-01", status="Approved"), _link("EVD1"))])
    assert status.next_review_date == "2026-05-31"
