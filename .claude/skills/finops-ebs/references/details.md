# finops-ebs — Detailed Rules

## Required Deletion Checks

Before reporting a snapshot as confirmed savings, require evidence for as many
of these as the provided files allow:
- No AMI references the snapshot.
- No launch template, ASG, image pipeline, or golden image process depends on it.
- Not managed by AWS Backup or DLM with a documented retention policy.
- Not tagged for legal hold, audit, compliance, DR, or business retention.
- A recent recovery point exists if the workload still needs backup coverage.
- Owner approval required for destructive cleanup.

If checks not present, mark savings as potential and state what must be verified.

## Deep Architectural Analysis

### Infrastructure
- Total snapshot count and affected count.
- Source volume status, snapshot age, size, storage tier, FSR status, tags
  (Owner, Environment, Retention, Purpose, BackupPolicy, SourceVolumeStatus,
  LegalHold, Compliance).
- Related lifecycle resources: AWS Backup plans, DLM policies, custom automation.

### Metric and Inventory Evidence
- Snapshot storage GB and observation period.
- Snapshot age and last restore/access evidence when provided.
- Archive tier status and Fast Snapshot Restore config.

### Cost
- Monthly EBS snapshot spend trend.
- Region-specific snapshot standard storage, archive, restore, FSR prices.
- Separate standard storage savings, archive-tier savings, FSR savings, and
  any restore/retrieval costs.

### Root Cause (lifecycle governance frame)
- Volumes deleted without snapshot cleanup review.
- Snapshot retention is tag-based but required tags are missing.
- DLM/AWS Backup creates points but lifecycle expiration misaligned with policy.
- Long-term backups left in standard tier instead of archive.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → provided snapshot GB × region price
→ rule fallback (estimate).

```
standard_snapshot_cost = snapshot_storage_gb * standard_snapshot_price_per_gb_month
archive_delta_savings  = standard_snapshot_cost - archive_storage_cost - expected_restore_cost
delete_savings         = standard_snapshot_cost + removable_fsr_cost
```

Do not count archive savings when expected restore/retrieval charges or minimum
archive duration would erase the benefit.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Do not remove snapshot resources directly unless dependency and retention
  evidence is complete.
- Deletion candidates: comment the resource and add explicit verification
  commands/checks instead of silently deleting.
- Long-term retention candidates: recommend archive or DLM/AWS Backup lifecycle
  changes rather than deletion.
- Add missing governance tags: Owner, Environment, Purpose, RetentionDays,
  BackupPolicy, CostCenter.

## Preventive Actions

1. Enforce snapshot owner/purpose/retention tags.
2. Use AWS Data Lifecycle Manager or AWS Backup lifecycle expiration.
3. Review snapshot cost, FSR usage, and archive candidates monthly.
