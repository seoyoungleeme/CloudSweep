---
name: finops-elasticache
description: >
  FinOps ElastiCache Analysis Skill. Detects cost waste in ElastiCache clusters
  from excess replicas, overprovisioned node types, missing reserved node
  coverage, and HA mismatches using Terraform, CloudWatch metrics, and AWS
  cost reports.
user_invocable: false
---

# FinOps ElastiCache Analysis Skill

## Scope

Reduce ElastiCache spend while preserving cache hit rates, read throughput,
eviction limits, replication lag, Multi-AZ availability, and failover
requirements.

## Required Evidence

| File | Used For | If Missing |
|------|----------|------------|
| `main.tf` | `aws_elasticache_replication_group`, node type, num_cache_clusters, Multi-AZ, parameter group, engine version | Cannot analyze; ask for path |
| `metrics.json` | CacheHitRate, Evictions, CPUUtilization, DatabaseMemoryUsagePercentage, ReplicationLag, NetworkBytesIn/Out | Mark metrics unavailable |
| `cost_report.json` | Monthly ElastiCache cost, reserved node coverage | Mark cost unavailable |

Missing facts → write `Not available in the provided data; verify in the real environment.`

## Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| EC1 | num_cache_clusters >2 AND read replica traffic is low (p95 connections <30% of primary) | HIGH | REVIEW_REDUCE_REPLICAS |
| EC2 | DatabaseMemoryUsagePercentage p95 <50% AND CPUUtilization avg <20% | HIGH | REVIEW_DOWNSIZE_NODE |
| EC3 | Steady baseline with no reserved node purchase AND monthly cost >$200 | LOW | MODEL_RESERVED_NODE |
| EC4 | Single node, no replica, no Multi-AZ, production workload | INFO | REVIEW_HA_POSTURE |
| EC5 | Engine version eligible for upgrade AND current version EOL or approaching EOL | MEDIUM | UPGRADE_ENGINE |

## Safety Guardrails

- Do not reduce replicas when eviction count is >0 in any observation window,
  or when replication lag exceeds 100ms at p95.
- Do not downsize node type when cache hit rate drops below 95% or when
  evictions are non-zero — these indicate memory pressure.
- EC1 and EC2 may co-occur; report both. Do not combine their savings.
- EC4 is informational; set `estimated_monthly_saving_usd` to 0.0.
- For EC3, model savings conservatively: 1-year reserved is typically 30% off
  on-demand. Only recommend if the cluster has been stable for ≥60 days.

## Output Contract

Write `result/elasticache_skill_analysis.json` conforming to
`schemas/skill-analysis.schema.json` before running LangGraph.

LangGraph reads this file and assigns `finding_id`, `savings_group`, and
`evidence_facts`. Do not include those fields in the skill output.

```json
{
  "schema_version": "1.0",
  "domain": "elasticache",
  "skill_version": "2.0",
  "findings": [
    {
      "rule_id": "ELASTICACHE_EC1_REDUCE_REPLICAS",
      "resource": "<tf_resource_name>",
      "severity": "HIGH",
      "confidence": "MEDIUM",
      "estimated_monthly_saving_usd": 0.0,
      "evidence": ["num_cache_clusters=4", "replica_connection_p95_pct=18", "evictions=0", "replication_lag_ms_p95=12"],
      "recommendation": "Reduce to 2 replicas after confirming eviction=0, lag<100ms, and hit rate >95%.",
      "optimized_replacement": null
    }
  ]
}
```

Allowed `rule_id` values: `ELASTICACHE_EC1_REDUCE_REPLICAS`,
`ELASTICACHE_EC2_DOWNSIZE_NODE`, `ELASTICACHE_EC3_NO_RESERVED_NODE`,
`ELASTICACHE_EC4_NO_HA`, `ELASTICACHE_EC5_ENGINE_UPGRADE`.

Set `estimated_monthly_saving_usd` to `0.0` when cost data is unavailable or
when the rule is informational (EC4).
