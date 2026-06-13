"""
Load compliance_rules.json and control_requirements.json into Neo4j Aura
as a fully connected knowledge graph.

Graph Model
-----------
Nodes:
  (:Framework)         — RBI, CERT-In, DPDP, PCI-DSS  (4)
  (:SourceDocument)    — 7 official regulatory documents
  (:Rule)              — 96 individual compliance rules
  (:Domain)            — 17 compliance domains
  (:SubDomain)         — sub-categories within domains
  (:EvidenceType)      — 87 types of evidence required
  (:ApplicableEntity)  — 28 entity types subject to rules
  (:Priority)          — P1_Critical, P2_High, P3_Medium
  (:Control)           — 7 Rakshak controls from control_requirements.json
  (:Tag)               — 312 keyword tags

Relationships:
  (:Framework)-[:PUBLISHES]->(:SourceDocument)
  (:Rule)-[:BELONGS_TO]->(:Framework)
  (:Rule)-[:FROM_DOCUMENT]->(:SourceDocument)
  (:Rule)-[:IN_DOMAIN]->(:Domain)
  (:Rule)-[:IN_SUBDOMAIN]->(:SubDomain)
  (:Domain)-[:HAS_SUBDOMAIN]->(:SubDomain)
  (:Rule)-[:REQUIRES_EVIDENCE]->(:EvidenceType)
  (:Rule)-[:APPLIES_TO]->(:ApplicableEntity)
  (:Rule)-[:HAS_PRIORITY]->(:Priority)
  (:Rule)-[:CROSS_REFERENCES]->(:Framework)
  (:Rule)-[:TAGGED_WITH]->(:Tag)
  (:Control)-[:GOVERNED_BY]->(:Rule)
  (:Control)-[:UNDER_FRAMEWORK]->(:Framework)

Usage:
  python -m app.knowledge.neo4j_loader          (from backend/)
  python backend/app/knowledge/neo4j_loader.py  (from repo root)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = REPO_ROOT / "compliance_rules.json"
CONTROLS_PATH = REPO_ROOT / "docs" / "control_requirements.json"

# Maps each Rakshak control to the rule domains + sub-domains + tags it covers.
# Used to create (:Control)-[:GOVERNED_BY]->(:Rule) edges.
CONTROL_TO_RULE_MAPPING: dict[str, dict[str, list[str]]] = {
    "FT-IAM-01": {
        "domains": ["Authentication", "Access_Control"],
        "sub_domains": ["MFA_Enforcement", "MFA_Implementation", "MFA_For_Privileged_Users", "MFA_For_Remote_Access"],
        "tags": ["MFA", "multi_factor_authentication", "authentication"],
    },
    "FT-IAM-02": {
        "domains": ["Access_Control"],
        "sub_domains": ["User_Account_Review", "Need_Based_Access", "Privileged_User_Monitoring"],
        "tags": ["privileged", "access_review", "privileged_access"],
    },
    "FT-DPDP-01": {
        "domains": ["Consent_Management"],
        "sub_domains": ["Consent_Withdrawal_Mechanism", "Consent_Manager_Registration", "Privacy_Notice"],
        "tags": ["consent", "consent_withdrawal", "data_principal"],
    },
    "FT-DPDP-02": {
        "domains": ["Cryptography", "Data_Protection"],
        "sub_domains": ["Strong_Cryptographic_Standards", "Disk_Level_Encryption", "SAD_Encryption"],
        "tags": ["encryption", "TLS", "AES", "key_rotation", "tokenization", "PAN"],
    },
    "FT-VAPT-01": {
        "domains": ["Vulnerability_Management"],
        "sub_domains": ["VA_PT_Frequency", "Vulnerability_Remediation", "Authenticated_Scanning"],
        "tags": ["VAPT", "vulnerability", "penetration_test", "ASV", "CVE"],
    },
    "FT-LOG-01": {
        "domains": ["Logging_and_Monitoring", "Data_Retention"],
        "sub_domains": ["Log_Retention", "Automated_Log_Review", "Minimum_Retention_Period"],
        "tags": ["log_retention", "180_days", "SIEM", "logging"],
    },
    "FT-IR-01": {
        "domains": ["Incident_Response"],
        "sub_domains": ["Breach_Notification", "Incident_Escalation_and_Reporting", "Incident_Cooperation"],
        "tags": ["incident_reporting", "6_hours", "CERT-In_notification"],
    },
}


def _load_json(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _clear_graph(tx):
    """Wipe all nodes and relationships so reloads are idempotent."""
    tx.run("MATCH (n) DETACH DELETE n")


def _create_constraints(tx):
    """Unique constraints for fast MERGE and data integrity."""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Framework) REQUIRE f.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Rule) REQUIRE r.rule_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (dm:Domain) REQUIRE dm.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (sd:SubDomain) REQUIRE sd.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (e:EvidenceType) REQUIRE e.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:ApplicableEntity) REQUIRE a.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Priority) REQUIRE p.level IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Control) REQUIRE c.control_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Tag) REQUIRE t.name IS UNIQUE",
    ]
    for c in constraints:
        tx.run(c)


def _load_frameworks_and_documents(tx, rules: list[dict]):
    """Create Framework and SourceDocument nodes with PUBLISHES edges."""
    fw_docs: dict[str, set[str]] = {}
    for r in rules:
        fw = r["framework"]
        doc = r["source_document"]
        fw_docs.setdefault(fw, set()).add(doc)

    for fw, docs in fw_docs.items():
        tx.run("MERGE (f:Framework {name: $name})", name=fw)
        for doc in docs:
            tx.run(
                """
                MERGE (d:SourceDocument {name: $doc})
                WITH d
                MATCH (f:Framework {name: $fw})
                MERGE (f)-[:PUBLISHES]->(d)
                """,
                doc=doc,
                fw=fw,
            )


def _load_lookup_nodes(tx, rules: list[dict]):
    """Create Domain, SubDomain, Priority, EvidenceType, ApplicableEntity, Tag nodes."""
    domains: set[str] = set()
    subdomains: set[str] = set()
    priorities: set[str] = set()
    evidence_types: set[str] = set()
    entities: set[str] = set()
    tags: set[str] = set()
    domain_subdomain: set[tuple[str, str]] = set()

    for r in rules:
        dom = r["domain"]
        sub = r["sub_domain"]
        domains.add(dom)
        subdomains.add(sub)
        domain_subdomain.add((dom, sub))
        priorities.add(r["priority"])
        evidence_types.update(r.get("evidence_required", []))
        entities.update(r.get("applicability", []))
        tags.update(r.get("tags", []))

    for d in domains:
        tx.run("MERGE (:Domain {name: $name})", name=d)
    for s in subdomains:
        tx.run("MERGE (:SubDomain {name: $name})", name=s)
    for ds in domain_subdomain:
        tx.run(
            """
            MATCH (d:Domain {name: $dom}), (s:SubDomain {name: $sub})
            MERGE (d)-[:HAS_SUBDOMAIN]->(s)
            """,
            dom=ds[0],
            sub=ds[1],
        )
    for p in priorities:
        tx.run("MERGE (:Priority {level: $level})", level=p)
    for e in evidence_types:
        tx.run("MERGE (:EvidenceType {name: $name})", name=e)
    for a in entities:
        tx.run("MERGE (:ApplicableEntity {name: $name})", name=a)
    for t in tags:
        tx.run("MERGE (:Tag {name: $name})", name=t)


def _load_rules(tx, rules: list[dict]):
    """Create Rule nodes with all scalar properties and connect to lookup nodes."""
    for r in rules:
        tx.run(
            """
            MERGE (rule:Rule {rule_id: $rule_id})
            SET rule.framework          = $framework,
                rule.framework_version  = $framework_version,
                rule.source_document    = $source_document,
                rule.section_number     = $section_number,
                rule.section_title      = $section_title,
                rule.clause_reference   = $clause_reference,
                rule.page_number        = $page_number,
                rule.rule_text          = $rule_text,
                rule.domain             = $domain,
                rule.sub_domain         = $sub_domain,
                rule.obligation_type    = $obligation_type,
                rule.frequency          = $frequency,
                rule.deadline_or_sla    = $deadline_or_sla,
                rule.penalty            = $penalty,
                rule.priority           = $priority
            """,
            rule_id=r["rule_id"],
            framework=r["framework"],
            framework_version=r["framework_version"],
            source_document=r["source_document"],
            section_number=r["section_number"],
            section_title=r["section_title"],
            clause_reference=r["clause_reference"],
            page_number=r.get("page_number", 0),
            rule_text=r["rule_text"],
            domain=r["domain"],
            sub_domain=r["sub_domain"],
            obligation_type=r["obligation_type"],
            frequency=r["frequency"],
            deadline_or_sla=r.get("deadline_or_sla", "Not_Specified"),
            penalty=r.get("penalty", ""),
            priority=r["priority"],
        )

        # Framework edge
        tx.run(
            """
            MATCH (rule:Rule {rule_id: $rid}), (f:Framework {name: $fw})
            MERGE (rule)-[:BELONGS_TO]->(f)
            """,
            rid=r["rule_id"],
            fw=r["framework"],
        )

        # SourceDocument edge
        tx.run(
            """
            MATCH (rule:Rule {rule_id: $rid}), (d:SourceDocument {name: $doc})
            MERGE (rule)-[:FROM_DOCUMENT]->(d)
            """,
            rid=r["rule_id"],
            doc=r["source_document"],
        )

        # Domain edge
        tx.run(
            """
            MATCH (rule:Rule {rule_id: $rid}), (d:Domain {name: $dom})
            MERGE (rule)-[:IN_DOMAIN]->(d)
            """,
            rid=r["rule_id"],
            dom=r["domain"],
        )

        # SubDomain edge
        tx.run(
            """
            MATCH (rule:Rule {rule_id: $rid}), (s:SubDomain {name: $sub})
            MERGE (rule)-[:IN_SUBDOMAIN]->(s)
            """,
            rid=r["rule_id"],
            sub=r["sub_domain"],
        )

        # Priority edge
        tx.run(
            """
            MATCH (rule:Rule {rule_id: $rid}), (p:Priority {level: $prio})
            MERGE (rule)-[:HAS_PRIORITY]->(p)
            """,
            rid=r["rule_id"],
            prio=r["priority"],
        )

        # Evidence edges
        for ev in r.get("evidence_required", []):
            tx.run(
                """
                MATCH (rule:Rule {rule_id: $rid}), (e:EvidenceType {name: $ev})
                MERGE (rule)-[:REQUIRES_EVIDENCE]->(e)
                """,
                rid=r["rule_id"],
                ev=ev,
            )

        # Applicability edges
        for app in r.get("applicability", []):
            tx.run(
                """
                MATCH (rule:Rule {rule_id: $rid}), (a:ApplicableEntity {name: $app})
                MERGE (rule)-[:APPLIES_TO]->(a)
                """,
                rid=r["rule_id"],
                app=app,
            )

        # Cross-framework edges
        for xf in r.get("cross_framework_tags", []):
            if xf != r["framework"]:
                tx.run(
                    """
                    MATCH (rule:Rule {rule_id: $rid}), (f:Framework {name: $xf})
                    MERGE (rule)-[:CROSS_REFERENCES]->(f)
                    """,
                    rid=r["rule_id"],
                    xf=xf,
                )

        # Tag edges
        for tag in r.get("tags", []):
            tx.run(
                """
                MATCH (rule:Rule {rule_id: $rid}), (t:Tag {name: $tag})
                MERGE (rule)-[:TAGGED_WITH]->(t)
                """,
                rid=r["rule_id"],
                tag=tag,
            )


def _load_controls(tx, controls: list[dict]):
    """Create Control nodes from control_requirements.json and link to Framework."""
    for ctrl in controls:
        # Extract framework name from regulation_story
        story = ctrl.get("regulation_story", "")
        frameworks = []
        for fw in ["RBI", "CERT-In", "DPDP", "PCI-DSS", "NPCI"]:
            if fw in story:
                frameworks.append(fw if fw != "NPCI" else "PCI-DSS")

        tx.run(
            """
            MERGE (c:Control {control_id: $cid})
            SET c.name             = $name,
                c.priority         = $priority,
                c.regulation_story = $story,
                c.mission          = $mission,
                c.demo_status      = $demo_status
            """,
            cid=ctrl["id"],
            name=ctrl["name"],
            priority=ctrl["priority"],
            story=story,
            mission=ctrl["mission"],
            demo_status=ctrl.get("demo_status_target", ""),
        )

        for fw in frameworks:
            tx.run(
                """
                MATCH (c:Control {control_id: $cid})
                MERGE (f:Framework {name: $fw})
                MERGE (c)-[:UNDER_FRAMEWORK]->(f)
                """,
                cid=ctrl["id"],
                fw=fw,
            )


def _link_controls_to_rules(tx):
    """Create (:Control)-[:GOVERNED_BY]->(:Rule) edges using domain/sub-domain/tag mapping."""
    for control_id, mapping in CONTROL_TO_RULE_MAPPING.items():
        domains = mapping["domains"]
        sub_domains = mapping["sub_domains"]
        tags = mapping["tags"]

        # Link by domain match
        for dom in domains:
            tx.run(
                """
                MATCH (c:Control {control_id: $cid})
                MATCH (rule:Rule)-[:IN_DOMAIN]->(:Domain {name: $dom})
                MERGE (c)-[:GOVERNED_BY]->(rule)
                """,
                cid=control_id,
                dom=dom,
            )

        # Link by sub-domain match (catches rules the domain match might miss)
        for sub in sub_domains:
            tx.run(
                """
                MATCH (c:Control {control_id: $cid})
                MATCH (rule:Rule)-[:IN_SUBDOMAIN]->(:SubDomain {name: $sub})
                MERGE (c)-[:GOVERNED_BY]->(rule)
                """,
                cid=control_id,
                sub=sub,
            )


def load_knowledge_graph(
    uri: str,
    user: str,
    password: str,
    *,
    clear_first: bool = True,
) -> dict[str, int]:
    """
    Connect to Neo4j Aura and load the full compliance knowledge graph.

    Returns a summary dict with node/edge counts.
    """
    rules = _load_json(RULES_PATH)
    controls = _load_json(CONTROLS_PATH)

    logger.info("Connecting to Neo4j Aura at %s ...", uri)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    logger.info("Connected successfully.")

    with driver.session() as session:
        if clear_first:
            logger.info("Clearing existing graph data...")
            session.execute_write(_clear_graph)

        logger.info("Creating constraints...")
        session.execute_write(_create_constraints)

        logger.info("Loading frameworks and source documents...")
        session.execute_write(_load_frameworks_and_documents, rules)

        logger.info("Loading lookup nodes (domains, priorities, evidence types, tags)...")
        session.execute_write(_load_lookup_nodes, rules)

        logger.info("Loading %d rules with relationships...", len(rules))
        session.execute_write(_load_rules, rules)

        logger.info("Loading %d controls...", len(controls))
        session.execute_write(_load_controls, controls)

        logger.info("Linking controls to governing rules...")
        session.execute_write(_link_controls_to_rules)

        # Collect stats
        stats = session.run(
            """
            MATCH (n) WITH labels(n)[0] AS label, count(*) AS cnt
            RETURN label, cnt ORDER BY cnt DESC
            """
        ).data()
        edge_count = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]

    driver.close()

    summary = {s["label"]: s["cnt"] for s in stats}
    summary["_total_relationships"] = edge_count
    logger.info("Knowledge graph loaded: %s", summary)
    return summary


def main():
    """CLI entry point — reads creds from .env or environment variables."""
    import os
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    uri = os.environ.get("NEO4J_URI", "")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")

    if not uri or not password:
        logger.error("Set NEO4J_URI and NEO4J_PASSWORD in .env or environment.")
        sys.exit(1)

    summary = load_knowledge_graph(uri, user, password)
    print("\n=== Knowledge Graph Summary ===")
    for label, count in sorted(summary.items()):
        print(f"  {label:.<30} {count}")


if __name__ == "__main__":
    main()
