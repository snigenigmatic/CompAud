"""Generate the sample audit report deliverable (JSON + PDF).

Run: ./.venv/Scripts/python.exe -m app.scripts.ps3_report_sample
Writes docs/ps3_sample_report.json and docs/ps3_sample_report.pdf at repo root.
"""

from __future__ import annotations

from app.agents.ps3_pdf import render_report_pdf
from app.config import REPO_ROOT
from app.services.ps3_service import run_ps3_analysis


def main() -> None:
    report = run_ps3_analysis("sample-audit-report")
    out_dir = REPO_ROOT / "docs"

    json_path = out_dir / "ps3_sample_report.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    pdf_path = out_dir / "ps3_sample_report.pdf"
    pdf_path.write_bytes(render_report_pdf(report))

    s = report.summary
    print(f"Wrote {json_path}")
    print(f"Wrote {pdf_path}")
    print(
        f"{s.total_requirements} requirements | {s.compliant_count} compliant / "
        f"{s.partial_count} partial / {s.gap_count} gap | "
        f"compliance {s.overall_compliance_pct}% coverage {s.coverage_pct}% "
        f"freshness {s.freshness_pct}% auto {s.auto_collected_pct}%"
    )


if __name__ == "__main__":
    main()
