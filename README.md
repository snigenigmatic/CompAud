# CompAud — Automated Compliance Evidence Collection & Audit (PS3)

Parses policy documents into structured requirements, auto-collects evidence, links it to
requirements **semantically** (no fake id-join), evaluates each requirement's compliance with
**freshness-vs-audit-frequency SLAs** and confidence, and produces an **auditor-ready report
(JSON + PDF)** plus a dashboard. Built on FastAPI, LangGraph, and Next.js.

## Rubric mapping (100 pts)

| Criterion | Pts | Where |
|---|---|---|
| Policy Extraction | 25 | `app/agents/ps3_policy_parser.py` → 9 requirements, frameworks + audit-frequency SLAs |
| Evidence Linking | 25 | `app/agents/ps3_linker.py` + `ps3_embeddings.py` — local embeddings, framework tiebreak, **no id-join** |
| Report Quality | 20 | `app/agents/ps3_report.py` + `ps3_pdf.py` — narratives cite evidence ids, JSON & PDF |
| Automation | 15 | `app/collectors/` — CloudTrail + bucket collectors, ~100% auto-collected |
| Performance | 10 | 500 reqs × 5k evidence in ~23s (`app/scripts/ps3_perf.py`) |
| Bonus | 5 | Multi-framework filter on the dashboard (`/ps3`) |

## The three data traps we audited and avoided

The provided data has traps that punish the obvious approach. We verified each (see the notebook / `PS3_BUILD_BRIEF.md`) and designed around them:

1. **The requirement key is phantom.** `requirement_id` has 381 fake ids and `requirement_description` is the *same string on all 500 rows*. Neither joins to the 9 real requirements. → We **ignore both columns** (the `Evidence` model has no field for them) and link by embedding similarity of `evidence_type` against requirement text + expected evidence source, with framework agreement as a tiebreak.
2. **`anomaly_marker` is unlearnable noise.** A 5-line rule reconstructs it at ~11% — below the 74% "always clean" base rate. → We **ignore it** and derive `COMPLIANT/PARTIAL/GAP` from the real columns (`freshness_days` vs the requirement's SLA, `confidence_score`, `status`) as transparent, auditable rules.
3. **`evidence_summary` is 100% templated** ("Audit log showing N records collected" on every row) → carries no signal. → We embed the **evidence_type** descriptor, not the summary.

> Talking point: *"We audited the provided labels and found them inconsistent with the underlying evidence, so we derived auditable status from real fields instead of fitting noise."*

## Signature chain (audit-frequency → freshness → status)

Policy audit frequency sets a freshness SLA: `Continuous/Daily=1d, Weekly=7d, Monthly=30d, Quarterly=90d`.
Example end-to-end: *"Data-in-transit (TLS) must be **Continuous** (≤1 day fresh); the linked manual evidence is 153 days old → stale → PARTIAL. A CloudTrail TLS event collected 1 day ago is within SLA → COMPLIANT."* Adding the fresh automated CloudTrail evidence flips 2 encryption requirements from PARTIAL to COMPLIANT.

## Architecture

```
policy_documents.txt ─► ps3_policy_parser ─► Requirement[] (9)
                                                   │
                                                   ▼
CloudTrailCollector ┐                              
BucketCollector     ┴► Evidence[] ─► embed ─► link (cosine + framework) ─► quality/freshness ─► report (JSON + PDF)
```
LangGraph pipeline: `load_requirements → collect_evidence → embed → link_evidence → evaluate_quality → generate_narratives → assemble_report` (`app/agents/ps3_graph.py`). LLM (OpenAI, optional) is used **only** for narratives + executive summary, never for status decisions; deterministic fallbacks everywhere.

## Run it

**Backend** (Python 3.12, [uv](https://docs.astral.sh/uv/)):
```bash
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
```
Key PS3 endpoints: `GET /ps3/requirements`, `POST /ps3/analyze`, `GET /ps3/analyze/stream` (SSE), `GET /ps3/report.pdf`.

**Frontend** (Next.js 16, Node 20+):
```bash
cd frontend
pnpm install          # or npm install
pnpm dev              # http://localhost:3000  (PS3 dashboard is the homepage)
```
The dashboard streams the analysis, shows requirement status chips, evidence + freshness + confidence detail, a framework filter, and a Download-PDF button.

**Notebook:** `notebooks/ps3_compliance_demo.ipynb` (run from repo root with the backend venv kernel). Set `OPENAI_ENABLED=true` for LLM narratives.

**Tests & perf:**
```bash
cd backend
uv run pytest                              # full suite
uv run pytest -m slow                      # end-to-end + perf
uv run python -m app.scripts.ps3_perf      # 500 reqs × 5k evidence timing
uv run python -m app.scripts.ps3_tune_threshold   # link-score distribution
uv run python -m app.scripts.ps3_report_sample    # writes docs/ps3_sample_report.{json,pdf}
```

## Configuration (env / `.env`)
`OPENAI_ENABLED`, `OPENAI_MODEL` · `PS3_EMBEDDING_MODEL` (default `BAAI/bge-small-en-v1.5`) ·
`PS3_LINK_THRESHOLD` (0.42) · `PS3_CONFIDENCE_FLOOR` (0.7) · `PS3_FRESHNESS_DEFAULT_SLA` (90) ·
`PS3_LLM_NARRATIVES` (true). Embeddings are local (no API); if the model can't load, the linker
falls back to TF-IDF.

## Deploy (your own Modal + Vercel)
The backend is Modal-ready (`backend/modal_app.py`: PS3 deps, baked `bge-small`, data mounts) and
the frontend deploys to Vercel. Full fresh-deploy steps (auth, env vars, CORS): **`docs/ps3_deployment.md`**.

## Deliverables
- GitHub repo (this) · Jupyter notebook (`notebooks/`) · sample report JSON+PDF (`docs/ps3_sample_report.*`)
- Collector architecture / scaling doc (`docs/ps3_collector_architecture.md`, `docs/ps3_scaling.md`)
- Demo script (`docs/SCRIPT.md`)
