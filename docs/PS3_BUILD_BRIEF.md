# PS3 Build Brief — Automated Compliance Evidence Collection & Audit

**Audience:** Claude Code (autonomous build agent).
**Source of truth:** the three data files (`policy_documents.txt`, `evidence_artifacts.csv`, and the organizer markdown docs). The CSV/TXT data files are authoritative. **The organizer markdown docs (`PROBLEM_STATEMENT_03.md`, `README.md`) are NOT reliable about schema, counts, or relationships** — read them only for intent and rubric. Every schema/relationship claim below was verified against the actual files. Where this brief and the org docs disagree, this brief wins.

**Hackathon constraints:** 30-hour build. Existing base: RakshakAI (agentic compliance copilot — FastAPI + LangGraph backend, Next.js/TS frontend). Reuse it where noted.

---

## 0. How to use this doc

1. Do **Phase 0** (section 3) first — run the verification script against the real files and confirm the two traps yourself before writing any feature code.
2. Treat section 2 (Hard Constraints) as non-negotiable. An agent will *naturally* try to (a) join evidence to policies on `requirement_id` and (b) train a classifier on `anomaly_marker`. Both are wrong on this data. Don't.
3. Build in the order in section 7. Each component in section 6 has acceptance criteria — meet them before moving on.

---

## 1. Goal and what "winning" means

Build a system that parses policy documents into structured requirements, links collected evidence to those requirements, evaluates each requirement's compliance status (with freshness and confidence), and generates an auditor-ready report on demand.

**Official rubric (100 pts) — optimize for THIS, not the self-eval sidebar:**

| Criterion | Pts | What it rewards |
|---|---|---|
| Policy Extraction | 25 | Parse requirements from policy text, >85% accuracy |
| Evidence Linking | 25 | Link evidence to requirements, minimal false matches |
| Report Quality | 20 | Clear narratives, audit-ready format, confidence scores |
| Automation | 15 | ≥70% evidence auto-collected; ≥2 integrations (mock OK) |
| Performance | 10 | 500 reqs + 5k evidence in <60s (trivial here) |
| Bonus | 5 | Multi-framework view, trend, exception tracking |

There is a `precision>70 / recall>60` self-eval snippet in the org docs. **It is NOT in the rubric, and it is unwinnable on this data (see Trap 2). Do not optimize for it.**

---

## 2. HARD CONSTRAINTS — the two data traps

### Trap 1 — the requirement key is phantom. DO NOT id-join.

`evidence_artifacts.csv` has a `requirement_id` column with **381 distinct fake IDs** (`REQ959`, `REQ404`, …) and a `requirement_description` that is **identical on all 500 rows** (`"Data access must be logged and reviewed"`). None of this joins to the 9 real requirements in `policy_documents.txt` — the two files were generated independently.

- **DO NOT** join evidence → requirements on `requirement_id`. It links 500 rows to nothing real.
- **DO** ignore the `requirement_id` and `requirement_description` columns entirely.
- **DO** link semantically: `framework` (the one reliable real signal) + `evidence_type` + embedding similarity of `evidence_summary` against the parsed requirement text. See linker spec (6.2).

### Trap 2 — the labels are unlearnable. DO NOT train on `anomaly_marker`.

`anomaly_marker` exists (≈26% anomalous, 74% clean — *not* the 70% the docs claim), but it is **statistically independent of the columns that should define it**: `STALE_EVIDENCE` is uncorrelated with `freshness_days`, `UNREVIEWED_EVIDENCE` spans all statuses, `COMPLIANCE_GAP` is not tied to `Rejected`. A 5-line business rule reconstructs it at **11% accuracy** — worse than always guessing "clean" (74%). No rule engine and no ML model can predict it; any classifier collapses to predicting clean.

- **DO NOT** train a classifier on `anomaly_marker` or try to match it.
- **DO NOT** report precision/recall against it as a success metric.
- **DO** compute evidence-quality flags as transparent business rules from the *real* columns (`freshness_days`, `confidence_score`, `status`). See quality engine (6.3).
- **Optional talking point for judges:** if asked "did you use the provided labels?", the strong answer is: *"We audited them and found them inconsistent with the underlying evidence attributes (e.g. STALE labels uncorrelated with freshness), so we derived auditable status from the real fields instead of fitting noise."* Frame the divergence as rigor, not omission.

---

## 3. Phase 0 — verify before building (run this first)

Place the three files in a `data/` dir, then run. This confirms both traps on your copy and enumerates the categorical values you'll code against.

