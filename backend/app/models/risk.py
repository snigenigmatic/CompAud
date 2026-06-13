from app.models.base import APIModel


class ControlRiskResult(APIModel):
    control_id: str
    control_name: str
    priority: str
    status: str
    confidence: float
    total_elements: int
    satisfied_elements: int
    critical_elements: int
    satisfied_critical_elements: int
    negative_hit_count: int
    gaps: list[str]
    confidence_rationale: str


class RiskEvaluation(APIModel):
    control_results: list[ControlRiskResult]
