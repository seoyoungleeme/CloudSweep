---
name: finops-dynamodb
description: >
  FinOps DynamoDB Analysis Skill. Detects cost waste in AWS DynamoDB tables
  caused by over-provisioned capacity, missing or unsafe Auto Scaling,
  suboptimal billing mode selection, and capacity settings that ignore observed
  traffic, throttling, GSIs, table class, or reserved capacity commitments.
  Use for Terraform configurations, CloudWatch metrics, and AWS cost reports
  containing aws_dynamodb_table resources.
  Keywords: "DynamoDB cost", "RCU", "WCU", "over-provisioned",
  "DynamoDB waste", "PAY_PER_REQUEST", "PROVISIONED".
user_invocable: false
---

# FinOps DynamoDB Analysis Skill

## Scope

Analyze DynamoDB capacity and billing mode from a FinOps perspective. The goal
is to reduce unused provisioned capacity and avoid expensive billing mode
choices without increasing throttling risk or breaking workload reliability.

Important safety rule:

Do not recommend reducing capacity or changing billing mode based only on
average utilization. Check peak usage, p95 usage, throttling metrics, traffic
shape, Auto Scaling settings, GSIs, and any cost commitments first.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` for all files before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_dynamodb_table`, GSI, and autoscaling resources | Cannot analyze; ask user for path |
| `metrics.json` | CloudWatch metrics such as consumed RCU/WCU, throttled requests, successful requests, and account/table capacity | Mark metrics evidence as unavailable |
| `cost_report.json` | Monthly DynamoDB cost history, pricing notes, reserved capacity notes, or CUR-like line items | Mark cost evidence as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/overprovisioned_dynamodb.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| D1 | `PROVISIONED` table or GSI has avg utilization < 20%, p95 utilization < 50%, and no throttling | HIGH | REDUCE_CAPACITY or ADD_AUTOSCALING |
| D2 | `PROVISIONED` table or GSI has low read utilization under the same safety checks | HIGH | REDUCE_RCU or ADD_AUTOSCALING |
| D3 | `PROVISIONED` table or GSI has no Application Auto Scaling target/policy | MEDIUM | ADD_AUTOSCALING |
| D4 | `PAY_PER_REQUEST` has steady high-volume traffic and modeled provisioned cost is lower | LOW | CONSIDER_PROVISIONED |
| D5 | GSI capacity is over-provisioned or missing Auto Scaling | HIGH/MEDIUM | RIGHTSIZE_GSI |
| D6 | Cost report suggests storage, backup, streams, global table, or table class cost dominates | INFO | ANALYZE_NON_CAPACITY_COST |

### Utilization Thresholds

- `< 20%` average utilization: potential waste, but require p95/peak and
  throttling checks before recommending a reduction.
- `20-50%` average utilization: moderate headroom; prefer Auto Scaling tuning
  over a hard reduction.
- `> 50%` average utilization: generally acceptable, but still check cost mode,
  throttling, and traffic pattern.
- Any sustained throttling or frequent `ProvisionedThroughputExceeded` evidence:
  do not reduce capacity; investigate under-provisioning or hot partitions.

### Billing Mode Guidance

- `PAY_PER_REQUEST` is usually safer for new, spiky, unpredictable, or low-volume
  workloads.
- `PROVISIONED` with Auto Scaling can be cheaper for steady, predictable, high
  request volume workloads.
- Do not switch from `PROVISIONED` to `PAY_PER_REQUEST` if the table benefits
  from reserved provisioned capacity, predictable high utilization, or strict
  throughput planning unless cost modeling supports the change.
- Do not switch from `PAY_PER_REQUEST` to `PROVISIONED` without modeling peak
  traffic, Auto Scaling min/max capacity, and throttling risk.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total `aws_dynamodb_table` count.
- Billing mode per table: `PROVISIONED` or `PAY_PER_REQUEST`.
- Provisioned RCU/WCU per table and per GSI.
- Auto Scaling presence for table read, table write, GSI read, and GSI write:
  `aws_appautoscaling_target` and `aws_appautoscaling_policy`.