```python
import pandas as pd, re
ev = pd.read_csv('data/evidence_artifacts.csv')

# --- Trap 1: confirm phantom key ---
assert ev['requirement_description'].nunique() == 1, "requirement_description should be degenerate"
print("distinct requirement_ids:", ev['requirement_id'].nunique(), "(phantom — do not join)")

# --- Trap 2: confirm labels are noise ---
am = ev['anomaly_marker'].fillna('<CLEAN>')
def rule(r):
    if r['status']=='Rejected': return 'COMPLIANCE_GAP'
    if r['status']=='Pending_Review': return 'UNREVIEWED_EVIDENCE'
    if r['freshness_days']>90: return 'STALE_EVIDENCE'
    if r['status']=='Needs_Update': return 'INCOMPLETE_MAPPING'
    if r['confidence_score']<0.7: return 'LOW_CONFIDENCE'
    return '<CLEAN>'
acc = (ev.apply(rule,axis=1)==am).mean()
print(f"rule reconstructs anomaly_marker at {acc:.0%} (expect ~11%, < 74% base rate => unlearnable)")

# --- enumerate the real categorical vocab you must handle ---
for c in ['framework','evidence_type','status','anomaly_marker']:
    print(c, sorted(ev[c].fillna('<NA>').unique()))
print("confidence_score range:", ev.confidence_score.min(), ev.confidence_score.max())
print("freshness_days range:", ev.freshness_days.min(), ev.freshness_days.max())

# --- confirm 3 policies / 9 requirements ---
txt = open('data/policy_documents.txt').read()
print("policies:", re.findall(r'POLICY_ID:\s*(\S+)', txt))
print("requirement lines:", len(re.findall(r'REQUIREMENT\s+\d+:', txt)))
```

Do not proceed until the rule accuracy prints ~11% and policies print as 3 / requirements as 9. If they don't, the data changed — re-derive.

---

## 4. Verified data facts

### 4.1 `policy_documents.txt` — 3 policies, 9 requirements

Highly structured (NOT "poorly written" — the org framing overstates this). Each requirement has labeled fields: Responsible, Scope, Evidence Source, **Audit Frequency**, Compliance Mapping. The file has **no requirement IDs** — mint them as `<POLICY_ID>-R<n>` (e.g. `POL-ENC-001-R1`). This is your canonical parse target; validate the parser's output against it:

| Minted ID | Requirement (short) | Audit Frequency | Frameworks |
|---|---|---|---|
| POL-ENC-001-R1 | Data at rest encrypted AES-256+ | Monthly | GDPR Art 32, NIST SC-7, PCI-DSS 3.4 |
| POL-ENC-001-R2 | Encryption keys rotated ≥ annually | Quarterly | NIST SC-7, ISO 27001 A.10.1.1 |
| POL-ENC-001-R3 | Data in transit TLS 1.2+ | Continuous | GDPR Art 32, NIST SC-7 |
| POL-AC-001-R1 | Admin access requires MFA | Daily | NIST IA-2, CIS 5.3.1 |
| POL-AC-001-R2 | Least privilege on all access | Quarterly | NIST AC-2, AC-3, SOX 302 |
| POL-AC-001-R3 | Privileged accounts: no personal use | Monthly | NIST AC-3, CIS 4.1 |
| POL-AUD-001-R1 | All sensitive-data access logged | Daily | GDPR Art 32, NIST AU-2, SOX 302 |
| POL-AUD-001-R2 | Logs retained ≥ 90 days | Monthly | NIST AU-4, PCI-DSS 3.4 |
| POL-AUD-001-R3 | Log access restricted & monitored | Weekly | NIST AU-5, ISO 27001 A.10.2.3 |

### 4.2 `evidence_artifacts.csv` — 500 rows, 17 columns

```
evidence_id            EVD##### (500 unique)            <- real key
requirement_id         REQ### (381 phantom)             <- IGNORE (Trap 1)
requirement_description "Data access must be logged..." <- IGNORE (identical on all rows)
framework              HIPAA|ISO27001|PCI-DSS|SOX|GDPR|NIST (6)  <- linking signal
evidence_type          10 categories (e.g. Encryption_Cert, Access_Report, Training_Record, Test_Result) <- enumerate in Phase 0
collected_by / collector_email     names+emails  <- audit-trail "who"
collection_date        2025-10-23 .. 2026-04-20
freshness_days         int, 0..~180  <- precomputed; use directly for staleness
evidence_summary       free text (mostly templated)  <- embed for linking
reviewed_by / reviewer_email
review_date
evidence_location      Vault-N/Path-M
confidence_score        float 0..1  <- use for low-confidence flag
status                 Approved|Rejected|Pending_Review|Needs_Update (4)  <- use for status logic
anomaly_marker         CLEAN|COMPLIANCE_GAP|INCOMPLETE_MAPPING|UNREVIEWED_EVIDENCE|STALE_EVIDENCE|MISSING_DOCUMENTATION  <- IGNORE (Trap 2)
```

