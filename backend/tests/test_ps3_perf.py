import time

import pytest

from app.agents.ps3_linker import link_from_scores, score_matrix
from app.agents.ps3_quality import evaluate_quality
from app.agents.ps3_report import build_ps3_report
from app.scripts.ps3_perf import _scale_evidence, _scale_requirements
from app.services.ps3_evidence_loader import load_evidence_csv
from app.services.ps3_requirement_service import load_requirements


@pytest.mark.slow
def test_pipeline_handles_500_requirements_5000_evidence_under_60s():
    requirements = _scale_requirements(load_requirements(), 500)
    evidence = _scale_evidence(load_evidence_csv(), 5000)
    assert len(requirements) == 500
    assert len(evidence) == 5000

    start = time.perf_counter()
    sims = score_matrix(evidence, requirements)
    link_result = link_from_scores(evidence, requirements, sims)
    statuses = evaluate_quality(requirements, evidence, link_result)
    build_ps3_report(
        request_id="perf",
        generated_at="2026-06-13",
        requirements=requirements,
        evidence=evidence,
        link_result=link_result,
        statuses=statuses,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 60.0, f"pipeline took {elapsed:.1f}s (>60s)"
    assert len(link_result.links) + len(link_result.orphan_evidence_ids) == 5000
