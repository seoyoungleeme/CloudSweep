# finops-lambda — Report Template

```markdown
# FinOps Lambda Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Lambda memory, timeout, provisioned concurrency, or retry inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<memory, timeout, runtime, architecture, concurrency, storage, event source config>

### Metrics
<duration p95/p99, max memory, errors, throttles, concurrency, retry/backlog>

### Cost Report
<compute, request, provisioned concurrency, storage, and pricing assumptions>

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
<real resource-based optimized Terraform or tuning plan>
```
