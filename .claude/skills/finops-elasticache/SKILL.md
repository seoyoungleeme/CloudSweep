---
name: finops-elasticache
description: >
  FinOps ElastiCache Analysis Skill. Detects ElastiCache cost waste from
  over-provisioned nodes, excessive replicas or shards, oversized node classes,
  missing reserved node coverage, and cache clusters whose topology no longer
  matches observed workload needs.
user_invocable: false
---

# FinOps ElastiCache Analysis Skill

## Scope

Analyze ElastiCache for Redis/Valkey or Memcached from a FinOps perspective.
The goal is to reduce unnecessary node hours while preserving availability,
latency, memory headroom, failover posture, and cache effectiveness.

Important safety rule:

Do not reduce node count based only on high `cache_hit_rate_pct`. A high hit
rate can mean the cache is healthy, not necessarily over-provisioned. Confirm
low memory pressure, low evictions, acceptable CPU, network headroom, connection
headroom, and replication/failover safety before recommending downsizing.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_elasticache_replication_group`, `aws_elasticache_cluster`, subnet/security resources, and tags | Cannot analyze; ask user for path |
| `metrics.json` | Cache hit rate, evictions, memory usage, CPU, network, connections, replication lag, and node count | Mark metrics section as unavailable |
| `cost_report.json` | Monthly ElastiCache cost history, pricing notes, or reserved node coverage | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/overprovisioned_elasticache.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| EC1 | Excess replicas/nodes with low memory pressure, low evictions, low CPU/network, and HA minimum preserved | HIGH | REDUCE_REPLICAS |
| EC2 | Node class oversized based on memory, CPU, network, and p95 usage | HIGH | DOWNSIZE_NODE_TYPE |
| EC3 | Too many shards for keyspace/throughput evidence | MEDIUM | REVIEW_SHARD_COUNT |
| EC4 | Reserved node coverage missing for retained steady baseline | LOW | CONSIDER_RESERVED_NODES |
| EC5 | Evictions, high memory, high CPU, high connections, or replication lag present | INFO | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE |

### Required Safety Checks

Before reducing nodes or node type, verify:

- `DatabaseMemoryUsagePercentage` or equivalent memory utilization is safely
  below threshold at average and p95.
- Evictions are zero or negligible.
- CPU, network bytes, and connection counts have headroom.
- Replication lag is acceptable for Redis/Valkey replicas.
- Multi-AZ and automatic failover requirements are preserved.
- Cluster mode shard count and replica count remain valid for the engine and
  workload.
- Reserved node coverage and commitments are considered before changing node
  families or counts.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total ElastiCache clusters/replication groups.
- Engine, node type, shard count, replica count, `num_cache_clusters`,
  automatic failover, Multi-AZ, and cluster mode.
- Reserved node coverage or commitment notes when present.
- Tags such as Owner, Environment, Purpose, SLA, and CostCenter.

### 3.2 Metric Evidence

For each cluster or replication group:

- Cache hit rate average/p95.
- Memory usage average/p95/max.
- Evictions and swap usage.
- CPU, network, current connections, and replication lag.
- Traffic pattern: steady, spiky, batch, seasonal, or flat-zero.

If only cache hit rate is available, lower confidence and do not make an
automatic downsizing recommendation.

### 3.3 Cost Evidence

- Monthly ElastiCache spend trend.
- Node-hour cost by node type, shard count, and replica count.
- Reserved node or savings commitment coverage when present.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.

### 3.4 Root Cause

Frame root cause as architecture or governance, such as:

- Replica count was set for a higher availability tier than the workload needs.
- Node class was selected for expected memory growth that did not happen.
- Cluster mode/shards were overbuilt for traffic.
- Reserved node coverage is missing for stable retained capacity.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like ElastiCache line items.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback node prices in the rule file only as estimates.

Formula:

```text
current_node_cost = current_node_count * current_node_hourly_price * hours_per_month
recommended_node_cost = recommended_node_count * recommended_node_hourly_price * hours_per_month
monthly_savings = current_node_cost - recommended_node_cost
```

Do not count reserved node savings unless the recommendation explicitly buys or
changes reserved node coverage.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Do not hard-code all flagged replication groups to `num_cache_clusters = 2`.
  Preserve the minimum topology required for the engine, shard count, automatic
  failover, Multi-AZ, and workload SLA.
- Prefer changing replica count or node type only when metrics show enough
  memory, CPU, network, connection, and replication headroom.
- Add comments explaining the evidence and rollback/monitoring plan.
- If evidence is incomplete, produce a review plan instead of changing topology.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

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
1. Review topology quarterly.
2. Alert on low utilization and on performance risk signals.
3. Consider reserved nodes for retained steady baseline.

## Estimated Monthly Savings
$XX.XX with assumptions.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```

Generated by: finops-elasticache skill
