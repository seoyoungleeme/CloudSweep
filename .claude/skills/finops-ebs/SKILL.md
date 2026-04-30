---
name: finops-ebs
description: >
  FinOps EBS Snapshot Analysis Skill. Detects potentially orphaned, stale, or
  over-retained Amazon EBS snapshots using Terraform, inventory tags, metrics,
  and AWS cost reports. Use for aws_ebs_snapshot resources and related snapshot
  lifecycle evidence.
user_invocable: false
---

# FinOps EBS Snapshot Analysis Skill

## Scope

Analyze EBS snapshot cost from a FinOps perspective. The goal is to reduce
unnecessary snapshot storage, archive eligible long-term backups, and improve
lifecycle governance without deleting recovery points that are still required
for AMIs, launch templates, AWS Backup, disaster recovery, audit, legal hold, or
compliance.

Important safety rule:

Do not recommend immediate snapshot deletion based only on
`SourceVolumeStatus = deleted`. A deleted source volume is a strong cleanup
signal, but snapshots may still be required by AMIs, launch templates, recovery
runbooks, AWS Backup recovery points, DLM policies, legal holds, or retention
policy.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_ebs_snapshot` resources and related lifecycle resources | Cannot analyze; ask user for path |
| `metrics.json` | Snapshot storage size, age, archive tier, FSR, restore/access evidence when provided | Mark metrics section as unavailable |
| `cost_report.json` | Monthly EBS snapshot cost history and pricing notes | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/orphaned_snapshot.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| S1 | Source volume deleted and no dependency evidence is present | HIGH | REVIEW_DELETE |
| S2 | Snapshot is referenced by AMI, launch template, AWS Backup, DLM, or legal/compliance tag | INFO | DO_NOT_DELETE |
| S3 | Snapshot is older than archive threshold and retained for long-term backup | MEDIUM | CONSIDER_ARCHIVE |
| S4 | Fast Snapshot Restore enabled without restore/launch need | MEDIUM | REVIEW_FSR_DISABLE |
| S5 | Snapshot lacks owner, retention, or purpose tags | MEDIUM | ADD_GOVERNANCE_TAGS |

### Required Deletion Checks

Before reporting a snapshot as confirmed savings, require evidence for as many
checks as the provided files allow:

- No AMI references the snapshot.
- No launch template, autoscaling group, image pipeline, or golden image process
  depends on the snapshot.
- It is not managed by AWS Backup or DLM with a documented retention policy.
- It is not tagged for legal hold, audit, compliance, disaster recovery, or
  business retention.
- A recent recovery point exists if the workload still needs backup coverage.
- Owner approval is required for destructive cleanup.

If those checks are not present in the files, mark savings as potential and
state what must be verified.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total snapshot count and affected snapshot count.
- Source volume status, snapshot age, snapshot size, storage tier, FSR status,
  and tags such as Owner, Environment, Retention, Purpose, BackupPolicy,
  SourceVolumeStatus, LegalHold, and Compliance.
- Related backup/lifecycle resources such as AWS Backup plans, DLM policies, or
  custom cleanup automation when present.

### 3.2 Metric and Inventory Evidence

- Snapshot storage GB and observation period.
- Snapshot age and last restore/access evidence when provided.
- Archive tier status and Fast Snapshot Restore configuration when provided.

### 3.3 Cost Evidence

- Monthly EBS snapshot spend trend.
- Region-specific snapshot standard storage price, archive price, restore price,
  and FSR cost when available.
- Separate standard snapshot storage savings, archive-tier savings, FSR savings,
  and any restore/retrieval costs.

### 3.4 Root Cause

Frame root cause as a lifecycle governance issue, such as:

- Volumes were deleted without snapshot cleanup review.
- Snapshot retention is tag-based but required tags are missing.
- DLM/AWS Backup policies create recovery points but lifecycle expiration is not
  aligned with business retention.
- Long-term backups are left in the standard tier instead of an archive tier.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like snapshot line items.
2. Use provided snapshot storage GB and region-specific pricing.
3. Use static fallback pricing in the rule file only as an estimate.

Formula:

```text
standard_snapshot_cost = snapshot_storage_gb * standard_snapshot_price_per_gb_month
archive_delta_savings = standard_snapshot_cost - archive_storage_cost - expected_restore_cost
delete_savings = standard_snapshot_cost + removable_fsr_cost
```

Do not count archive savings when expected restore/retrieval charges or minimum
archive duration would erase the benefit.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Do not remove snapshot resources directly unless dependency and retention
  evidence is complete in the provided files.
- For deletion candidates, comment the resource and add explicit verification
  commands/checks instead of silently deleting it.
- For long-term retention candidates, recommend archive or DLM/AWS Backup
  lifecycle changes rather than deletion.
- Add missing governance tags where appropriate: Owner, Environment, Purpose,
  RetentionDays, BackupPolicy, and CostCenter.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps EBS Snapshot Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Potential orphaned or over-retained EBS snapshots |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<snapshot status, tags, dependencies, lifecycle evidence>

### Metrics and Inventory
<snapshot size, age, tier, FSR, access/restore evidence>

### Cost Report
<monthly cost and pricing assumptions>

## Root Cause
<lifecycle governance cause>

## Proposed Solution

### Immediate Actions
1. Verify AMI, launch template, AWS Backup, DLM, legal hold, and owner dependencies.
2. Delete only snapshots that pass verification.
3. Archive long-term retention snapshots where cost modeling supports it.

### Preventive Actions
1. Enforce snapshot owner/purpose/retention tags.
2. Use AWS Data Lifecycle Manager or AWS Backup lifecycle expiration.
3. Review snapshot cost, FSR usage, and archive candidates monthly.

## Estimated Monthly Savings
$XX.XX, separated into deletion, archive, and FSR savings.

## Optimized Terraform
<real resource-based optimized Terraform or cleanup plan>
```

Generated by: finops-ebs skill
