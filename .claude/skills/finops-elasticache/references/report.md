# finops-elasticache — Report Template

```markdown
# FinOps ElastiCache Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | ElastiCache over-provisioned topology or node size |
| Affected Resources | X of Y |
| Monthly Waste | $XX estimated |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<engine, topology, node type, HA/failover, reserved coverage>

### Metrics
<hit rate, memory, evictions, CPU, network, connections, replication lag>

### Cost Report
<monthly cost and pricing assumptions>

## Root Cause
<architecture-based cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX.XX with assumptions.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```
