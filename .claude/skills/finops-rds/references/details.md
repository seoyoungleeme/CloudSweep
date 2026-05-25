# finops-rds — Detailed Rules

## Required Safety Checks

### Before downsizing
- CPU avg, p95, max.
- FreeableMemory, SwapUsage, connections, read/write IOPS, throughput, latency,
  DiskQueueDepth, storage free, burst balance.
- Read replicas, Multi-AZ, backup/maintenance windows, engine family compatibility.
- Reserved-instance coverage before changing class/family.
- Snapshot, maintenance window, rollback, post-change monitoring plan.

### Before disabling Multi-AZ
- Workload non-production or explicit reduced-availability tolerance.
- RTO/RPO, failover, backup, restore, maintenance needs confirmed.
- No compliance or customer-facing SLA requires Multi-AZ.

## Deep Architectural Analysis

### Infrastructure
- DB instance count, engine, version, class, storage type/size, allocated/max
  storage, IOPS/throughput, Multi-AZ, replicas, backups, deletion protection,
  Performance Insights, monitoring, tags.

### Metrics
- CPU avg/p95/max, connections, freeable memory, swap, IOPS, throughput,
  latency, disk queue, storage free, replica lag, failover/maintenance evidence.
- Lower confidence if only CPU average is available.

### Cost
- Monthly RDS spend trend.
- Instance hours, Multi-AZ, storage, IOPS, backup, data transfer, Extended
  Support, Performance Insights, RI coverage.
- Region pricing — prefer cost report or aws-pricing MCP.

### Root Cause (governance frame)
- Instance class selected for historical peak, never revisited.
- Multi-AZ applied uniformly to non-production without SLA review.
- Storage/IOPS static, not tied to observed workload.
- Engine versions past standard support.
- RI coverage doesn't match retained database baseline.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → aws-pricing MCP → rule fallback.

Separate savings by source: instance class, Multi-AZ, storage, IOPS/throughput,
backup, Extended Support, RI coverage. Do not count RI purchase savings unless
utilization and term risk are modeled.

For R5 (RI coverage): if term options, payment options, or engine-specific
eligibility (Aurora vs RDS, custom engine versions) is unclear, call `aws-docs`
to verify before modeling savings.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- If metric coverage is incomplete, generate a review plan instead of changing
  instance class or Multi-AZ.
- For confirmed downsizing: conservative target classes; snapshot, maintenance
  window, rollback, 7-14 day monitoring plan.
- Do not disable Multi-AZ when SLA/DR/compliance requirements are unknown.
- Comments explain evidence and risk controls.

## Preventive Actions

1. Review rightsizing quarterly.
2. Alert on low utilization and performance risk.
3. Track RI coverage for retained steady databases.
