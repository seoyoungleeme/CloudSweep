# finops-s3 — Detailed Rules

## Pipeline Scripts (standalone mode only)

If Python is available:
```bash
python SKILL_DIR/scripts/parser.py    --tf <main.tf> --metrics <metrics.json> --cost <cost_report.json> --out WORK_DIR/parsed_input.json
python SKILL_DIR/scripts/analyzer.py  --input WORK_DIR/parsed_input.json --rules SKILL_DIR/rules/missing_lifecycle_policy.json --out WORK_DIR/findings.json
python SKILL_DIR/scripts/formatter.py --findings WORK_DIR/findings.json --original-tf <main.tf> --out WORK_DIR/finops_report.md
```

Orchestrator subagent mode: pipeline scripts require full file paths — skip
and apply detection rules manually using the inline slices.

If Python is unavailable, manually apply the rules.

## Lifecycle Baselines (defaults, not absolute rules)

| Environment / Data Class | Noncurrent Expiry | Versions Kept | Multipart Abort |
|--------------------------|-------------------|---------------|-----------------|
| dev / test | 14-30 days | 2-3 | 3 days |
| staging | 30-60 days | 3 | 3-7 days |
| prod application data | 60-180 days | 5-10 | 7 days |
| audit / compliance / legal hold | Org policy first | Policy-defined | Policy-defined |
| unknown | 30 days provisional | 3 | 7 days |

If environment or data class is unknown, report the lifecycle as a review
candidate and require owner validation before applying.

## Deep Architectural Analysis

### Infrastructure
- Bucket count, versioning status, lifecycle config, Object Lock, replication,
  encryption, logging, tags.
- Whether existing lifecycle rules include noncurrent expiration, noncurrent
  transitions, current expiration, multipart abort.

### Metrics
- Noncurrent version count: first/last/slope.
- Storage bytes and storage class mix.
- Incomplete multipart upload evidence.
- Replication, restore, or access evidence when provided.

### Cost
- Monthly S3 spend trend.
- Current vs noncurrent storage cost, storage class cost, requests, retrieval,
  replication, early-deletion effects.
- Region pricing — prefer cost report or aws-pricing MCP.

### Root Cause (lifecycle governance frame)
- Versioning enabled without matching lifecycle expiration.
- Backup/rollback retention requirements not encoded in Terraform.
- Multipart uploads not being aborted.
- Data classification tags missing, preventing safe lifecycle policy.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → noncurrent storage GB × storage-class
pricing → rule fallback.

Separate savings by source: noncurrent expiration, multipart abort, storage
class transition, request/retrieval changes. Do not count savings if Object
Lock or retention policy blocks expiration.

## Optimized Terraform Rules

- No placeholders; preserve original bucket resources.
- Add lifecycle blocks only for buckets where retention evidence supports it.
- If Object Lock, legal hold, compliance, backup, or replication evidence is
  present or unknown, add a commented review plan instead of aggressive expiration.
- Include `abort_incomplete_multipart_upload` where safe.
- Recommend governance tags where missing.

## Preventive Actions

1. Require lifecycle policy with versioning.
2. Require data classification and retention tags.
3. Review S3 Storage Lens / CUR storage class trends monthly.
