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
| R3 | Production baseline lacks Reserved DB coverage | LOW | REVIEW_RESERVED_INSTANCE |
| R4 | Old engine version incurs Extended Support cost | HIGH | UPGRADE_ENGINE |
| R5 | gp2 storage is a gp3 migration candidate | MEDIUM | REVIEW_GP3_MIGRATION |
| R6 | Read replica has very low connection usage | MEDIUM | REVIEW_REPLICA_DEPENDENCIES |

## Safety Guardrails

- Do not downsize or disable Multi-AZ from average CPU or environment tags
  alone. Check p95/max CPU, memory, connections, IOPS, storage, latency, queue
  depth, failover/SLA, backup/DR, RI coverage first.
- For R5 RI eligibility uncertainty (Aurora vs RDS, custom engines), note the
  uncertainty in the finding evidence rather than omitting the finding.
- R5 requires IOPS and throughput validation before accepting a migration.
- R6 requires DR, reporting, and read-routing dependency validation.

## Output Contract

Read `result/rds_skill_request.json` after the first LangGraph pass. Decide
each candidate using SLA, DR, compliance, peak-performance, memory, I/O, and
dependency context. Write `result/rds_skill_analysis.json` conforming to
`schemas/skill-analysis.schema.json`, then rerun LangGraph.

Do not calculate savings, change severity, or write Terraform. LangGraph owns
those deterministic values and applies them only to `accepted` candidates.

```json
{
  "schema_version": "1.0",
  "domain": "rds",
  "skill_version": "2.0",
  "decisions": [
    {
      "rule_id": "RDS_R1_NONPROD_MULTI_AZ",
      "resource": "<tf_resource_name>",
      "disposition": "needs_evidence",
      "confidence": "MEDIUM",
      "rationale": "Environment is non-production, but no SLA/DR requirement was provided.",
      "evidence": ["multi_az=true", "environment=dev", "sla_requirement=not_available"]
    }
  ]
}
```

Use `needs_evidence` whenever a safety guardrail cannot be resolved. Never add
a decision for a rule/resource pair absent from the Skill request.
