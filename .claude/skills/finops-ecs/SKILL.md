---
name: finops-ecs
description: >
  FinOps ECS Analysis Skill. Detects cost waste in ECS/Fargate services from
  CPU/memory overprovisioning, missing autoscaling, and always-on workloads
  using Terraform, CloudWatch metrics, and AWS cost reports.
user_invocable: false
---

# FinOps ECS Analysis Skill

## Scope

Reduce Fargate and EC2-launch-type ECS spend while preserving deployment
surge capacity, sidecar headroom, latency SLAs, and batch burst requirements.

## Required Evidence

| File | Used For | If Missing |
|------|----------|------------|
| `main.tf` | `aws_ecs_service`, `aws_ecs_task_definition`, launch type, desired count, cpu/memory, autoscaling | Cannot analyze; ask for path |
| `metrics.json` | CPUUtilization, MemoryUtilization, p95/p99, RunningTaskCount, errors, throttles | Mark metrics unavailable |
| `cost_report.json` | Monthly Fargate/ECS cost per service | Mark cost unavailable |

Missing facts → write `Not available in the provided data; verify in the real environment.`

## Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| E1 | Fargate: CPU avg <20% AND p95 <50% AND no error/throttle spike | HIGH | REVIEW_RIGHTSIZE_CPU_MEMORY |
| E2 | EC2 launch type: CPU avg <15% AND no capacity provider strategy | MEDIUM | REVIEW_MIGRATE_TO_FARGATE_OR_RIGHTSIZE |
| E3 | Service with desired_count ≥2 and no autoscaling target or policy | MEDIUM | ADD_TARGET_TRACKING_AUTOSCALING |
| E4 | Scheduled scaling absent for services with predictable traffic patterns | LOW | ADD_SCHEDULED_SCALING |

## Safety Guardrails

- For E1, always verify valid Fargate CPU/memory combinations (256/512, 512/1024,
  1024/2048, 2048/4096, 4096/8192, etc.) before proposing a target shape.
- Do not downsize when sidecar containers share the task CPU/memory budget —
  check `container_definitions` for sidecar count and their reservations.
- Reject E1 when deployment surge (rolling update) would need the headroom
  (check `deployment_maximum_percent` > 100).
- Treat p99 latency SLA evidence as blocking for E1 when it is within 20% of SLA.
- E2 and E3 may co-occur on the same service; report both.

## Output Contract

Write `result/ecs_skill_analysis.json` conforming to
`schemas/skill-analysis.schema.json` before running LangGraph.

LangGraph reads this file and assigns `finding_id`, `savings_group`, and
`evidence_facts`. Do not include those fields in the skill output.

```json
{
  "schema_version": "1.0",
  "domain": "ecs",
  "skill_version": "2.0",
  "findings": [
    {
      "rule_id": "ECS_E1_FARGATE_RIGHTSIZE",
      "resource": "<tf_resource_name>",
      "severity": "HIGH",
      "confidence": "MEDIUM",
      "estimated_monthly_saving_usd": 0.0,
      "evidence": ["cpu_avg_pct=12", "cpu_p95_pct=38", "errors=0", "desired_count=3"],
      "recommendation": "Reduce Fargate CPU/memory to next valid shape; canary and monitor p95 latency and errors.",
      "optimized_replacement": null
    }
  ]
}
```

Allowed `rule_id` values: `ECS_E1_FARGATE_RIGHTSIZE`, `ECS_E2_EC2_UNDERUTILIZED`,
`ECS_E3_MISSING_AUTOSCALING`, `ECS_E4_MISSING_SCHEDULED_SCALING`.

Set `estimated_monthly_saving_usd` to `0.0` when cost data is unavailable.
