# finops-elasticache — Detailed Rules

## Required Safety Checks (before reducing nodes or node type)

- `DatabaseMemoryUsagePercentage` (or equivalent) safely below threshold at avg + p95.
- Evictions zero or negligible.
- CPU, network bytes, connection counts have headroom.
- Replication lag acceptable for Redis/Valkey replicas.
- Multi-AZ and automatic failover requirements preserved.
- Cluster-mode shard count and replica count remain valid for engine and workload.
- Reserved-node coverage and commitments considered before changing families or counts.

## Deep Architectural Analysis

### Infrastructure
- Total ElastiCache clusters / replication groups.
- Engine, node type, shard count, replica count, `num_cache_clusters`, automatic
  failover, Multi-AZ, cluster mode.
- Reserved-node coverage / commitment notes when present.
- Tags: Owner, Environment, Purpose, SLA, CostCenter.

### Metrics (per cluster / replication group)
- Cache hit rate avg/p95.
- Memory usage avg/p95/max.
- Evictions and swap usage.
- CPU, network, current connections, replication lag.
- Traffic pattern: steady, spiky, batch, seasonal, flat-zero.

If only cache hit rate is available, lower confidence and don't auto-recommend
downsizing.

### Cost
- Monthly ElastiCache spend trend.
- Node-hour cost by node type, shard count, replica count.
- Reserved-node / commitment coverage if present.
- Region pricing — prefer cost report or aws-pricing MCP.

### Root Cause (governance frame)
- Replica count set for higher availability tier than workload needs.
- Node class selected for memory growth that didn't happen.
- Cluster mode / shards overbuilt for traffic.
- Reserved-node coverage missing for stable retained capacity.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → aws-pricing MCP → rule fallback.

```
current_node_cost     = current_node_count * current_node_hourly_price * hours_per_month
recommended_node_cost = recommended_node_count * recommended_node_hourly_price * hours_per_month
monthly_savings       = current_node_cost - recommended_node_cost
```

For reserved-node recommendations: if node type, engine, or region eligibility
is not covered by rules / cost_report / aws-pricing, call `aws-docs` to verify
before modeling savings.

Do not count reserved-node savings unless the recommendation explicitly buys or
changes reserved coverage.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Do not hard-code all flagged replication groups to `num_cache_clusters = 2`.
  Preserve the minimum topology required for engine, shard count, automatic
  failover, Multi-AZ, and workload SLA.
- Prefer changing replica count or node type only when metrics show enough
  memory, CPU, network, connection, and replication headroom.
- Comments explain evidence and rollback/monitoring plan.
- If evidence is incomplete, produce a review plan instead of changing topology.

## Preventive Actions

1. Review topology quarterly.
2. Alert on low utilization and on performance-risk signals.
3. Consider reserved nodes for retained steady baseline.
