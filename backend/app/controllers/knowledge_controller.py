import logging

from fastapi import APIRouter, Path

from app.errors import ApiError
from app.knowledge.graph import (
    get_full_context,
    get_graph_stats,
    get_regulatory_context,
    get_rules_by_priority,
    search_rules,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _require_driver():
    from app.knowledge.graph import _driver

    if _driver is None:
        raise ApiError(
            status_code=503,
            code="KNOWLEDGE_GRAPH_UNAVAILABLE",
            message="Neo4j knowledge graph is not connected.",
        )


@router.get(
    "/stats",
    operation_id="getKnowledgeGraphStats",
    summary="Get knowledge graph node and relationship counts",
)
def knowledge_stats() -> dict:
    _require_driver()
    return get_graph_stats()


@router.get(
    "/context/{control_id}",
    operation_id="getControlRegulatoryContext",
    summary="Get full regulatory context for a control",
)
def control_context(control_id: str = Path(description="Control ID, e.g. FT-IAM-01")) -> dict:
    _require_driver()
    ctx = get_full_context(control_id)
    if "error" in ctx:
        raise ApiError(status_code=404, code="CONTROL_NOT_FOUND", message=ctx["error"])
    return ctx


@router.get(
    "/rules/{control_id}",
    operation_id="getControlGoverningRules",
    summary="Get governing rules for a control from official regulatory sources",
)
def control_rules(control_id: str = Path(description="Control ID, e.g. FT-IAM-01")) -> list[dict]:
    _require_driver()
    return get_regulatory_context(control_id)


@router.get(
    "/priority/{priority}",
    operation_id="getRulesByPriority",
    summary="Get all rules at a given priority level",
)
def rules_by_priority(priority: str = Path(description="Priority level, e.g. P1_Critical")) -> list[dict]:
    _require_driver()
    return get_rules_by_priority(priority)


@router.get(
    "/search",
    operation_id="searchRules",
    summary="Full-text search across regulatory rule text",
)
def search(q: str, limit: int = 10) -> list[dict]:
    _require_driver()
    return search_rules(q, limit=limit)
