---
name: finops-rds
description: >
  FinOps RDS Analysis Skill. Detects RDS cost inefficiencies from instance
  over-sizing, unnecessary Multi-AZ, storage/IOPS over-provisioning, old engine
  support costs, and reserved instance coverage gaps using Terraform,
  CloudWatch metrics, and AWS cost reports.
user_invocable: false
---

# FinOps RDS Analysis Skill

## Scope

Reduce unnecessary database spend while preserving availability, durability,
performance, backup/restore, compliance, and maintenance requirements.

## Required Evidence

| File | Used For | If Missing |
|------|----------|------------|
| `main.tf` | `aws_db_instance`, storage, Multi-AZ, backups, replicas, monitoring, tags | Cannot analyze; ask for path |
| `metrics.json` | CPU avg/p95/max, connections, freeable memory, IOPS, throughput, latency, storage, queue depth | Mark metrics unavailable |
| `cost_report.json` | Monthly RDS cost, pricing notes, RI coverage, Extended Support, storage, IOPS, backup, transfer cost | Mark cost unavailable |

Missing facts → write `Not available in the provided data; verify in the real environment.`

## Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| R1 | Multi-AZ on non-production with no SLA/DR requirement | MEDIUM | REVIEW_SINGLE_AZ |
| R2 | Instance class underutilized across CPU, memory, connections, I/O with safe p95/max | HIGH | REVIEW_DOWNSIZE |
| R3 | Provisioned storage, IOPS, or throughput exceeds observed needs | MEDIUM | REVIEW_STORAGE_IOPS |
| R4 | Old engine version incurs Extended Support cost | HIGH | UPGRADE_ENGINE |
| R5 | Steady retained baseline lacks Reserved DB Instance coverage | LOW | MODEL_RESERVED_INSTANCE |
| R6 | Performance risk: high CPU, low memory, high I/O, high latency, throttling | INFO | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE |

## Safety Guardrails

- Do not downsize or disable Multi-AZ from average CPU or environment tags
  alone. Check p95/max CPU, memory, connections, IOPS, storage, latency, queue
  depth, failover/SLA, backup/DR, RI coverage first.
- For R5 RI eligibility uncertainty (Aurora vs RDS, custom engines), note the
  uncertainty in the finding evidence rather than omitting the finding.
- R6 is informational and must not carry savings. Its presence should block R2/R3.

## Output Contract

Write `result/rds_skill_analysis.json` conforming to
`schemas/skill-analysis.schema.json` before running LangGraph.

LangGraph reads this file and assigns `finding_id`, `savings_group`, and
`evidence_facts`. Do not include those fields in the skill output.

```json
{
  "schema_version": "1.0",
  "domain": "rds",
  "skill_version": "2.0",
  "findings": [
    {
      "rule_id": "RDS_R1_NONPROD_MULTI_AZ",
      "resource": "<tf_resource_name>",
      "severity": "MEDIUM",
      "confidence": "MEDIUM",
      "estimated_monthly_saving_usd": 0.0,
      "evidence": ["multi_az=true", "environment=dev", "No DR/SLA requirement in config"],
      "recommendation": "Review SLA, DR, and compliance requirements before disabling Multi-AZ.",
      "optimized_replacement": null
    }
  ]
}
```

Allowed `rule_id` values: `RDS_R1_NONPROD_MULTI_AZ`, `RDS_R2_LOW_UTILIZATION`,
`RDS_R3_STORAGE_IOPS_OVERPROVISIONED`, `RDS_R4_EXTENDED_SUPPORT`,
`RDS_R5_NO_RI_COVERAGE`, `RDS_R6_PERFORMANCE_RISK`.

Set `estimated_monthly_saving_usd` to `0.0` when cost data is unavailable or
when the rule is informational (R6).
