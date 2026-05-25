# finops-sqs — Report Template

```markdown
# FinOps SQS Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | SQS polling, batching, or retry inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<queue settings, DLQ, visibility, event sources, tags>

### Metrics
<empty receives, request ratio, message age, backlog, DLQ/retry evidence>

### Cost Report
<request cost and pricing assumptions>

## Root Cause
<consumer or queue configuration cause>

## Proposed Solution

### Immediate Actions
1. Validate client read timeouts and latency requirements.
2. Enable long polling for flagged queues.
3. Review batching and retry behavior where relevant.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, separated by savings source.

## Optimized Terraform
<real resource-based optimized Terraform>
```
