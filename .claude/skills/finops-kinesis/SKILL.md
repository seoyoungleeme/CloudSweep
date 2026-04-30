---
name: finops-kinesis
description: >
  FinOps Kinesis Data Streams Analysis Skill. Detects potentially unnecessary
  enhanced fan-out, shard overcapacity, retention overuse, and billing mode
  mismatches using Terraform, CloudWatch metrics, and AWS cost reports.
user_invocable: false
---

# FinOps Kinesis Analysis Skill

## Scope

Analyze Amazon Kinesis Data Streams cost from a FinOps perspective. The goal is
to reduce avoidable stream, shard, retention, and consumer costs while
preserving producer throughput, consumer latency, replay requirements, and
operational safety.

Important safety rule:

Do not disable Enhanced Fan-Out (EFO) or reduce shard count based on processing
interval alone. EFO can be justified by low-latency SLAs, consumer isolation,
high fan-out, read-throughput contention, or critical consumers. Shard changes
can cause producer/consumer throttling if peak throughput is not modeled.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_kinesis_stream`, stream consumers, retention, shard count, and tags | Cannot analyze; ask user for path |
| `metrics.json` | Iterator age, incoming bytes/records, read/write throttles, consumer lag, consumer count, EFO usage, retention, and shard count | Mark metrics section as unavailable |
| `cost_report.json` | Monthly Kinesis cost history, pricing notes, mode, EFO, shard-hours, retention, PUT payload units, and retrieval costs | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/efo_waste.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| K1 | EFO enabled but no low-latency, high fan-out, or read-throughput contention evidence | MEDIUM | REVIEW_EFO |
| K2 | Provisioned shards exceed p95 write/read throughput with no throttling and safe headroom | HIGH | REDUCE_SHARDS |
| K3 | On-demand or provisioned mode appears cost-inefficient for observed steady/spiky traffic | LOW | MODEL_BILLING_MODE |
| K4 | Extended retention is enabled without replay/compliance requirement evidence | MEDIUM | REVIEW_RETENTION |
| K5 | Write/read throttles, high iterator age, or consumer lag exists | INFO | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE |

### Required Safety Checks

Before disabling EFO:

- Confirm consumer latency SLA does not require dedicated low-latency delivery.
- Confirm standard polling read throughput is sufficient for all consumers.
- Confirm no critical consumer relies on isolation from other consumers.
- Confirm `IteratorAgeMilliseconds`, consumer lag, and read throttles stay safe
  in a pilot or modeled test.

Before reducing shards:

- Check p95 and max incoming bytes/records against shard limits.
- Check write and read provisioned throughput exceeded metrics.
- Include peak bursts, partition-key skew, and resharding operational risk.
- Preserve enough headroom for planned growth and replay events.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Stream count, stream mode (`PROVISIONED` or `ON_DEMAND` if present), shard
  count, retention period, encryption, tags, and registered consumers.
- EFO consumers and standard consumers.
- Any downstream consumers such as Lambda event source mappings, KCL apps,
  Firehose, analytics, or custom apps when visible.

### 3.2 Metric Evidence

- Incoming bytes and records, average/p95/max.
- Read/write throughput exceeded metrics.
- Iterator age, consumer lag, and processing interval.
- EFO retrieval volume and consumer count when provided.
- Traffic pattern: steady, spiky, batch, diurnal, or bursty.

If only one metric is provided, lower confidence and avoid destructive or
latency-impacting recommendations.

### 3.3 Cost Evidence

- Monthly Kinesis spend trend.
- Stream/shard-hour, ingest, retrieval, EFO, retention, and enhanced retention
  charges when available.
- Pricing assumptions and region. Prefer cost report or AWS Pricing MCP over
  static fallback prices.
- Separate savings by source: EFO, shard count, mode change, retention, or
  producer record aggregation.

### 3.4 Root Cause

Frame root cause as architecture or governance, such as:

- EFO was enabled by default for consumers that do not need dedicated throughput.
- Shard count was sized for peak launch traffic and never revisited.
- Billing mode no longer matches workload shape.
- Extended retention was set without documented replay requirement.
- Producer record aggregation is missing, increasing PUT payload or ingest cost.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like Kinesis line items.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback prices in the rule file only as estimates.

Do not count EFO savings unless consumers can safely move to standard polling or
another lower-cost architecture. Do not count shard savings if throttling,
iterator age, or peak throughput evidence blocks downsizing.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Prefer a review/pilot plan when latency or throughput evidence is incomplete.
- Disable EFO only for consumers that are explicitly flagged and have no
  low-latency or isolation requirement.
- Reduce shard count only when p95/max throughput, throttling, and headroom
  evidence support it.
- Adjust retention only when replay/compliance requirements are documented.
- Add comments explaining evidence, rollout, and rollback monitoring.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps Kinesis Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Kinesis EFO, shard, retention, or billing mode inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<stream mode, shard count, EFO consumers, retention, downstream consumers>

### Metrics
<throughput, throttling, iterator age, lag, retrieval, traffic pattern>

### Cost Report
<monthly spend and pricing assumptions>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
1. Review stream mode, shard count, EFO consumers, and retention monthly.
2. Alert on throttling, high iterator age, and low shard utilization.
3. Require documented latency/replay requirements for EFO and extended retention.

## Estimated Monthly Savings
$XX.XX, separated by EFO, shard, retention, and mode-change savings.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```

Generated by: finops-kinesis skill
