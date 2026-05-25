# finops-rds — Report Template

```markdown
# FinOps RDS Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | RDS instance, availability, storage, or commitment inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<engine, class, Multi-AZ, storage, backups, replicas, RI coverage>

### Metrics
<CPU, memory, connections, IOPS, latency, storage, replica/failover evidence>

### Cost Report
<instance, Multi-AZ, storage, IOPS, backup, Extended Support, RI cost>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, separated by savings source.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```
