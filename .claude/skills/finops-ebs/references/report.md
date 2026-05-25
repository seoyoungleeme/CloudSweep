# finops-ebs — Report Template

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
1. Verify AMI, launch template, AWS Backup, DLM, legal hold, owner dependencies.
2. Delete only snapshots that pass verification.
3. Archive long-term retention snapshots where cost modeling supports it.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, separated into deletion, archive, and FSR savings.

## Optimized Terraform
<real resource-based optimized Terraform or cleanup plan>
```
