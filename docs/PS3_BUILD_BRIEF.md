# Technical Design & Data Analysis — CompAud

This document covers the key technical decisions made during development of CompAud: the data analysis that shaped the approach, the component design, and the audit-frequency → freshness SLA mapping that is the system's signature feature.

---

## 1. Data Analysis Findings

Before writing any code, we performed a full exploratory analysis of the provided dataset. This revealed three critical characteristics that shaped the entire system design.

### Finding 1 — The requirement key is phantom

`evidence_artifacts.csv` has a `requirement_id` column with **381 distinct fake IDs** and a `requirement_description` field that is **identical on all 500 rows** (`"Data access must be logged and reviewed"`). Neither column joins to the 9 real requirements in `policy_documents.txt` — the two files were generated independently.

**Design decision:** ignore both columns entirely. The `Evidence` model has no field for them, making the mistake structurally impossible downstream. Evidence is linked to requirements **semantically**, using embedding similarity of the evidence type against requirement text.

### Finding 2 — `anomaly_marker` is statistical noise

`anomaly_marker` exists (~26% anomalous, 74% clean), but it is statistically independent of the columns that should define it: `STALE_EVIDENCE` is uncorrelated with `freshness_days`, `UNREVIEWED_EVIDENCE` spans all review statuses, `COMPLIANCE_GAP` is not tied to `Rejected` status. A 5-line business rule reconstructs it at **11% accuracy** — worse than always guessing "clean" (74% base rate). No model can predict it; any classifier collapses to predicting clean.

**Design decision:** ignore `anomaly_marker` entirely. Compliance status is derived from the **real columns** (`freshness_days`, `confidence_score`, `status`) as transparent, auditable business rules. If asked why we diverged from the provided labels: *"We audited them and found them inconsistent with the underlying evidence attributes — STALE labels were uncorrelated with freshness_days. We derived auditable status from real fields instead of fitting noise."*

### Finding 3 — `evidence_summary` is 100% templated

All 500 `evidence_summary` values follow the identical template: `"Audit log showing N records collected"`. This field carries no discriminative signal for linking.

**Design decision:** embed the `evidence_type` field using a semantic descriptor (e.g. `Encryption_Cert` → `"encryption certificate, key management, AES, TLS, data encryption at rest and in transit"`) rather than the summary. This is what makes discriminative linking possible.

---

## 2. Verified Dataset Facts

### policy_documents.txt — 3 policies, 9 requirements

Each requirement has labelled fields: Responsible, Scope, Evidence Source, **Audit Frequency**, Compliance Mapping. There are no requirement IDs in the source — CompAud mints them as `<POLICY_ID>-R<n>`.

| Minted ID | Requirement | Audit Frequency | Frameworks |
|---|---|---|---|
| POL-ENC-001-R1 | Data at rest encrypted AES-256+ | Monthly | GDPR, NIST, PCI-DSS |
| POL-ENC-001-R2 | Encryption keys rotated ≥ annually | Quarterly | NIST, ISO 27001 |
| POL-ENC-001-R3 | Data in transit TLS 1.2+ | Continuous | GDPR, NIST |
| POL-AC-001-R1 | Admin access requires MFA | Daily | NIST, CIS |
| POL-AC-001-R2 | Least privilege on all access | Quarterly | NIST, SOX |
| POL-AC-001-R3 | Privileged accounts: no personal use | Monthly | NIST, CIS |
| POL-AUD-001-R1 | All sensitive-data access logged | Daily | GDPR, NIST, SOX |
| POL-AUD-001-R2 | Logs retained ≥ 90 days | Monthly | NIST, PCI-DSS |
| POL-AUD-001-R3 | Log access restricted & monitored | Weekly | NIST, ISO 27001 |

### evidence_artifacts.csv — 500 rows, 13 real columns

The usable columns (the three poisoned columns are excluded from the schema entirely):

