from collections import Counter

import pytest
from pydantic import ValidationError

from app.agents.ps3_linker import link_evidence
from app.models.ps3 import Evidence
from app.services.ps3_evidence_loader import load_evidence_csv
from app.services.ps3_requirement_service import load_requirements


@pytest.fixture(scope="module")
def requirements():
    return load_requirements()


@pytest.fixture(scope="module")
def evidence():
    return load_evidence_csv()


@pytest.fixture(scope="module")
def result(evidence, requirements):
    return link_evidence(evidence, requirements)


def test_evidence_model_structurally_excludes_poisoned_columns():
    # The two data traps cannot leak in: there is no field to id-join or to fit a label on.
    base = {"evidence_id": "EVD00001"}
    Evidence(**base)  # valid
    for poisoned in ("requirement_id", "requirement_description", "anomaly_marker"):
        with pytest.raises(ValidationError):
            Evidence(**base, **{poisoned: "x"})


def test_loader_drops_poisoned_columns(evidence):
    assert len(evidence) == 500
    sample = evidence[0].model_dump()
    for poisoned in ("requirement_id", "requirement_description", "anomaly_marker"):
        assert poisoned not in sample


def test_every_row_is_linked_or_orphaned(result, evidence):
    assert len(result.links) + len(result.orphan_evidence_ids) == len(evidence)
    linked_ids = {link.evidence_id for link in result.links}
    assert linked_ids.isdisjoint(set(result.orphan_evidence_ids))


def test_link_confidence_in_range(result):
    assert all(0.0 <= link.link_confidence <= 1.0 for link in result.links)


def test_discriminative_types_map_to_expected_policy(result, evidence, requirements):
    req_policy = {r.id: r.policy_id for r in requirements}
    link_policy = {link.evidence_id: req_policy[link.requirement_id] for link in result.links}
    ev_type = {e.evidence_id: e.evidence_type for e in evidence}

    expected = {
        "Encryption_Cert": "POL-ENC-001",
        "Access_Report": "POL-AC-001",
        "Audit_Log": "POL-AUD-001",
    }
    for etype, policy in expected.items():
        policies = Counter(
            link_policy[eid] for eid, t in ev_type.items() if t == etype and eid in link_policy
        )
        assert policies, f"no links for {etype}"
        top_policy, _ = policies.most_common(1)[0]
        assert top_policy == policy, f"{etype}: expected {policy}, got {policies}"


def test_coverage_gaps_and_orphans_are_computed(result, requirements):
    linked_req_ids = {link.requirement_id for link in result.links}
    for gap_id in result.coverage_gap_ids:
        assert gap_id not in linked_req_ids
    assert set(result.coverage_gap_ids).issubset({r.id for r in requirements})
