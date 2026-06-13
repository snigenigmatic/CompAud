from app.collectors import BucketCollector, CloudTrailCollector
from app.collectors.base import collect_all


def test_bucket_collector_yields_500_normalized_rows():
    rows = BucketCollector().collect()
    # 500 CSV rows (a bucket may also contain PDFs, so >= 500).
    assert len([e for e in rows if e.evidence_id.startswith("EVD")]) == 500
    sample = rows[0]
    assert sample.evidence_id
    assert sample.framework
    assert sample.evidence_type
    assert 0.0 <= sample.confidence_score <= 1.0
    assert all(e.source.startswith("bucket") for e in rows)


def test_cloudtrail_collector_maps_encryption_events_and_filters_noise():
    rows = CloudTrailCollector().collect()
    assert len(rows) == 8  # 8 encryption events mapped, 4 noise events filtered
    assert all(e.evidence_type == "Encryption_Cert" for e in rows)
    assert all(e.status == "Approved" for e in rows)
    assert all(e.source == "cloudtrail" for e in rows)
    # ids must be unique (regression guard for the truncation collision)
    assert len({e.evidence_id for e in rows}) == len(rows)


def test_cloudtrail_evidence_is_fresh():
    rows = CloudTrailCollector().collect()
    assert all(e.freshness_days <= 10 for e in rows)


def test_collectors_produce_high_auto_collection_rate():
    evidence = collect_all([BucketCollector(), CloudTrailCollector()])
    auto = sum(1 for e in evidence if e.source.startswith(("bucket", "cloudtrail")))
    assert auto / len(evidence) >= 0.70
    assert auto == len(evidence)  # everything is collector-sourced
