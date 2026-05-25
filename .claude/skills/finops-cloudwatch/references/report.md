# finops-cloudwatch — Report Template

```markdown
# FinOps CloudWatch Log Group Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | CloudWatch Logs missing or excessive retention policy |
| Affected Resources | X of Y log groups |
| Monthly Waste | $XX estimated storage waste |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<retention settings, environment/data-class inference, invalid Terraform attributes>

### Metrics
<stored bytes and ingestion table; active vs silent groups>

### Cost Report
<monthly spend table, pricing note, region/pricing assumptions>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX from storage reduction only; ingestion unchanged unless separately optimized.

## Optimized Terraform
<real resource-based optimized Terraform>
```
