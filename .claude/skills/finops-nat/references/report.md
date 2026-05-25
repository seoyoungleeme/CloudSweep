# finops-nat — Report Template

```markdown
# FinOps NAT Gateway Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Avoidable NAT Gateway data processing or hourly cost |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<NATs, routes, endpoints, endpoint policies, subnet/AZ placement>

### Metrics and Flow Logs
<NAT bytes, service mix, cross-AZ evidence, endpoint traffic>

### Cost Report
<NAT hourly, NAT data processing, endpoint, and transfer cost assumptions>

## Root Cause
<architecture or route governance cause>

## Proposed Solution

### Immediate Actions
1. Add or fix gateway endpoints for S3/DynamoDB where evidence supports it.
2. Model interface endpoints for high-volume supported AWS services.
3. Preserve NAT until remaining egress is verified.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX, separated into NAT data processing, NAT hourly, and endpoint net savings.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```
