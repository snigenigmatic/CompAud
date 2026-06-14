# 5-minute demo script

**One-liner:** *"CompAud turns a pile of policy docs and raw evidence into an auditor-ready
compliance report — and it does it by refusing to trust the data's misleading fields."*

### 0:00 — The problem (20s)
"Auditors ask: for each policy requirement, is there fresh, trustworthy evidence? Today that's
weeks of manual spreadsheet work. We automate it: parse → collect → link → evaluate → report."

### 0:20 — The twist: we audited the data first (45s)  ← differentiator
Open the notebook's Phase-0 cell.
- "The CSV ships a `requirement_id` and `requirement_description` — but the description is the
  **same string on all 500 rows**, and the ids are fake. Joining on them links 500 rows to nothing."
- "It also ships an `anomaly_marker` label. We tested it: a rule reproduces it at **11%** — worse
  than always guessing 'clean'. It's noise. We **don't fit it.**"
- "So we link **semantically** and derive status from **real** fields. That's the whole game."

### 1:05 — Policy extraction (30s)
`GET /ps3/requirements` (or notebook cell 2). "9 requirements parsed from 3 policies, each with its
frameworks and — key — its **audit frequency**, which becomes a freshness SLA."

### 1:35 — Automated collection + linking (45s)
Dashboard homepage (`/`) → "Run compliance analysis". Watch the live pipeline stream.
- "Two collectors — a mock S3 bucket (the CSV) and **CloudTrail** — 100% auto-collected, zero manual entry."
- "We embed each evidence item's *type* against the requirements; the templated summary is ignored
  because it's identical on every row. Encryption certs land on encryption requirements, access
  reports on access control."

### 2:20 — The signature chain: freshness (60s)  ← the memorable moment
Click **POL-ENC-001-R3 (Data in transit / TLS)**.
- "This is a **Continuous** requirement — evidence must be ≤1 day old. The linked manual evidence is
  153 days old → **stale** → it can't make this COMPLIANT on its own."
- "But our **CloudTrail** collector pulled a TLS cert renewal **1 day ago** — within SLA — so the
  requirement is **COMPLIANT**, cited to that event id. Automation directly closes the gap."

### 3:20 — A real gap (30s)
Click the **GAP** requirement (MFA). "No evidence maps here. The report says exactly what's missing:
*expected Azure AD Configuration and Login Logs.* That's an actionable finding, not a mystery label."

### 3:50 — The report (45s)
Click **Download PDF**. "Executive summary, per-requirement status, every claim cites an evidence id,
freshness and next-review dates. JSON for systems, PDF for auditors."
- Metrics strip: "55% compliant, 89% coverage, 100% automated."
- Framework filter (bonus): pick **PCI-DSS** → multi-framework view.

### 4:35 — Scale & honesty (25s)
"500 requirements × 5,000 evidence in ~23 seconds. And if a judge asks about the provided labels:
we audited them, found them inconsistent with the evidence, and chose auditable rules over fitting
noise. That's the difference between a demo and an audit tool."

---
**Backup if the live run hiccups:** `docs/ps3_sample_report.pdf` is a pre-generated report; the
original Rakshak `/demo/golden` route still works as a fallback.
