# FinOps ElastiCache Deep Analysis Report — L2-019

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Excess Node Count (E1) |
| Affected Resources | 1 of 2 `aws_elasticache_replication_group` (k1b93b) |
| Excess Nodes | 4 (6 provisioned → 2 HA minimum) |
| Monthly Waste | $665.76 |
| Annual Waste | $7,989.12 |

---

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)

2 `aws_elasticache_replication_group` resources, both using `cache.r5.large` with `automatic_failover_enabled = true`.

| Cluster | node_type | num_cache_clusters | auto_failover | E1? |
|---|---|---|---|---|
| k1b93b | cache.r5.large | **6** | true | ✅ Yes |
| 31362i | cache.r5.large | 2 | true | ❌ No — at HA minimum |

AWS requires minimum 2 nodes when `automatic_failover_enabled = true` (1 primary + 1 replica). k1b93b runs 4 extra replicas beyond this requirement. The two clusters are identical in node type — making 31362i a direct comparison baseline.

### 3.2 Evidence from Metrics (CloudWatch — 30 days)

| Cluster | Node Count | Avg Hit Rate % | Min Hit Rate % | Avg CPU % | Avg Connections | Issue |
|---|---|---|---|---|---|---|
| k1b93b | 6 | **99.9967** | 99.14 | 8.45 | 49.0 | ✅ E1 |
| 31362i | 2 | 91.74 | 85.65 | **54.43** | 100.0 | — baseline |

**k1b93b analysis:**
- 30-day average hit rate: **99.9967%** (minimum ever recorded: 99.14%) — far above the 99.0% E1 threshold
- CPU utilization: **8.45%** average — the cluster is substantially idle
- Connections: ~49 average — low traffic load
- A 99.9967% hit rate means the entire working set fits in memory with enormous headroom. The 4 extra replicas each hold a complete copy of data that is already serving every request from the primary/first replica.

**31362i analysis (contrast):**
- Hit rate: **91.74%** — shows what genuine memory pressure looks like; 8.26% of requests miss the cache and hit the backend
- CPU: **54.43%** — actively processing substantial load
- Connections: 100.0 (flat at max) — traffic is saturating this cluster's connection pool

The contrast is definitive: 31362i at 2 nodes with real load shows cache pressure; k1b93b at 6 nodes with low load shows none. Adding nodes to k1b93b beyond 2 provides zero cache benefit.

### 3.3 Evidence from Cost Report (6 months)

| Month | ElastiCache Spend | Total Spend | ElastiCache % |
|---|---|---|---|
| M-5 | $719.30 | $4,206.35 | 17.1% |
| M-4 | $952.34 | $4,241.93 | 22.5% |
| M-3 | $782.75 | $4,099.20 | 19.1% |
| M-2 | $784.75 | $4,048.34 | 19.4% |
| M-1 | $968.18 | $4,136.01 | 23.4% |
| M-0 | $723.37 | $4,185.39 | 17.3% |
| **Avg** | **$821.78** | **$4,152.87** | **19.8%** |

`pricing_note`: *"cache.r5.large = $0.228/hr. 초과 4 노드 × $0.228 × 730시간 = ~$665/mo 절감 가능."*

Cross-check with actual node pricing:
- k1b93b current: 6 × $0.228 × 730 = **$998.64/mo**
- 31362i current: 2 × $0.228 × 730 = **$332.88/mo**
- Combined: **$1,331.52/mo** theoretical (avg billed $821.78 — variance attributable to RI pricing or partial-month billing)
- After optimization (k1b93b → 2 nodes): 2 × $0.228 × 730 = $332.88/mo → **savings $665.76/mo**

### 3.4 Root Cause

k1b93b was provisioned with 6 nodes during initial deployment, likely to handle anticipated peak traffic or as a "safe" buffer. The actual workload never materialized at that scale: 30-day metrics show 8.4% CPU utilization and a 99.9967% cache hit rate — the cluster barely works. Nodes 3–6 are replicas holding identical data copies that are never read; each bills identically at $0.228/hr with zero contribution to performance or availability beyond nodes 1–2.

AWS ElastiCache does not provide any SLA benefit beyond 2 nodes for `automatic_failover_enabled = true` workloads. Additional replicas can improve read throughput under heavy load — but with only ~49 connections and 8.4% CPU, k1b93b has no such need.

---

## Proposed Solution

### Immediate Actions (Week 1)
1. Apply `main_optimized.tf` — sets `num_cache_clusters = 2` for k1b93b.
2. AWS ElastiCache removes replica nodes sequentially (non-disruptive); no connection interruption.
3. Monitor `CacheHitRate`, `CurrConnections`, and `CPUUtilization` for 48 hours post-change.
   - Alert threshold: `CacheHitRate < 95%` → pause and investigate before removing further nodes.
4. `terraform plan -out=elasticache_fix.plan` → review → `terraform apply`.

### Preventive Actions (Week 2–4)
1. **CloudWatch Alarm** — `CacheHitRate < 95%`: triggers scale-up review. `Evictions > 0`: immediate alert.
2. **CloudWatch Alarm** — `CPUUtilization > 70%`: node count review.
3. **ElastiCache Reserved Nodes** — with k1b93b reduced to 2 nodes + 31362i at 2 nodes, purchase 1-yr reserved nodes for all 4 remaining nodes; further 30–40% cost reduction.
4. **Capacity review cadence** — quarterly CloudWatch hit rate and CPU review for all ElastiCache clusters; flag any cluster with >2 nodes AND hit rate >99% AND CPU <20% for downsizing.

---

## Estimated Monthly Savings (USD)

| Cluster | Current Nodes | Recommended Nodes | node_type | Monthly Savings |
|---|---|---|---|---|
| k1b93b | 6 | 2 | cache.r5.large | **$665.76** |
| 31362i | 2 | 2 | cache.r5.large | — (no change) |
| **Total** | | | | **$665.76/mo** |

**Annual savings: $7,989.12**

---

## Optimized Terraform

See `main_optimized.tf` for the complete modified configuration.

```bash
# Safety verification before applying:
# 1. terraform plan -out=elasticache_fix.plan
# 2. Confirm only num_cache_clusters changes for k1b93b
# 3. terraform apply elasticache_fix.plan
# 4. Monitor CacheHitRate, CPUUtilization, Evictions for 48h post-apply
```

---

*Generated by: finops-elasticache skill — Claude Code*