| Column | Values |
|---|---|
| `evidence_id` | EVD##### (500 unique) — real key |
| `framework` | HIPAA, ISO27001, PCI-DSS, SOX, GDPR, NIST |
| `evidence_type` | 10 types: Encryption_Cert, Access_Report, Audit_Log, Training_Record, Configuration_Snapshot, Test_Result, Screenshot, Report, Policy_Document, Procedure_Evidence |
| `freshness_days` | 0–179 |
| `confidence_score` | 0.50–1.00 |
| `status` | Approved, Rejected, Pending_Review, Needs_Update |
| `collection_date`, `collected_by`, `collector_email`, `reviewed_by`, `reviewer_email`, `review_date`, `evidence_location` | Audit trail fields |

---

## 3. Component Design

### Policy Parser

Parses `policy_documents.txt` → list of `Requirement` objects using a deterministic regex skeleton (the file is well-structured). Field extraction is case-insensitive to handle a known inconsistency (`scope:` is lowercased on one requirement). Frameworks are normalised from the Compliance Mapping field. An optional LLM pass polishes requirement text but the regex extraction is the authoritative path. Output is validated against the 9-requirement ground truth by automated test.

### Semantic Evidence Linker

For each of the 500 evidence rows, finds the best-matching requirement among the 9. Process:
1. Build evidence text from the `evidence_type` semantic descriptor.
2. Build requirement text from `text + scope + evidence_source`.
3. Encode both sets with a local `BAAI/bge-small-en-v1.5` model in a single batched call.
4. Compute the full cosine similarity matrix (single matrix multiply, no per-pair loop).
5. Add a small framework agreement bonus (0.05) as a tiebreak — not a hard gate, since framework coverage only partially overlaps between evidence and policies.
6. Assign each item to its argmax requirement above a configurable threshold; below threshold → `unmapped`.

Derived findings: requirements with zero linked evidence (coverage gaps), evidence linking to nothing (orphans).

### Evidence-Quality + Freshness Engine

Per evidence row, transparent rules from real columns only:

| Flag | Rule |
|---|---|
| `stale` | `freshness_days > requirement.freshness_sla_days` |
| `low_confidence` | `confidence_score < 0.70` |
| `unreviewed` | `status == Pending_Review` |
| `rejected` | `status == Rejected` |
| `acceptable` | `status == Approved` AND not stale AND not low_confidence |

Per-requirement aggregate status:
- **COMPLIANT** — ≥1 acceptable linked evidence item
- **PARTIAL** — linked evidence exists but only with caveats (stale / low-confidence / pending)
- **GAP** — no acceptable evidence (none linked, or all rejected)

Status is fully explainable from the evidence attributes alone. `anomaly_marker` is never read.

### Report Generator

Produces a `PS3ReportResponse` (JSON) and a ReportLab PDF. A single batched LLM call writes all 9 per-requirement narratives and an executive summary from the pre-computed deterministic facts; every narrative must cite evidence IDs. A templated deterministic fallback is used when the LLM is unavailable — status is never decided by the LLM.

### Evidence Collectors

Two collectors implementing a common `Collector(since) → list[Evidence]` abstract base:

- **BucketCollector** — reads CSV/PDF files from a local directory (simulating S3/GCS). This is how `evidence_artifacts.csv` arrives in the pipeline.
- **CloudTrailCollector** — reads a JSON file of CloudTrail-shaped event records, maps 7 KMS/encryption/TLS event types to `Encryption_Cert` evidence. Non-encryption events are filtered.

---

## 4. Audit-Frequency → Freshness SLA Mapping

The policy's `Audit Frequency` field drives each requirement's evidence freshness SLA. This is the signature chain: a policy decision propagates all the way through to compliance status.

| Audit Frequency | freshness_sla_days |
|---|---|
| Continuous | 1 |
| Daily | 1 |
| Weekly | 7 |
| Monthly | 30 |
| Quarterly | 90 |

Example end-to-end: *"The policy says TLS evidence must be Continuous (≤1 day). The best manually-collected evidence is 153 days old → stale → PARTIAL. A CloudTrail TLS certificate renewal collected 1 day ago is within SLA → COMPLIANT, cited to that event ID."* This chain — policy frequency → freshness SLA → staleness flag → status → narrative — demonstrates every component working together.
