# finops-s3 — Report Template

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
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX by savings source.

## Optimized Terraform
<real lifecycle configuration or review plan>
```