- Table class, global secondary indexes, global table replicas, streams,
  point-in-time recovery, TTL, backups, and tags when present.

### 3.2 Metric Evidence

For each table and GSI where data is available:

- Consumed RCU/WCU average, p95, max, and utilization percentage.
- Throttled read/write requests or `ProvisionedThroughputExceeded` evidence.
- Request pattern classification: steady, spiky, diurnal, batch, or flat-zero.
- Hot partition signals if available.

If only average capacity metrics are provided, lower the confidence of any
capacity reduction recommendation.

### 3.3 Cost Evidence

- Monthly DynamoDB spend trend.
- Capacity cost breakdown: provisioned read/write, on-demand read/write, GSI
  capacity, reserved capacity, storage, backups, PITR, streams, export/import,
  global tables, and data transfer when available.
- Pricing assumptions and region. Prefer cost report values or AWS Pricing MCP
  over static fallback rates.
- Whether savings are from reducing provisioned capacity, changing billing mode,
  tuning Auto Scaling minimums, or addressing non-capacity cost.

### 3.4 Root Cause

Explain the architecture or governance cause, such as:

- Capacity was set for a launch estimate or historical peak and never revisited.
- Auto Scaling is missing or min capacity is too high.
- GSIs were provisioned independently and forgotten.
- Workload changed from steady to spiky, or from high-volume to low-volume.
- On-demand was selected for convenience but traffic became steady enough to
  justify provisioned mode with Auto Scaling.
- Reserved capacity commitments are not aligned with actual provisioned usage.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like line items when available.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback prices in `rules/overprovisioned_dynamodb.json` only as
   an estimate.

Provisioned estimate:

```text
provisioned_write_cost = provisioned_wcu * wcu_hour_price * hours_per_month
provisioned_read_cost = provisioned_rcu * rcu_hour_price * hours_per_month
recommended_write_cost = recommended_wcu * wcu_hour_price * hours_per_month
recommended_read_cost = recommended_rcu * rcu_hour_price * hours_per_month
monthly_savings = current_capacity_cost - recommended_capacity_cost
```

On-demand estimate:

```text
monthly_write_request_units = observed_write_request_units
monthly_read_request_units = observed_read_request_units
on_demand_cost = (monthly_write_request_units / 1,000,000 * write_request_price)
               + (monthly_read_request_units / 1,000,000 * read_request_price)
```

Do not count storage, backup, PITR, stream, global table, or data transfer
savings unless the proposed remediation directly changes those cost drivers.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Do not modify `PAY_PER_REQUEST` tables unless Rule D4 is supported by cost
  modeling.
- For `PROVISIONED` tables with confirmed over-provisioning and no throttling:
  - Prefer adding or tuning Auto Scaling when traffic varies.
  - Reduce minimum capacity only to a value supported by p95/peak evidence and
    business headroom.
  - Include both table and GSI autoscaling where GSIs exist.
  - Use target utilization around 70% by default, but lower it for latency-
    sensitive workloads or when throttling risk is present.
- Switch to `PAY_PER_REQUEST` only when traffic is spiky, low-volume, or
  unpredictable and the modeled on-demand cost is lower or acceptable.
- Switch to `PROVISIONED` only when traffic is steady and cost modeling shows
  savings after Auto Scaling min/max capacity and operational risk are included.
- Include a short header comment with savings estimate, confidence, and
  recommendation rationale.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

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
<monthly spend table, pricing note, capacity vs non-capacity cost breakdown>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
1. Enable Auto Scaling defaults for PROVISIONED tables and GSIs.
2. Alert on sustained low utilization and on throttling.
3. Review billing mode monthly for high-spend tables.
4. Track reserved capacity coverage and utilization where used.

## Estimated Monthly Savings
$XX.XX, with savings source and assumptions.

## Optimized Terraform
<real resource-based optimized Terraform>
```

Generated by: finops-dynamodb skill
