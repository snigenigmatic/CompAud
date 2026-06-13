import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.agents.analysis_graph import graph_node_names, run_analysis_graph, stream_analysis_graph
from app.config import REPO_ROOT
from app.models.analysis import AnalysisResponse
from app.observability import set_span_attributes, start_span


DEMO_EVIDENCE_PATH = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"
DEMO_REQUEST_ID = "demo-golden"

STEP_LABELS = {
    "load_controls": "Load controls",
    "evidence_agent": "Read evidence",
    "compliance_agent": "Map controls",
    "llm_enrichment": "Enrich with law",
    "risk_agent": "Score risk",
    "auditor_agent": "Draft auditor view",
    "report_agent": "Assemble report",
}


def analyze_evidence_bytes(
    filename: str,
    content: bytes,
    request_id: str,
) -> AnalysisResponse:
    with start_span(
        "analysis.request",
        {
            "request_id": request_id,
            "uploaded_filename": filename,
        },
    ) as request_span:
        response = run_analysis_graph(
            filename=filename,
            content=content,
            request_id=request_id,
        )
        set_span_attributes(
            request_span,
            {
                "artifact_count": len(response.artifacts),
                "chunk_count": sum(
                    artifact.chunk_count for artifact in response.artifacts
                ),
                "gap_count": response.summary.total_gap_count,
            },
        )
        return response


def analyze_demo_evidence(path: Path = DEMO_EVIDENCE_PATH) -> AnalysisResponse:
    return analyze_evidence_bytes(
        filename=path.name,
        content=path.read_bytes(),
        request_id=DEMO_REQUEST_ID,
    )


def stream_evidence_analysis(
    filename: str,
    content: bytes,
    request_id: str,
) -> Iterator[str]:
    steps = graph_node_names()
    yield _sse(
        event="analysis.started",
        data={
            "request_id": request_id,
            "uploaded_filename": filename,
            "steps": [
                {"id": step, "label": STEP_LABELS.get(step, step)}
                for step in steps
            ],
        },
        event_id=f"{request_id}:started",
    )

    try:
        with start_span(
            "analysis.request",
            {
                "request_id": request_id,
                "uploaded_filename": filename,
                "streaming": True,
            },
        ) as request_span:
            response: AnalysisResponse | None = None
            for update in stream_analysis_graph(
                filename=filename,
                content=content,
                request_id=request_id,
            ):
                for node_name, node_update in update.items():
                    if node_name == "report_agent" and "response" in node_update:
                        response = node_update["response"]

                    yield _sse(
                        event="analysis.progress",
                        data=_progress_event(
                            node_name=node_name,
                            node_update=node_update,
                            request_id=request_id,
                            steps=steps,
                        ),
                        event_id=f"{request_id}:{node_name}",
                    )

            if response is None:
                raise RuntimeError("Analysis finished without a response.")

            set_span_attributes(
                request_span,
                {
                    "artifact_count": len(response.artifacts),
                    "chunk_count": sum(
                        artifact.chunk_count for artifact in response.artifacts
                    ),
                    "gap_count": response.summary.total_gap_count,
                },
            )
            yield _sse(
                event="analysis.complete",
                data={"response": response.model_dump(mode="json")},
                event_id=f"{request_id}:complete",
            )
    except Exception as exc:
        yield _sse(
            event="analysis.error",
            data={
                "request_id": request_id,
                "code": exc.__class__.__name__,
                "message": str(exc),
            },
            event_id=f"{request_id}:error",
        )


def stream_demo_evidence(path: Path = DEMO_EVIDENCE_PATH) -> Iterator[str]:
    return stream_evidence_analysis(
        filename=path.name,
        content=path.read_bytes(),
        request_id=DEMO_REQUEST_ID,
    )


def _progress_event(
    node_name: str,
    node_update: dict[str, Any],
    request_id: str,
    steps: list[str],
) -> dict[str, Any]:
    step_index = steps.index(node_name) if node_name in steps else 0
    progress = round(((step_index + 1) / len(steps)) * 100)
    message = _progress_message(node_name=node_name, node_update=node_update)

    return {
        "request_id": request_id,
        "step": node_name,
        "label": STEP_LABELS.get(node_name, node_name),
        "status": "completed",
        "progress": progress,
        "message": message,
    }


def _progress_message(node_name: str, node_update: dict[str, Any]) -> str:
    if node_name == "evidence_agent":
        return (
            f"{node_update.get('artifact_count', 0)} artifact(s), "
            f"{node_update.get('chunk_count', 0)} evidence chunk(s)"
        )
    if node_name == "compliance_agent":
        compliance = node_update.get("compliance")
        control_count = len(getattr(compliance, "control_results", []) or [])
        return f"{control_count} control(s) evaluated"
    if node_name == "llm_enrichment":
        enrichments = node_update.get("llm_enrichments") or {}
        contexts = node_update.get("regulatory_contexts") or {}
        return (
            f"{len(enrichments)} LLM enrichment(s), "
            f"{sum(bool(value) for value in contexts.values())} control(s) with rules"
        )
    if node_name == "risk_agent":
        return f"{node_update.get('gap_count', 0)} gap(s) found"
    if node_name == "auditor_agent":
        auditor = node_update.get("auditor")
        question_count = len(getattr(auditor, "control_results", []) or [])
        return f"{question_count} auditor question(s) prepared"
    if node_name == "report_agent":
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
