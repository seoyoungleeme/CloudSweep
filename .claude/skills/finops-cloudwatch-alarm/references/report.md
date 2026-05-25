# finops-cloudwatch-alarm — Report Template

```markdown
# FinOps CloudWatch Metric Alarm Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | CloudWatch Metric Alarm unnecessary high-resolution (1s) period |
| Affected Resources | X of Y alarms |
| Monthly Waste | $XX estimated excess metric cost |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<alarm count, resolution settings, namespace, evaluation period, scenario attrs>

### Metrics
<metric_count pattern per alarm; evidence for/against sub-minute need>

### Cost Report
<monthly spend table, pricing note, affected alarm count, API overhead>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. Downgrade all affected alarms from `period = 1` to `period = 60`.
2. Remove scenario-only Terraform attributes and replace with valid AWS provider attributes.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX from resolution downgrade (X alarms × $0.60/alarm/month) plus ~$Y API call reduction.

## Optimized Terraform
<real resource-based optimized Terraform>
```
