from app.models.base import APIModel
from app.models.evidence import EvidenceCitation


class EvidenceElementResult(APIModel):
    control_id: str
    element_id: str
    label: str
    critical: bool
    satisfied: bool
    matched_terms: list[str]
    missing_terms: list[str]
    citations: list[EvidenceCitation]
    negative_hits: list[EvidenceCitation]
    reviewer_gap: str


class ControlComplianceResult(APIModel):
    control_id: str
    control_name: str
    target_artifacts: list[str]
    target_chunk_count: int
    element_results: list[EvidenceElementResult]


class ComplianceEvaluation(APIModel):
    control_results: list[ControlComplianceResult]