Note: `framework` is a single value per row; most requirements map to NIST-family controls, so framework alone is a weak filter — embeddings do the heavy lifting, framework is a filter/tiebreak.

---

## 5. Reuse map (RakshakAI → PS3)

| Rakshak component | PS3 use | Action |
|---|---|---|
| LangGraph agent graph | orchestration backbone | reuse |
| Compliance Agent (evidence→control) | Evidence Linking (25 pts) | **rebuild as semantic linker** — Rakshak used hardcoded rules; no join key here |
| Risk Agent (gap finder) | evidence-quality / gap detection | reuse logic, feed real-column rules |
| Report + Auditor Agents | Report Quality (20 pts) | reuse — strongest carryover |
| FastAPI + OpenAPI SDK gen | API layer | reuse |
| Next.js/TS frontend shell | dashboard | reuse |
| `compliance_rules.json` (hardcoded) | — | **discard**; requirements now come from the parser |

**Net-new:** policy parser, semantic linker, freshness-SLA logic, 2 collectors.
**Do NOT** ingest the NIST 800-53 / OSCAL catalog — requirements come from `policy_documents.txt`, which already carries framework mappings. (OSCAL is at most a bonus for validating control IDs; skip for the 30h build.)

---

## 6. Component specs

### 6.1 Policy Parser  (Rubric: Policy Extraction, 25 pts)
- Parse `policy_documents.txt` → list of `Requirement` objects: `{id (minted POL-x-Rn), policy_id, text, responsible, scope, evidence_source, audit_frequency, frameworks[], freshness_sla_days}`.
- Approach: regex for the labeled-field skeleton (the file is structured) + one LLM pass to normalize requirement text into a crisp testable statement. `frameworks[]` = split the "Compliance Mapping" line.
- Derive `freshness_sla_days` from `audit_frequency` via section 8 mapping.
- **Acceptance:** output matches the 9 rows in 4.1 (all 9 found, frameworks correct, audit_frequency correct). Print a diff against the table above.

