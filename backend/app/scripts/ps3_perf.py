"""Performance check (PS3 Performance, 10 pts): scale to 500 requirements +
5,000 evidence and time the deterministic pipeline (embed -> link -> quality ->
report). LLM narration is excluded (it is per-requirement and optional).

Run: ./.venv/Scripts/python.exe -m app.scripts.ps3_perf
"""

from __future__ import annotations

import time

from app.agents.ps3_linker import link_from_scores, score_matrix
from app.agents.ps3_quality import evaluate_quality
from app.agents.ps3_report import build_ps3_report
from app.models.ps3 import Evidence, Requirement
from app.services.ps3_evidence_loader import load_evidence_csv
from app.services.ps3_requirement_service import load_requirements

TARGET_REQUIREMENTS = 500
TARGET_EVIDENCE = 5000


def _scale_requirements(base: list[Requirement], target: int) -> list[Requirement]:
    out: list[Requirement] = []
    i = 0
    while len(out) < target:
        for req in base:
            clone = req.model_copy(update={"id": f"{req.id}-{i}"})
            out.append(clone)
            if len(out) >= target:
                break
        i += 1
    return out


def _scale_evidence(base: list[Evidence], target: int) -> list[Evidence]:
    out: list[Evidence] = []
    i = 0
    while len(out) < target:
        for ev in base:
            out.append(ev.model_copy(update={"evidence_id": f"{ev.evidence_id}-{i}"}))
            if len(out) >= target:
                break
        i += 1
    return out


def main() -> None:
    requirements = _scale_requirements(load_requirements(), TARGET_REQUIREMENTS)
    evidence = _scale_evidence(load_evidence_csv(), TARGET_EVIDENCE)
    print(f"Scaled to {len(requirements)} requirements x {len(evidence)} evidence")

    start = time.perf_counter()

    t0 = time.perf_counter()
    sims = score_matrix(evidence, requirements)
    t_embed = time.perf_counter() - t0

    t0 = time.perf_counter()
    link_result = link_from_scores(evidence, requirements, sims)
    t_link = time.perf_counter() - t0

    t0 = time.perf_counter()
    statuses = evaluate_quality(requirements, evidence, link_result)
    t_quality = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_ps3_report(
        request_id="perf",
        generated_at="2026-06-13",
        requirements=requirements,
        evidence=evidence,
        link_result=link_result,
        statuses=statuses,
    )
    t_report = time.perf_counter() - t0

    total = time.perf_counter() - start
    print(f"embed={t_embed:.2f}s  link={t_link:.2f}s  quality={t_quality:.2f}s  report={t_report:.2f}s")
    print(f"TOTAL = {total:.2f}s  (target < 60s)  links={len(link_result.links)}")


if __name__ == "__main__":
    main()
