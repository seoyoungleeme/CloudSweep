# finops-elb — Report Template

```markdown
# FinOps ELB Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Idle or potentially unused load balancers |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<LB type, listeners, target groups, DNS, WAF, certificates, tags>

### Metrics
<request, connection, bytes, LCU, healthy host evidence>

### Cost Report
<fixed and variable cost assumptions>

## Root Cause
<architecture or lifecycle cause>

## Proposed Solution

### Immediate Actions
1. Verify dependencies and owner approval.
2. Drain traffic and remove DNS safely.
3. Delete only confirmed idle load balancers and dependent resources.

### Preventive Actions
1. Enforce owner/environment/purpose tags.
2. Add teardown automation for ephemeral environments.
3. Alert on sustained zero traffic and missing ownership.

## Estimated Monthly Savings
$XX.XX, separated into fixed LB-hour and LCU savings.

## Optimized Terraform
<real resource-based optimized Terraform or cleanup plan>
```
