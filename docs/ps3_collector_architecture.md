# Evidence Collector Architecture (PS3 Automation)

The system collects evidence through pluggable **Collectors**. Each collector
pulls from one source system and **normalises** its native format into the
single `Evidence` schema the linker and quality engine consume. This is what
makes ≥70% of evidence "auto-collected" — in the bundled demo, **100%** of
evidence arrives via collectors (no manual entry).

```
 Source systems            Collectors (normalise)         Pipeline
 ┌───────────────┐         ┌────────────────────┐
 │ AWS CloudTrail│ ───────▶│ CloudTrailCollector │──┐
 └───────────────┘         └────────────────────┘  │   list[Evidence]
 ┌───────────────┐         ┌────────────────────┐  ├──▶ linker ▶ quality ▶ report
 │ S3/GCS bucket │ ───────▶│ BucketCollector     │──┘
 └───────────────┘         └────────────────────┘
```

## Contract

```python
class Collector(ABC):
    name: str
    def collect(self, since: datetime | None = None) -> list[Evidence]: ...
```

`since` enables incremental collection (only evidence on/after a watermark).
Every emitted `Evidence` carries a `source` tag (`"cloudtrail"`, `"bucket:<file>"`)
so provenance — and the automation rate — is auditable.

## Shipped (mock) collectors

### CloudTrailCollector
Reads CloudTrail-shaped JSON (`{"Records":[{eventSource,eventName,eventTime,requestParameters}]}`)
and maps **encryption/KMS/TLS** events into encryption `Evidence`:

| Event | → evidence_type | framework hint |
|---|---|---|
| `kms:EnableKeyRotation` / `RotateKeyOnDemand` / `CreateKey` | Encryption_Cert | ISO27001 |
| `s3:PutBucketEncryption`, `rds:ModifyDBInstance` | Encryption_Cert | PCI-DSS |
| `acm:RenewCertificate`, `elasticloadbalancing:ModifyListener` | Encryption_Cert | GDPR |

Non-encryption events (ConsoleLogin, RunInstances, …) are ignored. `eventTime`
becomes `collection_date`/`freshness_days`; these configs come from the source
of truth, so `status=Approved`, `confidence=0.90`.

### BucketCollector
Simulates an object store. Reads files from a local `bucket/` directory; CSVs
are parsed with the **existing** `app.agents.evidence.parse_evidence_upload`
(reuse), then each row is normalised via `evidence_from_fields`. This is how
`evidence_artifacts.csv` "arrives". PDFs are recorded as `Policy_Document`
evidence.

## Productionising (the real version)

- **CloudTrail:** replace file read with `boto3` `cloudtrail.lookup_events(LookupAttributes=…, StartTime=since)` paginated; or query the CloudTrail→S3→Athena lake for scale. Same `_map_event` normaliser.
- **Bucket:** replace `iterdir()` with `boto3` `s3.list_objects_v2` + `get_object` (or `google-cloud-storage` `bucket.list_blobs`). Stream large CSVs.
- **Scheduling:** run each collector on a cadence aligned to the requirement's
  audit frequency (Continuous→event-driven via EventBridge; Daily/Weekly→cron /
  Lambda / Cloud Scheduler). Persist a per-collector `since` watermark for
  incremental pulls.
- **Idempotency & integrity:** dedupe on a stable source key (CloudTrail
  `eventID`, S3 `ETag`); store an evidence hash; keep `collector_email`/`source`
  for the audit trail.
- **Secrets:** source credentials from the platform secret manager / IAM role,
  never in code.
- **More integrations (same contract):** Okta/Azure AD (MFA & access),
  GitHub/GitLab (change control), vuln scanners (test results), HRIS (training
  records) — each a new `Collector` subclass.
