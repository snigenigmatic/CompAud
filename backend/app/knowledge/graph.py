"""
Neo4j knowledge graph query layer for CompAud agents.

Provides high-level query functions that agents call to get regulatory context,
evidence requirements, cross-framework relationships, and control-to-rule mappings.

All functions accept a Neo4j driver (or session) and return plain dicts/lists
ready for injection into agent prompts.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Driver management
# ---------------------------------------------------------------------------

_driver: Driver | None = None


def init_driver(uri: str, user: str, password: str) -> Driver:
    """Initialise and cache the Neo4j driver. Call once at app startup."""
    global _driver
    from neo4j import GraphDatabase

    _driver = GraphDatabase.driver(uri, auth=(user, password))
    _driver.verify_connectivity()
    logger.info("Neo4j driver initialised → %s", uri)
    return _driver


def get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialised. Call init_driver() first.")
    return _driver


def close_driver() -> None:
    global _driver
    if _driver:
        _driver.close()
        _driver = None


# ---------------------------------------------------------------------------
# Agent query functions
# ---------------------------------------------------------------------------


def get_regulatory_context(control_id: str) -> list[dict[str, Any]]:
    """
    Return official regulatory text for every rule that governs a Rakshak control.

    Used by the Compliance Agent and Auditor Agent to ground assessments
    in actual regulation text with section references.

    Returns list of dicts:
      {rule_id, framework, section_number, clause_reference,
       rule_text, obligation_type, deadline_or_sla, penalty,
       source_document, priority}
    """
    query = """
    MATCH (c:Control {control_id: $cid})-[:GOVERNED_BY]->(r:Rule)
    RETURN r.rule_id           AS rule_id,
           r.framework         AS framework,
           r.section_number    AS section_number,
           r.section_title     AS section_title,
           r.clause_reference  AS clause_reference,
           r.rule_text         AS rule_text,
           r.obligation_type   AS obligation_type,
           r.deadline_or_sla   AS deadline_or_sla,
           r.penalty           AS penalty,
           r.source_document   AS source_document,
           r.priority          AS priority
    ORDER BY r.priority, r.rule_id
    """
    with get_driver().session() as session:
        return session.run(query, cid=control_id).data()


def get_controls_for_domain(domain: str) -> list[dict[str, Any]]:
    """
    Return all Rakshak controls linked to rules in a given domain.

    Useful for the Risk Agent to see which controls are affected
    when a domain-level gap is detected.
    """
    query = """
    MATCH (c:Control)-[:GOVERNED_BY]->(r:Rule)-[:IN_DOMAIN]->(d:Domain {name: $domain})
    RETURN DISTINCT
           c.control_id  AS control_id,
           c.name        AS control_name,
           c.priority    AS priority,
           c.mission     AS mission,
           c.demo_status AS demo_status
    ORDER BY c.priority
    """
    with get_driver().session() as session:
        return session.run(query, domain=domain).data()


def get_rules_for_domain(domain: str) -> list[dict[str, Any]]:
    """Return all rules in a specific compliance domain."""
    query = """
    MATCH (r:Rule)-[:IN_DOMAIN]->(d:Domain {name: $domain})
    RETURN r.rule_id          AS rule_id,
           r.framework        AS framework,
           r.clause_reference AS clause_reference,
           r.rule_text        AS rule_text,
           r.obligation_type  AS obligation_type,
           r.priority         AS priority,
           r.deadline_or_sla  AS deadline_or_sla
    ORDER BY r.priority, r.rule_id
    """
    with get_driver().session() as session:
        return session.run(query, domain=domain).data()


def get_evidence_requirements(control_id: str) -> list[dict[str, Any]]:
    """
    Return all evidence types required by rules governing a control.

    The Evidence Agent uses this to know what documents to look for
    beyond the search_terms in control_requirements.json.
    """
    query = """
    MATCH (c:Control {control_id: $cid})-[:GOVERNED_BY]->(r:Rule)-[:REQUIRES_EVIDENCE]->(e:EvidenceType)
    RETURN DISTINCT
           e.name          AS evidence_type,
           r.rule_id       AS rule_id,
           r.framework     AS framework,
           r.obligation_type AS obligation_type
    ORDER BY e.name
    """
    with get_driver().session() as session:
        return session.run(query, cid=control_id).data()


def get_cross_framework_rules(framework: str) -> list[dict[str, Any]]:
    """
    Return rules from other frameworks that cross-reference this framework.

    Useful for showing auditors that a single control satisfies
    multiple regulatory bodies (e.g., PCI-DSS + RBI + CERT-In).
    """
    query = """
    MATCH (r:Rule)-[:CROSS_REFERENCES]->(f:Framework {name: $fw})
    WHERE r.framework <> $fw
    RETURN r.rule_id       AS rule_id,
           r.framework     AS source_framework,
           r.domain        AS domain,
           r.rule_text     AS rule_text,
           r.priority      AS priority
    ORDER BY r.priority, r.rule_id
    """
    with get_driver().session() as session:
        return session.run(query, fw=framework).data()


def get_full_context(control_id: str) -> dict[str, Any]:
    """
    Return everything an agent needs for a control in one call:
    control metadata, governing rules with regulatory text, evidence types,
    and cross-framework relationships.

    This is the primary injection point for the Compliance and Auditor agents.
    """
    # Control metadata
    ctrl_query = """
    MATCH (c:Control {control_id: $cid})
    OPTIONAL MATCH (c)-[:UNDER_FRAMEWORK]->(f:Framework)
    RETURN c.control_id       AS control_id,
           c.name             AS name,
           c.priority         AS priority,
           c.regulation_story AS regulation_story,
           c.mission          AS mission,
           c.demo_status      AS demo_status,
           collect(DISTINCT f.name) AS frameworks
    """
    with get_driver().session() as session:
        ctrl = session.run(ctrl_query, cid=control_id).single()
        if not ctrl:
            return {"error": f"Control {control_id} not found in knowledge graph"}

        control_meta = dict(ctrl)
        rules = get_regulatory_context(control_id)
        evidence = get_evidence_requirements(control_id)

        # Cross-framework rules for each framework the control falls under
        cross_refs = []
        for fw in control_meta.get("frameworks", []):
            cross_refs.extend(get_cross_framework_rules(fw))

        return {
            "control": control_meta,
            "governing_rules": rules,
            "evidence_types": evidence,
            "cross_framework_rules": cross_refs,
        }


def get_rules_by_priority(priority: str) -> list[dict[str, Any]]:
    """Return all rules at a given priority level (P1_Critical, P2_High, P3_Medium)."""
    query = """
    MATCH (r:Rule)-[:HAS_PRIORITY]->(p:Priority {level: $prio})
    RETURN r.rule_id       AS rule_id,
           r.framework     AS framework,
           r.domain        AS domain,
           r.rule_text     AS rule_text,
           r.obligation_type AS obligation_type,
           r.deadline_or_sla AS deadline_or_sla
    ORDER BY r.framework, r.rule_id
    """
    with get_driver().session() as session:
        return session.run(query, prio=priority).data()


def get_applicable_rules(entity_type: str) -> list[dict[str, Any]]:
    """Return all rules that apply to a specific entity type (e.g., 'Payment_Aggregators')."""
    query = """
    MATCH (r:Rule)-[:APPLIES_TO]->(a:ApplicableEntity {name: $entity})
    RETURN r.rule_id       AS rule_id,
           r.framework     AS framework,
           r.domain        AS domain,
           r.sub_domain    AS sub_domain,
           r.rule_text     AS rule_text,
           r.priority      AS priority
    ORDER BY r.priority, r.rule_id
    """
    with get_driver().session() as session:
        return session.run(query, entity=entity_type).data()


def get_rules_by_tag(tag: str) -> list[dict[str, Any]]:
    """Return all rules tagged with a specific keyword."""
    query = """
    MATCH (r:Rule)-[:TAGGED_WITH]->(t:Tag {name: $tag})
    RETURN r.rule_id    AS rule_id,
           r.framework  AS framework,
           r.domain     AS domain,
           r.rule_text  AS rule_text,
           r.priority   AS priority
    ORDER BY r.priority
    """
    with get_driver().session() as session:
        return session.run(query, tag=tag).data()


def get_graph_stats() -> dict[str, Any]:
    """Return node and relationship counts for health checks / dashboard."""
    query = """
    MATCH (n)
    WITH labels(n)[0] AS label, count(*) AS cnt
    RETURN label, cnt ORDER BY cnt DESC
    """
    with get_driver().session() as session:
        nodes = session.run(query).data()
        edges = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]
        return {"nodes": {n["label"]: n["cnt"] for n in nodes}, "total_relationships": edges}


def search_rules(text: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Full-text search across rule_text using CONTAINS.
    For production, consider a full-text index.
    """
    query = """
    MATCH (r:Rule)
    WHERE toLower(r.rule_text) CONTAINS toLower($text)
    RETURN r.rule_id    AS rule_id,
           r.framework  AS framework,
           r.domain     AS domain,
           r.rule_text  AS rule_text,
           r.priority   AS priority
    ORDER BY r.priority
    LIMIT $limit
    """
    with get_driver().session() as session:
        return session.run(query, text=text, limit=limit).data()
