# CompAud Backend

FastAPI backend for the CompAud compliance readiness demo.

## Structure

The backend uses a simple MVC-style layout:

- `app/controllers/`: FastAPI route controllers.
- `app/services/`: application use cases and catalog loading.
- `app/models/`: Pydantic request/response and internal data models split by domain.
- `app/agents/`: deterministic Evidence, Compliance, Risk, Auditor, Report, and LangGraph orchestration agents.
- `app/main.py`: FastAPI app assembly, middleware, exception handlers, and router registration.

Model modules are intentionally small:

- `base.py`: shared strict `APIModel` base.
- `system.py`: health response.
- `errors.py`: structured API errors.
- `controls.py`: control catalog requirements.
- `evidence.py`: evidence artifacts, chunks, packages, and citations.
- `compliance.py`: raw evidence-element evaluation results.
- `risk.py`: readiness status, confidence, and gaps.
- `auditor.py`: reviewer guidance and tool trace entries.
- `analysis.py`: final frontend-facing analysis response.
- `schemas.py`: compatibility exports only.

## Dev Commands

Run these from `backend/`:

```bash
uv run compaud-api
uv run compaud-phoenix
uv run compaud-dev
uv run compaud-openapi --output openapi.json
uv run pytest
```

Command purpose:

- `compaud-api`: starts FastAPI on `API_HOST` / `API_PORT`.
- `compaud-phoenix`: starts local Phoenix for traces.
- `compaud-dev`: starts Phoenix and FastAPI together.
- `compaud-dev --no-phoenix`: starts only FastAPI through the same dev runner.
- `compaud-openapi`: exports the OpenAPI spec for HeyAPI.


## Checkpoint 0

This checkpoint initializes the backend project with:

- FastAPI app
- environment-driven settings
- `GET /health`
- pytest setup
- Phoenix/OpenAI configuration placeholders

## Checkpoint 1

This checkpoint adds the deterministic control catalog foundation:

- typed Pydantic models for `docs/control_requirements.json`
- cached control requirement loading
- `GET /controls`
- tests that lock the current seven FT controls

## Checkpoint 2

This checkpoint adds the Evidence Agent foundation:

- in-memory ZIP, CSV, TXT, LOG, and JSON parsing
- unsafe ZIP path rejection
- unsupported artifact type rejection
- `EvidenceArtifact`, `EvidenceChunk`, and `EvidencePackage` models
- stable chunk provenance with artifact, location, text, normalized text, hash, and parsed CSV fields

## Checkpoint 3

This checkpoint adds the Compliance Agent foundation:

- deterministic matching of control evidence elements against target artifacts
- positive term matching with citations
- negative term matching with blocking hits
- missing term reporting
- per-control `element_results` for the Risk Agent checkpoint

## Checkpoint 4

This checkpoint adds the Risk Agent foundation:

- converts compliance element results into `Ready`, `Partial`, or `Needs Prep`
- applies the documented demo-specific blocker rules
- computes deterministic confidence scores
- emits reviewer gap strings for the Auditor Agent checkpoint
- preserves the current seven-control demo status story

## Checkpoint 5

This checkpoint adds the Auditor Agent foundation:

- selects reviewer-facing questions from control requirements
- applies deterministic demo guidance for suggestions and risk summaries
- emits agent plans and summary-only tool traces
- avoids putting raw uploaded evidence content into auditor tool traces

## Checkpoint 6

This checkpoint adds the Report Agent foundation:

- assembles `AnalysisResponse` for the frontend
- computes summary counts and top auditor questions
- emits control-level report fields with evidence provenance
- emits safe agent trace summaries
- exposes `GET /demo/golden` for frontend work before upload analysis

## Checkpoint 7

This checkpoint adds the upload analysis endpoint:

- `POST /analyze`
- multipart upload field: `file`
- supports ZIP, CSV, TXT, LOG, and JSON evidence
- returns the same `AnalysisResponse` shape as `GET /demo/golden`
- rejects unsafe ZIP paths, empty uploads, and unsupported file types cleanly

## Checkpoint 8

This checkpoint adds Phoenix/OpenTelemetry observability:

- startup config for Phoenix OTLP tracing
- one `analysis.request` span per analysis
- spans for Evidence, Compliance, Risk, Auditor, and Report agents
- one `control.<FT-ID>.evaluate` span per control evaluation
- safe span attributes only: IDs, counts, status metadata, and error type
- tests use a fake tracer and do not require a live Phoenix server

## Checkpoint 9

This checkpoint adds the LangGraph orchestration skeleton:

- `AnalysisState` typed state
- sequential LangGraph nodes for controls, Evidence, Compliance, Risk, Auditor, and Report
- `/demo/golden` and `/analyze` now run through the graph-backed pipeline
- deterministic agent logic remains unchanged
- tests lock the graph node order and final response shape

## Checkpoint 10

This checkpoint tightens the API contract before frontend SDK generation:

- stable OpenAPI operation IDs for HeyAPI
- route tags and summaries
- structured `ErrorResponse` for known upload errors
- documented `400` and `415` responses on `POST /analyze`
- OpenAPI tests for the frontend-facing contract

Run locally:

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run tests:

```bash
uv run pytest
```
