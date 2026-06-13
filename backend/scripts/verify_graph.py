"""
Verify the Neo4j knowledge graph by running agent query functions
against the live Aura instance.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

load_dotenv(REPO_ROOT / ".env")

from app.knowledge.graph import init_driver, get_graph_stats, get_regulatory_context, \
    get_controls_for_domain, get_evidence_requirements, get_full_context, \
    get_cross_framework_rules, get_rules_by_priority, search_rules, close_driver


def main():
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]

    init_driver(uri, user, password)

    print("=" * 60)
    print("1. GRAPH STATS")
    print("=" * 60)
    stats = get_graph_stats()
    for label, count in sorted(stats["nodes"].items()):
        print(f"  {label:.<30} {count}")
    print(f"  {'Total relationships':.<30} {stats['total_relationships']}")

    print("\n" + "=" * 60)
    print("2. REGULATORY CONTEXT for FT-IAM-01 (MFA)")
    print("=" * 60)
    rules = get_regulatory_context("FT-IAM-01")
    print(f"  Found {len(rules)} governing rules")
    for r in rules[:3]:
        print(f"  - [{r['rule_id']}] {r['framework']} | {r['clause_reference']}")
        print(f"    {r['rule_text'][:120]}...")

    print("\n" + "=" * 60)
    print("3. CONTROLS for Incident_Response domain")
    print("=" * 60)
    controls = get_controls_for_domain("Incident_Response")
    for c in controls:
        print(f"  - {c['control_id']}: {c['control_name']} ({c['priority']})")

    print("\n" + "=" * 60)
    print("4. EVIDENCE REQUIREMENTS for FT-DPDP-02 (Encryption)")
    print("=" * 60)
    evidence = get_evidence_requirements("FT-DPDP-02")
    print(f"  Found {len(evidence)} evidence types")
    for e in evidence[:5]:
        print(f"  - {e['evidence_type']} (from {e['rule_id']}, {e['framework']})")

    print("\n" + "=" * 60)
    print("5. CROSS-FRAMEWORK RULES referencing PCI-DSS")
    print("=" * 60)
    xrefs = get_cross_framework_rules("PCI-DSS")
    print(f"  Found {len(xrefs)} rules from other frameworks citing PCI-DSS")
    for x in xrefs[:3]:
        print(f"  - [{x['rule_id']}] {x['source_framework']} / {x['domain']}")

    print("\n" + "=" * 60)
    print("6. FULL CONTEXT for FT-IR-01 (6-Hour Incident Reporting)")
    print("=" * 60)
    ctx = get_full_context("FT-IR-01")
    ctrl = ctx["control"]
    print(f"  Control: {ctrl['control_id']} — {ctrl['name']}")
    print(f"  Frameworks: {ctrl['frameworks']}")
    print(f"  Governing rules: {len(ctx['governing_rules'])}")
    print(f"  Evidence types: {len(ctx['evidence_types'])}")
    print(f"  Cross-framework rules: {len(ctx['cross_framework_rules'])}")

    print("\n" + "=" * 60)
    print("7. P1_Critical RULES")
    print("=" * 60)
    p1 = get_rules_by_priority("P1_Critical")
    print(f"  Found {len(p1)} P1_Critical rules")
    for r in p1[:3]:
        print(f"  - [{r['rule_id']}] {r['framework']} / {r['domain']}")

    print("\n" + "=" * 60)
    print("8. SEARCH for '6 hours'")
    print("=" * 60)
    results = search_rules("6 hours", limit=5)
    print(f"  Found {len(results)} rules mentioning '6 hours'")
    for r in results:
        print(f"  - [{r['rule_id']}] {r['framework']} — {r['rule_text'][:100]}...")

    close_driver()
    print("\n[OK] All verification queries passed successfully.")


if __name__ == "__main__":
    main()
