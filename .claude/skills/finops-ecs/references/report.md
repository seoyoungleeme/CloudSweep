# finops-ecs — Report Template

```markdown
# FinOps ECS/Fargate Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| ... | ... |

## Evidence

### Infrastructure Evidence (Terraform)
<table of all services: name, CPU, memory, desired_count, launch_type, status>

### Metric Evidence (30 days)
<per-service table: cpu_avg_pct, cpu_p95_pct, cpu_max_pct, memory_avg_pct, memory_p95_pct, status>

### Cost Evidence (6 months)
<monthly table, avg, pricing_note breakdown>

### Root Cause
<architectural explanation>

## Proposed Solution

### Immediate Actions
1. Right-size task definitions.
2. Roll out with staged deployment.
3. Monitor for 7 days.

### Preventive Actions
(See references/details.md § Preventive Actions)

## Estimated Monthly Savings
$XX / month
$XX / year
<savings table: before vs after>
```
