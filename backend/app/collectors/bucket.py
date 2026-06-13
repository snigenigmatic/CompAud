"""BucketCollector — simulates an S3/GCS object store.

Reads CSV/PDF files dropped into a local directory. CSVs are parsed with the
existing evidence parser (app.agents.evidence.parse_evidence_upload), then each
row is normalised into the Evidence schema. This is how evidence_artifacts.csv
"arrives" in the pipeline. PDFs are recorded as Policy_Document evidence.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from app.agents.evidence import parse_evidence_upload
from app.collectors.base import Collector
from app.config import REPO_ROOT
from app.models.ps3 import Evidence
from app.services.ps3_evidence_loader import evidence_from_fields

logger = logging.getLogger(__name__)

DEFAULT_BUCKET_DIR = REPO_ROOT / "backend" / "sample_inputs" / "bucket"
_EVAL_TODAY = date(2026, 6, 13)


class BucketCollector(Collector):
    name = "bucket"

    def __init__(self, directory: Path | None = None):
        self.directory = directory or DEFAULT_BUCKET_DIR

    def collect(self, since: datetime | None = None) -> list[Evidence]:
        if not self.directory.exists():
            logger.warning("Bucket directory does not exist: %s", self.directory)
            return []

        evidence: list[Evidence] = []
        for path in sorted(self.directory.iterdir()):
            suffix = path.suffix.lower()
            if suffix == ".csv":
                evidence.extend(self._collect_csv(path))
            elif suffix == ".pdf":
                evidence.append(self._collect_pdf(path))

        if since is not None:
            cutoff = since.date()
            evidence = [e for e in evidence if _on_or_after(e.collection_date, cutoff)]
        return evidence

    def _collect_csv(self, path: Path) -> list[Evidence]:
        package = parse_evidence_upload(path.name, path.read_bytes())
        source = f"bucket:{path.name}"
        rows: list[Evidence] = []
        for chunk in package.chunks:
            evidence = evidence_from_fields(chunk.parsed_fields, source=source)
            if evidence is not None:
                rows.append(evidence)
        logger.info("BucketCollector parsed %d rows from %s", len(rows), path.name)
        return rows

    def _collect_pdf(self, path: Path) -> Evidence:
        age = max(0, (_EVAL_TODAY - _file_mdate(path)).days)
        return Evidence(
            evidence_id=f"BKT-{path.stem}",
            framework="",
            evidence_type="Policy_Document",
            evidence_summary=f"Policy document file collected from bucket: {path.name}",
            collected_by="BucketCollector",
            collection_date=_file_mdate(path).isoformat(),
            freshness_days=age,
            evidence_location=str(path),
            confidence_score=0.75,
            status="Pending_Review",
            source=f"bucket:{path.name}",
        )


def _file_mdate(path: Path) -> date:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return _EVAL_TODAY


def _on_or_after(collection_date: str, cutoff: date) -> bool:
    try:
        return datetime.strptime(collection_date, "%Y-%m-%d").date() >= cutoff
    except (ValueError, TypeError):
        return True
