"""Semantic evidence linker (PS3 Evidence Linking, 25 pts).

Links each evidence row to the best-matching requirement using embedding
cosine similarity, with a small framework-agreement bonus as a tiebreak (NOT a
hard gate — evidence frameworks and policy frameworks only partially overlap,
e.g. HIPAA evidence has no policy, CIS policies have no evidence). Never reads
requirement_id / requirement_description / anomaly_marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.agents.ps3_embeddings import similarity_matrix
from app.config import get_settings
from app.models.ps3 import Evidence, LinkedEvidence, Requirement


@dataclass
class LinkResult:
    links: list[LinkedEvidence] = field(default_factory=list)
    orphan_evidence_ids: list[str] = field(default_factory=list)
    coverage_gap_ids: list[str] = field(default_factory=list)

    def links_for(self, requirement_id: str) -> list[LinkedEvidence]:
        return [link for link in self.links if link.requirement_id == requirement_id]


# EDA finding: evidence_summary is 100% templated ("Audit log showing N records
# collected" on all 500 rows) and carries no discriminative signal, so it is NOT
# embedded. The evidence_type is the real "what does this prove" signal; we map
# each type to descriptive terms so the embedding can match it against the
# requirement text + its Evidence Source field. This is domain description of the
# evidence categories, not a hardcoded type->requirement table.
EVIDENCE_TYPE_DESCRIPTORS: dict[str, str] = {
    "Encryption_Cert": "encryption certificate, key management, AES, TLS, data encryption at rest and in transit, SSL certificate",
    "Access_Report": "user access report, access rights review, least privilege, identity and access management, permissions, MFA",
    "Audit_Log": "audit log, logging and monitoring, access logging, sensitive data access events, log records",
    "Training_Record": "security awareness training record for personnel",
    "Configuration_Snapshot": "system configuration snapshot, security settings, hardening baseline",
    "Test_Result": "security test result, validation test, vulnerability scan",
    "Screenshot": "screenshot of a configuration or dashboard",
    "Report": "compliance report summary",
    "Policy_Document": "policy document, standard, written procedure",
    "Procedure_Evidence": "documented operating procedure, process control evidence",
}


def _humanize(token: str) -> str:
    return token.replace("_", " ").replace("-", " ").strip()


def requirement_text_for_embedding(req: Requirement) -> str:
    return " ".join(part for part in (req.text, req.scope, req.evidence_source) if part).strip()


def evidence_text_for_embedding(ev: Evidence) -> str:
    return EVIDENCE_TYPE_DESCRIPTORS.get(ev.evidence_type, _humanize(ev.evidence_type))


def score_matrix(evidence: list[Evidence], requirements: list[Requirement]) -> np.ndarray:
    """Cosine similarity matrix [n_evidence, n_requirements]."""
    req_texts = [requirement_text_for_embedding(req) for req in requirements]
    ev_texts = [evidence_text_for_embedding(ev) for ev in evidence]
    return similarity_matrix(ev_texts, req_texts)


def link_from_scores(
    evidence: list[Evidence],
    requirements: list[Requirement],
    sims: np.ndarray,
    threshold: float | None = None,
    framework_bonus: float | None = None,
) -> LinkResult:
    """Assign each evidence row to its best requirement given a score matrix.

    framework agreement adds a small bonus (tiebreak), it is not a hard gate.
    """
    settings = get_settings()
    threshold = settings.link_similarity_threshold if threshold is None else threshold
    framework_bonus = settings.framework_match_bonus if framework_bonus is None else framework_bonus

    if not requirements:
        return LinkResult(orphan_evidence_ids=[ev.evidence_id for ev in evidence])
    if not evidence:
        return LinkResult(coverage_gap_ids=[req.id for req in requirements])

    req_frameworks = [set(req.frameworks) for req in requirements]
    links: list[LinkedEvidence] = []
    orphans: list[str] = []
    linked_requirement_ids: set[str] = set()

    for i, ev in enumerate(evidence):
        cosines = sims[i]
        bonuses = np.array(
            [framework_bonus if ev.framework in req_frameworks[j] else 0.0 for j in range(len(requirements))]
        )
        scored = cosines + bonuses
        best = int(np.argmax(scored))

        if float(scored[best]) < threshold:
            orphans.append(ev.evidence_id)
            continue

        best_cosine = float(cosines[best])
        links.append(
            LinkedEvidence(
                evidence_id=ev.evidence_id,
                requirement_id=requirements[best].id,
                link_confidence=round(max(0.0, min(1.0, best_cosine)), 4),
                framework_match=ev.framework in req_frameworks[best],
            )
        )
        linked_requirement_ids.add(requirements[best].id)

    coverage_gaps = [req.id for req in requirements if req.id not in linked_requirement_ids]
    return LinkResult(links=links, orphan_evidence_ids=orphans, coverage_gap_ids=coverage_gaps)


def link_evidence(
    evidence: list[Evidence],
    requirements: list[Requirement],
    threshold: float | None = None,
    framework_bonus: float | None = None,
) -> LinkResult:
    if not requirements:
        return LinkResult(orphan_evidence_ids=[ev.evidence_id for ev in evidence])
    if not evidence:
        return LinkResult(coverage_gap_ids=[req.id for req in requirements])
    sims = score_matrix(evidence, requirements)
    return link_from_scores(evidence, requirements, sims, threshold, framework_bonus)
