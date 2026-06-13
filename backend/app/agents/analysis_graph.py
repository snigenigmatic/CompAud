import logging
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.auditor import prepare_auditor_output
from app.agents.compliance import enrich_compliance_with_llm, evaluate_control_compliance
from app.agents.evidence import parse_evidence_upload
from app.agents.report import build_analysis_report
from app.agents.risk import assess_risk
from app.config import get_settings
from app.models.analysis import AnalysisResponse
from app.models.auditor import AuditorEvaluation
from app.models.compliance import ComplianceEvaluation, ControlComplianceResult
from app.models.controls import ControlRequirement
from app.models.evidence import EvidenceChunk, EvidencePackage
from app.models.risk import RiskEvaluation
from app.observability import set_span_attributes, start_span
from app.services.control_catalog_service import load_control_requirements

logger = logging.getLogger(__name__)


class AnalysisState(TypedDict, total=False):
    request_id: str
    uploaded_filename: str
    uploaded_content: bytes
    control_requirements: list[ControlRequirement]
    evidence_package: EvidencePackage
    compliance: ComplianceEvaluation
    risk: RiskEvaluation
    auditor: AuditorEvaluation
    response: AnalysisResponse
    artifact_count: int
    chunk_count: int
    gap_count: int
    llm_enrichments: dict[str, dict[str, Any]]
    regulatory_contexts: dict[str, list[dict[str, Any]]]


def run_analysis_graph(
    filename: str,
    content: bytes,
    request_id: str,
) -> AnalysisResponse:
    initial_state: AnalysisState = {
        "request_id": request_id,
        "uploaded_filename": filename,
        "uploaded_content": content,
    }
    final_state = get_analysis_graph().invoke(initial_state)
    return final_state["response"]


def stream_analysis_graph(
    filename: str,
    content: bytes,
    request_id: str,
):
    initial_state: AnalysisState = {
        "request_id": request_id,
        "uploaded_filename": filename,
        "uploaded_content": content,
    }
    yield from get_analysis_graph().stream(initial_state, stream_mode="updates")


@lru_cache
def get_analysis_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("load_controls", _load_controls_node)
    graph.add_node("evidence_agent", _evidence_agent_node)
    graph.add_node("compliance_agent", _compliance_agent_node)
    graph.add_node("llm_enrichment", _llm_enrichment_node)
    graph.add_node("risk_agent", _risk_agent_node)
    graph.add_node("auditor_agent", _auditor_agent_node)
    graph.add_node("report_agent", _report_agent_node)

    graph.add_edge(START, "load_controls")
    graph.add_edge("load_controls", "evidence_agent")
    graph.add_edge("evidence_agent", "compliance_agent")
    graph.add_edge("compliance_agent", "llm_enrichment")
    graph.add_edge("llm_enrichment", "risk_agent")
    graph.add_edge("risk_agent", "auditor_agent")
    graph.add_edge("auditor_agent", "report_agent")
    graph.add_edge("report_agent", END)

    return graph.compile()


def _load_controls_node(state: AnalysisState) -> AnalysisState:
    return {"control_requirements": load_control_requirements()}


def _evidence_agent_node(state: AnalysisState) -> AnalysisState:
    request_id = state["request_id"]
    uploaded_filename = state["uploaded_filename"]

    with start_span(
        "evidence_agent.extract",
        {
            "request_id": request_id,
            "uploaded_filename": uploaded_filename,
        },
    ) as span:
        evidence_package = parse_evidence_upload(
            filename=uploaded_filename,
            content=state["uploaded_content"],
        )
        attributes = {
            "artifact_count": len(evidence_package.artifacts),
            "chunk_count": len(evidence_package.chunks),
        }
        set_span_attributes(span, attributes)
        return {
            "evidence_package": evidence_package,
            **attributes,
        }


def _compliance_agent_node(state: AnalysisState) -> AnalysisState:
    controls = state["control_requirements"]
    evidence_package = state["evidence_package"]

    with start_span(
        "compliance_agent.map",
        {
            "request_id": state["request_id"],
            "control_count": len(controls),
        },
    ):
        compliance = ComplianceEvaluation(
            control_results=[
                _evaluate_control_with_span(
                    request_id=state["request_id"],
                    control=control,
                    chunks=evidence_package.chunks,
                )
                for control in controls
            ]
        )

    return {"compliance": compliance}


