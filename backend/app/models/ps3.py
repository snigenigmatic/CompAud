"""PS3 domain + response models for Automated Compliance Evidence & Audit.

The Evidence model intentionally omits the three poisoned CSV columns
(requirement_id, requirement_description, anomaly_marker) so the two data
traps cannot be violated downstream: there is no field to id-join on, and no
provided label to fit.
"""

from __future__ import annotations

from pydantic import Field

from app.models.base import APIModel

class AgentTraceEntry(APIModel):
    agent: str
    status: str
    summary: str
    error: str | None = None


class Requirement(APIModel):
    id: str
    policy_id: str
    policy_name: str
    text: str
    raw_text: str
    responsible: str = ""
    scope: str = ""
    evidence_source: str = ""
    audit_frequency: str = ""
    frameworks: list[str] = Field(default_factory=list)
    compliance_mapping_raw: str = ""
    freshness_sla_days: int = 90


class Evidence(APIModel):
    evidence_id: str
    framework: str = ""
    evidence_type: str = ""
    evidence_summary: str = ""
    collected_by: str = ""
    collector_email: str = ""
    collection_date: str = ""
    freshness_days: int = 0
    reviewed_by: str = ""
    reviewer_email: str = ""
    review_date: str = ""
    evidence_location: str = ""
    confidence_score: float = 0.0
    status: str = ""
    source: str = "bucket"


class LinkedEvidence(APIModel):
    evidence_id: str
    requirement_id: str
    link_confidence: float
    framework_match: bool = False
    stale: bool = False
    low_confidence: bool = False
    unreviewed: bool = False
    rejected: bool = False
    needs_update: bool = False
    acceptable: bool = False


class RequirementStatusResult(APIModel):
    requirement_id: str
    status: str  # COMPLIANT | PARTIAL | GAP
    confidence: float
    confidence_rationale: str
    next_review_date: str
    linked_evidence_ids: list[str] = Field(default_factory=list)


# --- Frontend-facing response envelope shape ---


class PS3LinkedEvidenceView(APIModel):
    evidence_id: str
    type: str
    framework: str
    collection_date: str
    freshness_days: int
    confidence_score: float
    link_confidence: float
    status: str = ""
    flags: list[str] = Field(default_factory=list)


class RequirementReport(APIModel):
    id: str
    name: str
    text: str
    policy_id: str
    frameworks: list[str] = Field(default_factory=list)
    status: str
    confidence: float
    freshness_sla_days: int
    audit_frequency: str = ""
    linked_evidence: list[PS3LinkedEvidenceView] = Field(default_factory=list)
    narrative: str = ""
    confidence_rationale: str = ""
    next_review_date: str = ""
    gaps: list[str] = Field(default_factory=list)


class PS3Summary(APIModel):
    total_requirements: int
    compliant_count: int
    partial_count: int
    gap_count: int
    overall_compliance_pct: float
    coverage_pct: float
    freshness_pct: float
    total_evidence: int
    linked_evidence_count: int
    orphan_count: int
    auto_collected_pct: float
    frameworks: list[str] = Field(default_factory=list)
    exec_summary: str = ""


class PS3ReportResponse(APIModel):
    request_id: str
    generated_at: str
    summary: PS3Summary
    requirements: list[RequirementReport] = Field(default_factory=list)
    orphan_evidence_ids: list[str] = Field(default_factory=list)
    agent_trace: list[AgentTraceEntry] = Field(default_factory=list)
    disclaimer: str = ""


class RequirementCatalogResponse(APIModel):
    source: str
    count: int
    requirements: list[Requirement] = Field(default_factory=list)
