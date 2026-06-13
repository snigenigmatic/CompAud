"""Loads evidence_artifacts.csv into Evidence objects.

Deliberately reads ONLY the real, usable columns. The poisoned columns
(requirement_id, requirement_description, anomaly_marker) are never read — the
Evidence model has no fields for them — so the two data traps cannot leak in.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.config import PS3_EVIDENCE_CSV_PATH, get_settings
from app.models.ps3 import Evidence

# Columns we map. Note the three poisoned columns are intentionally absent.
_REAL_COLUMNS = {
    "evidence_id",
    "framework",
    "evidence_type",
    "evidence_summary",
    "collected_by",
    "collector_email",
    "collection_date",
    "freshness_days",
    "reviewed_by",
    "reviewer_email",
    "review_date",
    "evidence_location",
    "confidence_score",
    "status",
}


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _evidence_path() -> Path:
    settings = get_settings()
    if settings.ps3_evidence_csv_path:
        return Path(settings.ps3_evidence_csv_path)
    return PS3_EVIDENCE_CSV_PATH


def evidence_from_fields(fields: dict[str, str], source: str = "bucket") -> Evidence | None:
    """Map a row of named fields (only the real columns) to an Evidence object.

    Shared by the CSV loader and the BucketCollector. Poisoned columns present
    in ``fields`` are simply ignored — we never read them.
    """
    evidence_id = (fields.get("evidence_id") or "").strip()
    if not evidence_id:
        return None
    return Evidence(
        evidence_id=evidence_id,
        framework=(fields.get("framework") or "").strip(),
        evidence_type=(fields.get("evidence_type") or "").strip(),
        evidence_summary=(fields.get("evidence_summary") or "").strip(),
        collected_by=(fields.get("collected_by") or "").strip(),
        collector_email=(fields.get("collector_email") or "").strip(),
        collection_date=(fields.get("collection_date") or "").strip(),
        freshness_days=_to_int(fields.get("freshness_days", "")),
        reviewed_by=(fields.get("reviewed_by") or "").strip(),
        reviewer_email=(fields.get("reviewer_email") or "").strip(),
        review_date=(fields.get("review_date") or "").strip(),
        evidence_location=(fields.get("evidence_location") or "").strip(),
        confidence_score=_to_float(fields.get("confidence_score", "")),
        status=(fields.get("status") or "").strip(),
        source=source,
    )


def load_evidence_csv(path: Path | None = None, source: str = "bucket") -> list[Evidence]:
    path = path or _evidence_path()
    rows: list[Evidence] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            evidence = evidence_from_fields(raw, source=source)
            if evidence is not None:
                rows.append(evidence)
    return rows
