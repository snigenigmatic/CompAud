"""Quick script to test the /analyze endpoint with the demo ZIP."""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = REPO_ROOT / "docs" / "rakshak-demo-evidence.zip"
BASE_URL = "http://localhost:8000"


def main():
    if not ZIP_PATH.exists():
        print(f"ERROR: ZIP file not found at {ZIP_PATH}")
        sys.exit(1)

    print(f"Uploading {ZIP_PATH.name} to {BASE_URL}/analyze ...")

    with open(ZIP_PATH, "rb") as f:
        response = httpx.post(
            f"{BASE_URL}/analyze",
            files={"file": (ZIP_PATH.name, f, "application/zip")},
            timeout=120.0,
        )

    print(f"Status: {response.status_code}")

    if response.status_code != 200:
        print(f"Error: {response.text[:500]}")
        sys.exit(1)

    data = response.json()

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    summary = data["summary"]
    print(f"  Total controls: {summary['total_controls']}")
    print(f"  Ready: {summary['ready_count']}")
    print(f"  Partial: {summary['partial_count']}")
    print(f"  Needs Prep: {summary['needs_prep_count']}")
    print(f"  Total gaps: {summary['total_gap_count']}")
    print(f"  Top questions: {summary['top_auditor_questions'][:2]}")

    print(f"\n{'='*60}")
    print("CONTROLS")
    print(f"{'='*60}")
    for c in data["controls"]:
        scores = c.get("scores", {})
        print(f"\n  {c['id']} | {c['name']}")
        print(f"    Status: {c['status']} | Confidence: {c['confidence']}")
        print(f"    Scores: letter={scores.get('letter_of_law', 'N/A')}, "
              f"spirit={scores.get('spirit_of_law', 'N/A')}, "
              f"effort={scores.get('compliance_effort', 'N/A')}")
        if c.get("llm_reasoning"):
            print(f"    LLM Reasoning: {c['llm_reasoning'][:150]}...")
        if c.get("regulatory_citations"):
            print(f"    Regulatory Citations: {c['regulatory_citations'][:3]}")
        print(f"    Reviewer Q: {c['reviewer_question'][:120]}")
        print(f"    Suggestion: {c['suggestion'][:120]}")
        if c.get("gaps"):
            print(f"    Gaps: {c['gaps']}")

    print(f"\n{'='*60}")
    print("AGENT TRACE")
    print(f"{'='*60}")
    for t in data.get("agent_trace", []):
        print(f"  [{t['status']}] {t['agent']}: {t['summary']}")

    out_path = REPO_ROOT / "analysis_result.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nFull result saved to {out_path}")


if __name__ == "__main__":
    main()
