# Scaling: from the 500-row sample to production (5k+ evidence, 500+ requirements)

## Measured today
500 requirements × 5,000 evidence runs the deterministic pipeline (embed → link → quality →
report) in **~23s** on CPU — within the 60s target. Breakdown: embedding ~22.5s, linking 0.25s,
quality 0.08s, report 0.06s. **Embedding dominates; everything else is sub-second.**

Why it stays fast:
- **One batched `encode()`** for all evidence + a cached encode for requirements (normalised embeddings).
- **One matmul** for the full cosine matrix (`evidence @ requirements.T`), then vectorised argmax — no per-pair Python loop.
- Quality rules are per-row pure arithmetic; LLM narration is per-*requirement* (≤ hundreds), never per-evidence.

## Where it goes at production scale

| Concern | Sample (now) | Production move |
|---|---|---|
| Embedding throughput | CPU, ~22s for 5k | Batch on GPU, or cache embeddings by `evidence_type` (only ~10 distinct descriptors → encode once, reuse). Persist embeddings so re-runs skip encoding. |
| Requirement set (500+) | 9 tiled | Precompute + cache requirement embeddings (already `@lru_cache`d); partition linking **by framework** so each evidence row only scores its framework's requirements. |
| Evidence volume (5k → millions) | in-memory list | Stream from the collectors; embed + link in batches; store links in a DB/vector index (FAISS/pgvector) and do ANN top-k instead of a dense matmul. |
| Collection | read local files | `boto3 cloudtrail.lookup_events(StartTime=watermark)` paginated; `s3.list_objects_v2`; schedule per audit frequency (EventBridge / cron). Incremental via a per-collector `since` watermark. |
| LLM narratives | 1 batched call | Generate narratives only for changed requirements; cache by (status, evidence-set hash). Status itself never needs the LLM. |
| Freshness recompute | per run | Cheap; can run continuously as new evidence streams in (event-driven). |

## Partition-by-framework sketch
For N requirements and M evidence, dense scoring is O(N·M). Bucketing by `framework` makes it
O(Σ Nᶠ·Mᶠ) — typically far smaller, and embarrassingly parallel across frameworks/workers. The
linker already filters/boosts on framework, so this is a grouping change, not a logic change.

## Integrity & audit trail at scale
Dedupe on a stable source key (CloudTrail `eventID`, S3 `ETag`); store an evidence hash and the
`source`/collector so every linked item is traceable back to where and when it was collected.
