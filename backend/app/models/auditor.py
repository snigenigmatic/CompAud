from app.models.base import APIModel


class ToolTraceEntry(APIModel):
    tool: str
    input: str
    result: str


class ControlAuditorResult(APIModel):
    control_id: str
    reviewer_question: str
    suggestion: str
    risk_summary: str
    agent_plan: list[str]
    tool_trace: list[ToolTraceEntry]


class AuditorEvaluation(APIModel):
    control_results: list[ControlAuditorResult]
