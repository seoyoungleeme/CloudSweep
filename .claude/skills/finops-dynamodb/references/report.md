# finops-dynamodb — Report Template

```markdown
# FinOps DynamoDB Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | DynamoDB capacity or billing mode inefficiency |
| Affected Resources | X of Y tables / GSIs |
| Provisioned Capacity | X RCU / Y WCU |
| Actual Usage | avg/p95/max RCU/WCU and utilization |
| Monthly Waste | $XX estimated |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<billing mode, capacity, GSI, Auto Scaling, table class, retention-adjacent features>

### Metrics
<consumed RCU/WCU, p95/max, throttling, traffic pattern>

### Cost Report
<monthly spend table, pricing note, capacity vs non-capacity breakdown>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, with savings source and assumptions.

## Optimized Terraform
<real resource-based optimized Terraform>
```
