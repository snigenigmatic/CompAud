from app.models.auditor import ToolTraceEntry
from app.models.base import APIModel
from app.models.evidence import EvidenceArtifact


class AnalysisSummary(APIModel):
    total_controls: int
    ready_count: int
    partial_count: int
    needs_prep_count: int
    total_gap_count: int
    top_auditor_questions: list[str]


class ControlEvidenceFound(APIModel):
    claim: str
    artifact: str
    location: str
    hash: str


class ComplianceScores(APIModel):
    letter_of_law: int = 0
    spirit_of_law: int = 0
    compliance_effort: int = 0


class ControlReportResult(APIModel):
    id: str
    name: str
    priority: str
    status: str
    confidence: float
    regulation_story: str
    artifact: str
    reasoning: list[str]
    reviewer_question: str
    suggestion: str
    provenance: str
    risk_summary: str
    evidence_found: list[ControlEvidenceFound]
    gaps: list[str]
    agent_plan: list[str]
    tool_trace: list[ToolTraceEntry]
    confidence_rationale: str
    scores: ComplianceScores = ComplianceScores()
    llm_reasoning: str = ""
    regulatory_citations: list[str] = []


class AgentTraceEntry(APIModel):
    agent: str
    status: str
    summary: str


class AnalysisResponse(APIModel):
    request_id: str
    uploaded_filename: str
    summary: AnalysisSummary
    artifacts: list[EvidenceArtifact]
    controls: list[ControlReportResult]
    agent_trace: list[AgentTraceEntry]
    disclaimer: str
