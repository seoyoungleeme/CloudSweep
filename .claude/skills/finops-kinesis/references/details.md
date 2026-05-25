# finops-kinesis — Detailed Rules

## Required Safety Checks

### Before disabling EFO
- Consumer latency SLA doesn't require dedicated low-latency delivery.
- Standard polling read throughput sufficient for all consumers.
- No critical consumer relies on isolation from other consumers.
- `IteratorAgeMilliseconds`, consumer lag, read throttles stay safe in pilot/model.

### Before reducing shards
- p95 and max incoming bytes/records against shard limits.
- Write and read provisioned-throughput-exceeded metrics.
- Peak bursts, partition-key skew, resharding operational risk.
- Preserve enough headroom for planned growth and replay events.

## Deep Architectural Analysis

### Infrastructure
- Stream count, mode (`PROVISIONED` or `ON_DEMAND`), shard count, retention period,
  encryption, tags, registered consumers.
- EFO consumers and standard consumers.
- Downstream consumers: Lambda ESMs, KCL apps, Firehose, analytics, custom apps.

### Metrics
- Incoming bytes and records: avg/p95/max.
- Read/write throughput exceeded metrics.
- Iterator age, consumer lag, processing interval.
- EFO retrieval volume and consumer count.
- Traffic pattern: steady, spiky, batch, diurnal, bursty.

If only one metric is provided, lower confidence and avoid destructive or
latency-impacting recommendations.

### Cost
- Monthly Kinesis spend trend.
- Stream/shard-hour, ingest, retrieval, EFO, retention, enhanced-retention charges.
- Pricing assumptions and region — prefer cost report or aws-pricing MCP.
- Separate savings by source: EFO, shard count, mode change, retention,
  producer record aggregation.

### Root Cause (governance frame)
- EFO enabled by default for consumers that don't need dedicated throughput.
- Shard count sized for peak launch traffic and never revisited.
- Billing mode no longer matches workload shape.
- Extended retention set without documented replay requirement.
- Producer record aggregation missing, inflating PUT payload or ingest cost.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → aws-pricing MCP → rule fallback.

Do not count EFO savings unless consumers can safely move to standard polling or
another lower-cost architecture. Do not count shard savings if throttling,
iterator age, or peak throughput evidence blocks downsizing.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Prefer a review/pilot plan when latency or throughput evidence is incomplete.
- Disable EFO only for explicitly flagged consumers with no low-latency or
  isolation requirement.
- Reduce shard count only when p95/max throughput, throttling, and headroom support it.
- Adjust retention only when replay/compliance requirements are documented.
- Comments explain evidence, rollout, and rollback monitoring.

## Preventive Actions

1. Review stream mode, shard count, EFO consumers, and retention monthly.
2. Alert on throttling, high iterator age, and low shard utilization.
3. Require documented latency/replay requirements for EFO and extended retention.
