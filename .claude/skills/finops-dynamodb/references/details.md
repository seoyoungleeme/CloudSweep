# finops-dynamodb — Detailed Rules

## Utilization Thresholds

- `< 20%` avg utilization: potential waste, but require p95/peak and throttling
  checks before recommending reduction.
- `20-50%` avg: moderate headroom — prefer Auto Scaling tuning over hard reduction.
- `> 50%` avg: generally acceptable; still check cost mode, throttling, pattern.
- Sustained throttling or frequent `ProvisionedThroughputExceeded`: do not reduce
  capacity; investigate under-provisioning or hot partitions.

## Billing Mode Guidance

- `PAY_PER_REQUEST`: safer for new, spiky, unpredictable, low-volume workloads.
- `PROVISIONED` with Auto Scaling: cheaper for steady, predictable, high-volume.
- Don't switch `PROVISIONED → PAY_PER_REQUEST` if reserved capacity, predictable
  high utilization, or strict throughput planning applies unless modeled.
- Don't switch `PAY_PER_REQUEST → PROVISIONED` without modeling peak traffic,
  Auto Scaling min/max, and throttling risk.

## Deep Architectural Analysis

### Infrastructure
- Total `aws_dynamodb_table` count.
- Billing mode per table.
- Provisioned RCU/WCU per table and per GSI.
- Auto Scaling presence for table read/write and GSI read/write
  (`aws_appautoscaling_target`, `aws_appautoscaling_policy`).
- Table class, GSIs, global table replicas, streams, PITR, TTL, backups, tags.

### Metrics (per table and GSI)
- Consumed RCU/WCU avg, p95, max, utilization %.
- Throttled read/write or `ProvisionedThroughputExceeded`.
- Request pattern: steady, spiky, diurnal, batch, flat-zero.
- Hot partition signals if available.

If only avg capacity metrics provided, lower confidence of any reduction recommendation.

### Cost
- Monthly DynamoDB spend trend.
- Cost breakdown: provisioned read/write, on-demand read/write, GSI capacity,
  reserved, storage, backups, PITR, streams, export/import, global tables, data transfer.
- Region/pricing assumptions — prefer cost report or aws-pricing MCP.
- Savings source: reducing provisioned, changing mode, tuning Auto Scaling min,
  or non-capacity cost.

### Root Cause (governance frame)
- Capacity set for launch estimate or historical peak, never revisited.
- Auto Scaling missing or min too high.
- GSIs provisioned independently and forgotten.
- Workload shifted (steady ↔ spiky, high ↔ low).
- On-demand selected for convenience but traffic now steady.
- Reserved capacity commitments misaligned.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → aws-pricing MCP → rule fallback.

**Provisioned**:
```
provisioned_write_cost  = provisioned_wcu * wcu_hour_price * hours_per_month
provisioned_read_cost   = provisioned_rcu * rcu_hour_price * hours_per_month
recommended_write_cost  = recommended_wcu * wcu_hour_price * hours_per_month
recommended_read_cost   = recommended_rcu * rcu_hour_price * hours_per_month
monthly_savings         = current_capacity_cost - recommended_capacity_cost
```

**On-demand**:
```
on_demand_cost = (monthly_write_request_units / 1,000,000 * write_request_price)
               + (monthly_read_request_units  / 1,000,000 * read_request_price)
```

Do not count storage, backup, PITR, stream, global table, or data transfer
savings unless the remediation directly changes those drivers.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Do not modify `PAY_PER_REQUEST` tables unless Rule D4 is supported by cost modeling.
- For `PROVISIONED` with confirmed over-provisioning and no throttling:
  - Prefer adding/tuning Auto Scaling when traffic varies.
  - Reduce min capacity only to a value supported by p95/peak evidence + headroom.
  - Include both table and GSI autoscaling.
  - Target utilization ~70% default; lower for latency-sensitive or throttling-risk workloads.
- Switch to `PAY_PER_REQUEST` only when traffic is spiky/low/unpredictable and modeled on-demand is lower.
- Switch to `PROVISIONED` only when traffic is steady and modeling shows savings
  after Auto Scaling min/max and operational risk.
- Header comment with savings, confidence, rationale.

## Preventive Actions

1. Enable Auto Scaling defaults for PROVISIONED tables and GSIs.
2. Alert on sustained low utilization and on throttling.
3. Review billing mode monthly for high-spend tables.
4. Track reserved capacity coverage and utilization.
