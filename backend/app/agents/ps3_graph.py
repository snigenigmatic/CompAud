"""PS3 LangGraph pipeline. Mirrors the Rakshak analysis_graph backbone (linear
StateGraph, @lru_cache compiled graph, run/stream, node-names) so the SSE
service and observability are reused. The LLM is used only in
generate_narratives; everything else is deterministic.
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.ps3_linker import LinkResult, link_from_scores, score_matrix
from app.agents.ps3_quality import COMPLIANT, GAP, PARTIAL, evaluate_quality
from app.agents.ps3_report import build_ps3_report, generate_report_text
from app.collectors import BucketCollector, CloudTrailCollector
from app.collectors.base import collect_all
from app.models.analysis import AgentTraceEntry
from app.models.ps3 import Evidence, PS3ReportResponse, Requirement, RequirementStatusResult
from app.observability import set_span_attributes, start_span
from app.services.ps3_requirement_service import load_requirements

logger = logging.getLogger(__name__)


class PS3State(TypedDict, total=False):
    request_id: str
    generated_at: str
    requirements: list[Requirement]
    evidence: list[Evidence]
    scores: Any  # np.ndarray, kept out of the response
    link_result: LinkResult
    statuses: dict[str, RequirementStatusResult]
    narratives: dict[str, str]
    exec_summary: str
    response: PS3ReportResponse
    # counters for SSE progress
    requirement_count: int
    evidence_count: int
    auto_collected: int
    link_count: int
    unmapped_count: int
    compliant_count: int
    partial_count: int
    gap_count: int


_NODES = [
    "load_requirements",
    "collect_evidence",
    "embed",
    "link_evidence",
    "evaluate_quality",
    "generate_narratives",
    "assemble_report",
]


def ps3_graph_node_names() -> list[str]:
    return list(_NODES)


def run_ps3_graph(request_id: str, generated_at: str | None = None) -> PS3ReportResponse:
    initial: PS3State = {
        "request_id": request_id,
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
    }
    return get_ps3_graph().invoke(initial)["response"]


def stream_ps3_graph(request_id: str, generated_at: str | None = None):
    initial: PS3State = {
        "request_id": request_id,
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
    }
    yield from get_ps3_graph().stream(initial, stream_mode="updates")


@lru_cache
def get_ps3_graph():
    graph = StateGraph(PS3State)
    graph.add_node("load_requirements", _load_requirements_node)
    graph.add_node("collect_evidence", _collect_evidence_node)
    graph.add_node("embed", _embed_node)
    graph.add_node("link_evidence", _link_node)
    graph.add_node("evaluate_quality", _quality_node)
    graph.add_node("generate_narratives", _narratives_node)
    graph.add_node("assemble_report", _assemble_node)

    graph.add_edge(START, "load_requirements")
    graph.add_edge("load_requirements", "collect_evidence")
    graph.add_edge("collect_evidence", "embed")
    graph.add_edge("embed", "link_evidence")
    graph.add_edge("link_evidence", "evaluate_quality")
    graph.add_edge("evaluate_quality", "generate_narratives")
    graph.add_edge("generate_narratives", "assemble_report")
    graph.add_edge("assemble_report", END)
    return graph.compile()


def _load_requirements_node(state: PS3State) -> PS3State:
    with start_span("ps3.load_requirements", {"request_id": state["request_id"]}) as span:
        requirements = load_requirements()
        set_span_attributes(span, {"requirement_count": len(requirements)})
        return {"requirements": requirements, "requirement_count": len(requirements)}


def _collect_evidence_node(state: PS3State) -> PS3State:
    with start_span("ps3.collect_evidence", {"request_id": state["request_id"]}) as span:
        evidence = collect_all([BucketCollector(), CloudTrailCollector()])
        auto = sum(1 for e in evidence if e.source.startswith(("bucket", "cloudtrail")))
        set_span_attributes(span, {"evidence_count": len(evidence), "auto_collected": auto})
        return {"evidence": evidence, "evidence_count": len(evidence), "auto_collected": auto}


def _embed_node(state: PS3State) -> PS3State:
    with start_span("ps3.embed", {"request_id": state["request_id"]}) as span:
        scores = score_matrix(state["evidence"], state["requirements"])
        set_span_attributes(span, {"matrix_shape": str(getattr(scores, "shape", ""))})
        return {"scores": scores}


def _link_node(state: PS3State) -> PS3State:
    with start_span("ps3.link_evidence", {"request_id": state["request_id"]}) as span:
        link_result = link_from_scores(state["evidence"], state["requirements"], state["scores"])
        set_span_attributes(
            span,
            {"link_count": len(link_result.links), "unmapped_count": len(link_result.orphan_evidence_ids)},
        )
        return {
            "link_result": link_result,
            "link_count": len(link_result.links),
            "unmapped_count": len(link_result.orphan_evidence_ids),
        }


def _quality_node(state: PS3State) -> PS3State:
    with start_span("ps3.evaluate_quality", {"request_id": state["request_id"]}) as span:
        statuses = evaluate_quality(state["requirements"], state["evidence"], state["link_result"])
        counts = {
            "compliant_count": sum(1 for s in statuses.values() if s.status == COMPLIANT),
            "partial_count": sum(1 for s in statuses.values() if s.status == PARTIAL),
            "gap_count": sum(1 for s in statuses.values() if s.status == GAP),
        }
        set_span_attributes(span, counts)
        return {"statuses": statuses, **counts}


def _narratives_node(state: PS3State) -> PS3State:
    with start_span("ps3.generate_narratives", {"request_id": state["request_id"]}) as span:
        narratives, exec_summary = generate_report_text(
            state["requirements"], state["evidence"], state["link_result"], state["statuses"]
        )
        set_span_attributes(span, {"narrative_count": len(narratives)})
        return {"narratives": narratives, "exec_summary": exec_summary}


def _assemble_node(state: PS3State) -> PS3State:
    with start_span("ps3.assemble_report", {"request_id": state["request_id"]}):
        response = build_ps3_report(
            request_id=state["request_id"],
            generated_at=state["generated_at"],
            requirements=state["requirements"],
            evidence=state["evidence"],
            link_result=state["link_result"],
            statuses=state["statuses"],
            narratives=state.get("narratives"),
            exec_summary=state.get("exec_summary"),
            agent_trace=_agent_trace(state),
        )
        return {"response": response}


def _agent_trace(state: PS3State) -> list[AgentTraceEntry]:
    return [
        AgentTraceEntry(agent="Policy Parser", status="completed", summary=f"{state.get('requirement_count', 0)} requirements parsed"),
        AgentTraceEntry(agent="Collectors", status="completed", summary=f"{state.get('evidence_count', 0)} evidence auto-collected"),
        AgentTraceEntry(agent="Semantic Linker", status="completed", summary=f"{state.get('link_count', 0)} links, {state.get('unmapped_count', 0)} unmapped"),
        AgentTraceEntry(agent="Quality Engine", status="completed", summary=f"{state.get('compliant_count', 0)} compliant / {state.get('partial_count', 0)} partial / {state.get('gap_count', 0)} gap"),
        AgentTraceEntry(agent="Report Writer", status="completed", summary="Narratives + executive summary assembled"),
    ]
