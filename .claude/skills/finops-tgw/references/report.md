# finops-tgw — Report Template

```markdown
# FinOps Transit Gateway Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Avoidable TGW data processing or attachment charges |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<TGW, attachments, VPC pairs, existing peering, route tables>

### Metrics
<bytes processed, traffic volume, AZ distribution, traffic stability>

### Cost Report
<TGW attachment, data processing, VPC, transfer cost assumptions>

## Root Cause
<architecture or routing governance cause>

## Proposed Solution

### Immediate Actions
1. Validate topology: confirm no transitive routing, inspection, or multi-account dependency.
2. Route high-volume VPC-to-VPC traffic through VPC Peering.
3. Monitor TGW attachment traffic for 7 days before detaching.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX with assumptions and confidence.

## Optimized Terraform / Operational Plan
<real resource-based plan>
```
