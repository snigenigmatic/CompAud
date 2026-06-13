"""Dev-only: inspect link-score distribution and per-requirement coverage at
candidate thresholds, plus spot-check sample links. Read-only over the data.

Run: ./.venv/Scripts/python.exe -m app.scripts.ps3_tune_threshold
"""

from __future__ import annotations

import numpy as np

from app.agents.ps3_embeddings import embedding_mode, similarity_matrix
from app.agents.ps3_linker import (
    evidence_text_for_embedding,
    link_evidence,
    requirement_text_for_embedding,
)
from app.services.ps3_evidence_loader import load_evidence_csv
from app.services.ps3_requirement_service import load_requirements

CANDIDATES = [0.30, 0.35, 0.40, 0.42, 0.45, 0.50]


def main() -> None:
    requirements = load_requirements()
    evidence = load_evidence_csv()
    print(f"mode={embedding_mode()}  requirements={len(requirements)}  evidence={len(evidence)}\n")

    req_texts = [requirement_text_for_embedding(r) for r in requirements]
    ev_texts = [evidence_text_for_embedding(e) for e in evidence]
    sims = similarity_matrix(ev_texts, req_texts)
    best = sims.max(axis=1)

    pct = {p: round(float(np.percentile(best, p)), 3) for p in (10, 25, 50, 75, 90, 99)}
    print("max-cosine percentiles:", pct, "\n")

    for threshold in CANDIDATES:
        result = link_evidence(evidence, requirements, threshold=threshold)
        per_req = {r.id: len(result.links_for(r.id)) for r in requirements}
        print(
            f"threshold={threshold:.2f}  linked={len(result.links)}  "
            f"unmapped={len(result.orphan_evidence_ids)}  coverage_gaps={len(result.coverage_gap_ids)}"
        )
        print("   per-requirement:", per_req)
    print()

    result = link_evidence(evidence, requirements)
    by_id = {r.id: r for r in requirements}
    print("Spot-check (default threshold):")
    for link in result.links[:12]:
        ev = next(e for e in evidence if e.evidence_id == link.evidence_id)
        req = by_id[link.requirement_id]
        print(
            f"  {ev.evidence_id} [{ev.framework}/{ev.evidence_type}] "
            f"-> {req.id} (cos={link.link_confidence:.3f}, fw_match={link.framework_match})"
        )
        print(f"      summary: {ev.evidence_summary[:90]}")
        print(f"      req:     {req.text[:90]}")


if __name__ == "__main__":
    main()
