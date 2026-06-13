"""PS3 analysis service: run + SSE stream. Clones analysis_service's event
shape (analysis.started / progress / complete / error) so the frontend SSE
parser is reused unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from app.agents.ps3_graph import ps3_graph_node_names, run_ps3_graph, stream_ps3_graph
from app.models.ps3 import PS3ReportResponse
from app.observability import set_span_attributes, start_span

DEFAULT_REQUEST_ID = "ps3-analysis"

STEP_LABELS = {
    "load_requirements": "Parse policies",
    "collect_evidence": "Collect evidence",
    "embed": "Embed text",
    "link_evidence": "Link evidence",
    "evaluate_quality": "Evaluate quality",
    "generate_narratives": "Write narratives",
    "assemble_report": "Assemble report",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_ps3_analysis(request_id: str = DEFAULT_REQUEST_ID) -> PS3ReportResponse:
    with start_span("ps3.request", {"request_id": request_id}) as span:
        response = run_ps3_graph(request_id=request_id, generated_at=_now())
        set_span_attributes(
            span,
            {
                "requirement_count": response.summary.total_requirements,
                "evidence_count": response.summary.total_evidence,
                "gap_count": response.summary.gap_count,
            },
        )
        return response


def stream_ps3_analysis(request_id: str = DEFAULT_REQUEST_ID) -> Iterator[str]:
    steps = ps3_graph_node_names()
    yield _sse(
        event="analysis.started",
        data={
            "request_id": request_id,
            "uploaded_filename": "policy_documents.txt + evidence_artifacts.csv",
            "steps": [{"id": step, "label": STEP_LABELS.get(step, step)} for step in steps],
        },
        event_id=f"{request_id}:started",
    )

    # NOTE: no start_span() wrapping this generator — an OTel span context
    # cannot be detached cleanly across the yields that StreamingResponse
    # suspends/resumes in a different context. Per-node spans live inside the
    # graph nodes (which don't yield) and trace the work correctly.
    try:
        response: PS3ReportResponse | None = None
        for update in stream_ps3_graph(request_id=request_id, generated_at=_now()):
            for node_name, node_update in update.items():
                if node_name == "assemble_report" and "response" in node_update:
                    response = node_update["response"]
                yield _sse(
                    event="analysis.progress",
                    data=_progress_event(node_name, node_update, request_id, steps),
                    event_id=f"{request_id}:{node_name}",
                )

        if response is None:
            raise RuntimeError("PS3 analysis finished without a response.")

        yield _sse(
            event="analysis.complete",
            data={"response": response.model_dump(mode="json")},
            event_id=f"{request_id}:complete",
        )
    except Exception as exc:
        yield _sse(
            event="analysis.error",
            data={"request_id": request_id, "code": exc.__class__.__name__, "message": str(exc)},
            event_id=f"{request_id}:error",
        )


def _progress_event(node_name, node_update, request_id, steps) -> dict[str, Any]:
    step_index = steps.index(node_name) if node_name in steps else 0
    return {
        "request_id": request_id,
        "step": node_name,
        "label": STEP_LABELS.get(node_name, node_name),
        "status": "completed",
        "progress": round(((step_index + 1) / len(steps)) * 100),
        "message": _progress_message(node_name, node_update),
    }


def _progress_message(node_name, node_update) -> str:
    if node_name == "load_requirements":
        return f"{node_update.get('requirement_count', 0)} requirement(s) parsed"
    if node_name == "collect_evidence":
        return f"{node_update.get('evidence_count', 0)} evidence auto-collected"
    if node_name == "embed":
        return "Evidence + requirements embedded"
    if node_name == "link_evidence":
        return f"{node_update.get('link_count', 0)} linked, {node_update.get('unmapped_count', 0)} unmapped"
    if node_name == "evaluate_quality":
        return (
            f"{node_update.get('compliant_count', 0)} compliant / "
            f"{node_update.get('partial_count', 0)} partial / {node_update.get('gap_count', 0)} gap"
        )
    if node_name == "generate_narratives":
        return "Narratives written"
    if node_name == "assemble_report":
        return "Report ready"
    return "Step complete"


def _sse(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, separators=(",", ":"), default=str)
    for line in payload.splitlines():
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"
