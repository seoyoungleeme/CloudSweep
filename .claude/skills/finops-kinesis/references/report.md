# finops-kinesis — Report Template

```markdown
# FinOps Kinesis Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Kinesis EFO, shard, retention, or billing mode inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<stream mode, shard count, EFO consumers, retention, downstream consumers>

### Metrics
<throughput, throttling, iterator age, lag, retrieval, traffic pattern>

### Cost Report
<monthly spend and pricing assumptions>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, separated by EFO, shard, retention, and mode-change savings.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```
