---
name: finops-s3
description: >
  FinOps S3 Analysis Skill. Detects S3 cost waste from versioning-enabled
  buckets without safe lifecycle controls, noncurrent version accumulation,
  incomplete multipart uploads, storage-class mismatch, and lifecycle governance
  gaps using Terraform, metrics, and AWS cost reports.
user_invocable: false
---

# FinOps S3 Analysis Skill

## Scope

Analyze S3 storage lifecycle cost from a FinOps perspective. The goal is to
reduce noncurrent version accumulation and stale storage while preserving
restore windows, legal hold, Object Lock, replication, backup, audit, and
compliance requirements.

Important safety rule:

Do not add aggressive expiration policies solely from version growth. S3
`NoncurrentVersionExpiration` permanently deletes noncurrent object versions.
Validate restore, compliance, Object Lock, replication, backup, and application
rollback requirements before applying lifecycle expiration.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` for all files:

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_s3_bucket`, versioning, lifecycle, object lock, replication, encryption, logging, and tags | Cannot analyze; ask user for path |
| `metrics.json` | Storage bytes, object count, noncurrent versions, incomplete multipart uploads, storage class mix, request/restore evidence | Mark metrics section as unavailable |
| `cost_report.json` | Monthly S3 cost history with storage class, requests, retrieval, replication, and lifecycle pricing notes | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Run Pipeline Scripts

```bash
python SKILL_DIR/scripts/parser.py --tf <main.tf> --metrics <metrics.json> --cost <cost_report.json> --out WORK_DIR/parsed_input.json
python SKILL_DIR/scripts/analyzer.py --input WORK_DIR/parsed_input.json --rules SKILL_DIR/rules/missing_lifecycle_policy.json --out WORK_DIR/findings.json
python SKILL_DIR/scripts/formatter.py --findings WORK_DIR/findings.json --original-tf <main.tf> --out WORK_DIR/finops_report.md
```

If Python is unavailable, manually apply the rules below.

## Step 3 - Analyze Evidence

Apply detection rules from `rules/missing_lifecycle_policy.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| V1 | Versioning enabled, noncurrent versions growing, and no noncurrent expiration | HIGH | ADD_SAFE_LIFECYCLE_POLICY |
| V2 | Existing lifecycle lacks `abort_incomplete_multipart_upload` and incomplete uploads accumulate | MEDIUM | ADD_MULTIPART_ABORT |
| V3 | Object Lock, legal hold, compliance, replication, or backup evidence exists | INFO | DO_NOT_EXPIRE_WITHOUT_POLICY_REVIEW |
| V4 | Storage class mix suggests transition opportunity | LOW | MODEL_STORAGE_CLASS_TRANSITION |
| V5 | Missing owner, data class, retention, or cost tags | MEDIUM | ADD_GOVERNANCE_TAGS |

### Lifecycle Baselines

Use these as defaults, not absolute compliance rules:

| Environment / Data Class | Noncurrent Expiry | Versions Kept | Multipart Abort |
|--------------------------|-------------------|---------------|-----------------|
| dev / test | 14-30 days | 2-3 | 3 days |
| staging | 30-60 days | 3 | 3-7 days |
| prod application data | 60-180 days | 5-10 | 7 days |
| audit / compliance / legal hold | Organization policy first | Policy-defined | Policy-defined |
| unknown | 30 days provisional | 3 | 7 days |

If environment or data class is unknown, report the lifecycle as a review
candidate and require owner validation before applying.

## Step 4 - Deep Architectural Analysis

Cover these sections in the final report:

### 4.1 Infrastructure Evidence

- Bucket count, versioning status, lifecycle configuration, Object Lock,
  replication, encryption, logging, and tags.
- Whether existing lifecycle rules already include noncurrent expiration,
  noncurrent transitions, current expiration, and multipart abort.

### 4.2 Metrics Evidence

- Noncurrent version count first/last/slope.
- Storage bytes and storage class mix.
- Incomplete multipart upload evidence.
- Replication, restore, or access evidence when provided.

### 4.3 Cost Evidence

- Monthly S3 spend trend.
- Current vs noncurrent storage cost, storage class cost, requests, retrieval,
  replication, and early deletion effects where available.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.

### 4.4 Root Cause

Frame root cause as lifecycle governance:

- Versioning was enabled without matching lifecycle expiration.
- Backup/rollback retention requirements were not encoded in Terraform.
- Multipart uploads are not being aborted.
- Data classification tags are missing, preventing safe lifecycle policy.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like S3 line items.
2. Use noncurrent storage GB and storage-class pricing.
3. Use static fallback pricing only as an estimate.

Separate savings by source: noncurrent expiration, multipart abort, storage
class transition, and request/retrieval changes. Do not count savings if Object
Lock or retention policy blocks expiration.

## Step 5 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve original bucket resources.
- Add lifecycle blocks only for buckets where retention evidence supports it.
- If Object Lock, legal hold, compliance, backup, or replication evidence is
  present or unknown, add a commented review plan instead of an aggressive
  expiration.
- Include `abort_incomplete_multipart_upload` where safe.
- Add governance tags recommendations where missing.

## Step 6 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps S3 Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | S3 noncurrent version or lifecycle inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<versioning, lifecycle, object lock, replication, tags>

### Metrics
<noncurrent growth, storage, multipart, access/restore evidence>

### Cost Report
<storage class and lifecycle cost assumptions>

## Root Cause
<lifecycle governance cause>

## Proposed Solution

### Immediate Actions
1. Validate restore/compliance requirements.
2. Apply safe lifecycle rules.

### Preventive Actions
1. Require lifecycle policy with versioning.
2. Require data classification and retention tags.
3. Review S3 Storage Lens/CUR storage class trends monthly.

## Estimated Monthly Savings
$XX.XX by savings source.

## Optimized Terraform
<real lifecycle configuration or review plan>
```

Generated by: finops-s3 skill
