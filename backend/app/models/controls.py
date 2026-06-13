from pydantic import Field

from app.models.base import APIModel


class RequiredEvidenceElement(APIModel):
    id: str
    label: str
    description: str
    search_terms: list[str]
    negative_terms: list[str] = Field(default_factory=list)
    critical: bool
    reviewer_gap: str


class ControlRequirement(APIModel):
    id: str
    name: str
    priority: str
    regulation_story: str
    mission: str
    demo_status_target: str
    target_artifacts: list[str]
    required_evidence_elements: list[RequiredEvidenceElement]
    common_reviewer_questions: list[str]


class ControlCatalogResponse(APIModel):
    source: str
    count: int
    controls: list[ControlRequirement]