def _llm_enrichment_node(state: AnalysisState) -> AnalysisState:
    """Fetch regulatory context from knowledge graph and run LLM enrichment on each control."""
    settings = get_settings()
    controls = state["control_requirements"]
    compliance = state["compliance"]
    evidence_package = state["evidence_package"]
    compliance_by_id = {r.control_id: r for r in compliance.control_results}

    enrichments: dict[str, dict[str, Any]] = {}
    reg_contexts: dict[str, list[dict[str, Any]]] = {}

    with start_span(
        "llm_enrichment.run",
        {"request_id": state["request_id"], "control_count": len(controls)},
    ) as span:
        for control in controls:
            reg_ctx: list[dict[str, Any]] = []
            try:
                from app.knowledge.graph import _driver, get_regulatory_context
                if _driver is not None:
                    reg_ctx = get_regulatory_context(control.id)
            except Exception:
                logger.warning("Knowledge graph query failed for %s", control.id, exc_info=True)
            reg_contexts[control.id] = reg_ctx

            if settings.openai_enabled and settings.openai_api_key:
                try:
                    enrichment = enrich_compliance_with_llm(
                        control=control,
                        compliance_result=compliance_by_id[control.id],
                        chunks=evidence_package.chunks,
                        regulatory_context=reg_ctx,
                    )
                    enrichments[control.id] = enrichment
                except Exception:
                    logger.warning("LLM enrichment failed for %s", control.id, exc_info=True)

        set_span_attributes(span, {"enriched_count": len(enrichments)})

    return {
        "llm_enrichments": enrichments,
        "regulatory_contexts": reg_contexts,
    }


def _risk_agent_node(state: AnalysisState) -> AnalysisState:
    controls = state["control_requirements"]
    compliance = state["compliance"]

    with start_span(
        "risk_agent.score",
        {
            "request_id": state["request_id"],
            "control_count": len(controls),
        },
    ) as span:
        risk = assess_risk(controls=controls, compliance=compliance)
        gap_count = sum(len(result.gaps) for result in risk.control_results)
        set_span_attributes(span, {"gap_count": gap_count})

    return {
        "risk": risk,
        "gap_count": gap_count,
    }


def _auditor_agent_node(state: AnalysisState) -> AnalysisState:
    controls = state["control_requirements"]

    with start_span(
        "auditor_agent.questions",
        {
            "request_id": state["request_id"],
            "control_count": len(controls),
        },
    ):
        auditor = prepare_auditor_output(
            controls=controls,
            compliance=state["compliance"],
            risk=state["risk"],
            llm_enrichments=state.get("llm_enrichments"),
            regulatory_contexts=state.get("regulatory_contexts"),
        )

    return {"auditor": auditor}


def _report_agent_node(state: AnalysisState) -> AnalysisState:
    controls = state["control_requirements"]

    with start_span(
        "report_agent.assemble",
        {
            "request_id": state["request_id"],
            "control_count": len(controls),
        },
    ):
        response = build_analysis_report(
            request_id=state["request_id"],
            evidence_package=state["evidence_package"],
            controls=controls,
            compliance=state["compliance"],
            risk=state["risk"],
            auditor=state["auditor"],
            llm_enrichments=state.get("llm_enrichments"),
        )

    return {"response": response}


def _evaluate_control_with_span(
    request_id: str,
    control: ControlRequirement,
    chunks: list[EvidenceChunk],
) -> ControlComplianceResult:
    with start_span(
        f"control.{control.id}.evaluate",
        {
            "request_id": request_id,
            "control_id": control.id,
        },
    ) as span:
        result = evaluate_control_compliance(control=control, chunks=chunks)
        set_span_attributes(span, {"chunk_count": result.target_chunk_count})
        return result


def graph_node_names() -> list[str]:
    return [
        "load_controls",
        "evidence_agent",
        "compliance_agent",
        "llm_enrichment",
        "risk_agent",
        "auditor_agent",
        "report_agent",
    ]
