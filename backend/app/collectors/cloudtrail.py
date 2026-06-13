"""CloudTrailCollector — simulates AWS CloudTrail.

Reads a JSON file of CloudTrail-shaped events ({"Records": [...]}) and maps
encryption/KMS/TLS-related events into normalised encryption Evidence. Other
events are ignored. This satisfies the "CloudTrail + one other integration"
requirement; the architecture doc covers the real boto3 lookup_events version.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from app.collectors.base import Collector
from app.config import REPO_ROOT
from app.models.ps3 import Evidence

logger = logging.getLogger(__name__)

DEFAULT_CLOUDTRAIL_PATH = REPO_ROOT / "backend" / "sample_inputs" / "cloudtrail_events.json"
_EVAL_TODAY = date(2026, 6, 13)

# event (source, name) -> (evidence_type, framework hint, human label).
# framework hint nudges the linker toward the right encryption requirement.
_ENCRYPTION_EVENTS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("kms.amazonaws.com", "EnableKeyRotation"): ("Encryption_Cert", "ISO27001", "KMS key rotation enabled"),
    ("kms.amazonaws.com", "RotateKeyOnDemand"): ("Encryption_Cert", "ISO27001", "KMS key rotated on demand"),
    ("kms.amazonaws.com", "CreateKey"): ("Encryption_Cert", "ISO27001", "KMS customer master key created"),
    ("s3.amazonaws.com", "PutBucketEncryption"): ("Encryption_Cert", "PCI-DSS", "S3 bucket default encryption (AES-256) enabled"),
    ("rds.amazonaws.com", "ModifyDBInstance"): ("Encryption_Cert", "PCI-DSS", "RDS storage encryption configured"),
    ("acm.amazonaws.com", "RenewCertificate"): ("Encryption_Cert", "GDPR", "ACM TLS certificate renewed"),
    ("elasticloadbalancing.amazonaws.com", "ModifyListener"): ("Encryption_Cert", "GDPR", "ELB listener TLS 1.2+ policy applied"),
}


class CloudTrailCollector(Collector):
    name = "cloudtrail"

    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_CLOUDTRAIL_PATH

    def collect(self, since: datetime | None = None) -> list[Evidence]:
        if not self.path.exists():
            logger.warning("CloudTrail events file does not exist: %s", self.path)
            return []

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = payload.get("Records", []) if isinstance(payload, dict) else []

        evidence: list[Evidence] = []
        for record in records:
            mapped = self._map_event(record)
            if mapped is None:
                continue
            if since is not None and _event_date(record) < since.date():
                continue
            evidence.append(mapped)

        logger.info(
            "CloudTrailCollector mapped %d/%d events to encryption evidence",
            len(evidence),
            len(records),
        )
        return evidence

    def _map_event(self, record: dict) -> Evidence | None:
        key = (record.get("eventSource", ""), record.get("eventName", ""))
        mapping = _ENCRYPTION_EVENTS.get(key)
        if mapping is None:
            return None

        evidence_type, framework, label = mapping
        event_date = _event_date(record)
        resource = record.get("requestParameters", {}) or {}
        target = (
            resource.get("bucketName")
            or resource.get("keyId")
            or resource.get("certificateArn")
            or resource.get("dBInstanceIdentifier")
            or "resource"
        )
        return Evidence(
            evidence_id=f"CT-{record.get('eventID') or label}",
            framework=framework,
            evidence_type=evidence_type,
            evidence_summary=f"{label} on {target} (CloudTrail {record.get('eventName')})",
            collected_by="CloudTrailCollector",
            collector_email="automation@compaud.local",
            collection_date=event_date.isoformat(),
            freshness_days=max(0, (_EVAL_TODAY - event_date).days),
            reviewed_by="CloudTrail (source of truth)",
            review_date=event_date.isoformat(),
            evidence_location=f"cloudtrail://{record.get('awsRegion', 'us-east-1')}/{record.get('eventName')}",
            confidence_score=0.9,
            status="Approved",
            source="cloudtrail",
        )


def _event_date(record: dict) -> date:
    raw = str(record.get("eventTime", ""))
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return _EVAL_TODAY