### 6.2 Semantic Evidence Linker  (Rubric: Evidence Linking, 25 pts)
- For each of the 500 evidence rows, link to the best-matching requirement(s) among the 9.
- Signals, combined: (1) `framework` filter — evidence.framework ∈ requirement.frameworks; (2) embedding cosine between `evidence_summary` + `evidence_type` and the requirement's `text` + `scope` + `evidence_source`.
- Embeddings: use a **local** model (`BAAI/bge-small-en-v1.5` or `all-MiniLM-L6-v2`) — no API cost/latency in the dev loop.
- Pick argmax above a similarity threshold; below threshold → `unmapped`. Emit a per-link `link_confidence` = similarity (distinct from the row's own `confidence_score`).
- Two derived findings fall out for free: requirements with **zero** linked evidence = coverage gaps; evidence linking to **no** requirement = orphan evidence.
- **Acceptance:** every requirement has a ranked evidence list; spot-check 10 links look sensible (e.g. `Encryption_Cert` → encryption requirements, `Access_Report` → access/least-privilege); coverage gaps are surfaced explicitly.

### 6.3 Evidence-Quality + Freshness Engine  (feeds Report; replaces anomaly_marker)
Per evidence row, transparent rules from real columns:
- `stale` if `freshness_days > requirement.freshness_sla_days` (fallback 90d if unmapped)
- `low_confidence` if `confidence_score < 0.7` (starting threshold; expose as config)
- `unreviewed` if `status == Pending_Review`
- `rejected` if `status == Rejected`; `needs_update` if `status == Needs_Update`

Per requirement, aggregate to status:
- **COMPLIANT** — ≥1 linked evidence that is `Approved`, within freshness SLA, confidence ≥ threshold
- **PARTIAL** — linked evidence exists but only with caveats (stale / low-confidence / pending)
- **GAP** — no acceptable evidence (none linked, or all stale/rejected/low-conf/unreviewed)
- **Acceptance:** status is explainable from the evidence attributes alone; no use of `anomaly_marker`.

### 6.4 Report Generator  (Rubric: Report Quality, 20 pts)
- Per-requirement object: `{id, text, frameworks, status, freshness_sla_days, linked_evidence:[{evidence_id, type, collection_date, freshness_days, confidence_score, link_confidence}], narrative, next_review_date}`.
- Executive summary: overall compliance %, requirement coverage %, freshness %.
- LLM (reuse Rakshak's provider) generates the per-requirement narrative + exec summary. Every claim cites the `evidence_id`(s) — provenance is the point.
- Output JSON **and** PDF.
- **Acceptance:** a 10–15 requirement report renders with status, cited evidence, freshness, and a readable narrative; a GAP requirement explains *what proof is missing*.

### 6.5 Collectors  (Rubric: Automation, 15 pts)
- Define `Collector` ABC: `collect(since: datetime) -> list[RawEvidence]`, normalizing into the evidence schema the linker/quality engine consume (design that schema once).
- Ship **two** mock integrations (FAQ confirms mock + architecture is acceptable):
  - `CloudTrailCollector` — reads a JSON file of CloudTrail-shaped events, maps relevant ones (e.g. KMS config) → encryption evidence. (Satisfies the "CloudTrail + one other" line.)
  - `BucketCollector` — reads CSV/PDF dropped in a local `bucket/` dir (simulating S3/GCS) → evidence rows. This is how `evidence_artifacts.csv` itself "arrives".
- Include an architecture diagram + notes on the real version (boto3 / GCS SDK, scheduling). 
- **Acceptance:** both collectors emit normalized evidence consumed by the same pipeline; architecture doc present.

### 6.6 Dashboard
- Reuse Rakshak's Next.js shell. Views: requirement list with status chips (compliant/partial/gap), requirement detail (linked evidence + freshness + confidence + narrative), framework filter, "generate report" button.
- Multi-framework view = the +5 bonus, cheap since `framework` is right there.

---

## 7. 30-hour build order

- **H0–3** — Phase 0 verification. Policy parser → 9 requirements + freshness SLAs. EDA.
- **H3–10** — Semantic linker (framework + embeddings) → requirement↔evidence map + coverage gaps.
- **H10–16** — Evidence-quality + freshness-SLA engine → per-requirement status. Two mock collectors + architecture diagram.
- **H16–24** — Report generator (JSON + PDF, LLM narratives) + dashboard (reuse Rakshak).
- **H24–28** — PDF polish, multi-framework view (bonus), sample 10–15 requirement report.
- **H28–30** — Scaling doc (500 → 5k story: batch embeddings, partition by framework, async collectors), demo script.

---

## 8. Audit-frequency → freshness SLA mapping (the signature design)

This is the strongest, most demoable link, and it uses a field both org docs ignore — parsed policy frequency drives evidence staleness:

| Audit Frequency (in policy) | freshness_sla_days |
|---|---|
| Continuous | 1 |
| Daily | 1 |
| Weekly | 7 |
| Monthly | 30 |
| Quarterly | 90 |

Evidence with `freshness_days > sla` for its linked requirement = stale → drives PARTIAL/GAP status. Show this chain end-to-end in the demo: "the policy says MFA evidence must be Daily; this evidence is 40 days old; therefore the MFA requirement is stale."

---

## 9. Tech stack

- Backend: Python 3.11, FastAPI, LangGraph (reuse Rakshak graph), Pydantic models (`Requirement`, `Evidence`, `LinkedEvidence`, `RequirementStatus`).
- Embeddings: `sentence-transformers` (`BAAI/bge-small-en-v1.5` or `all-MiniLM-L6-v2`), local.
- LLM: reuse Rakshak's provider — used **only** for policy-text normalization and report narratives, not for linking or status.
- Frontend: Next.js + TypeScript (reuse Rakshak shell), OpenAPI-generated SDK.
- PDF: `weasyprint` or `reportlab`.
- No code comments unless asked.

---

## 10. Inoculation — organizer-doc claims that are FALSE

If you also read `PROBLEM_STATEMENT_03.md` / `README.md`, distrust these specific claims (verified false against the data):

- "6 policies" → **3** (POL-ENC-001, POL-AC-001, POL-AUD-001).
- "250+ records" / "15 samples" → **exactly 500**.
- `requirement_id` links evidence to policy requirements → **false** (381 phantom IDs; identical description).
- "~70% anomalous" → **26%**.
- `verification_status = verified/gap/pending`, ids like `EV-0015` → actual `status = Approved/Rejected/Pending_Review/Needs_Update`, ids `EVD#####`.
- precision>70 / recall>60 self-eval as a target → **unwinnable on these features and not in the rubric**.

---

## 11. Open items (confirm with the user, don't block on them)

- Local paths of the three data files (assumed `data/`).
- Starting from a Rakshak fork vs fresh scaffold (this brief assumes you can pull Rakshak's backend graph + frontend shell).
- LLM provider/key available locally for narratives.
- Whether judges run the code (performance matters) or only watch the demo.
