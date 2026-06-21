---
name: finops-elb
description: >
  FinOps ELB Analysis Skill. Detects cost waste in idle or underutilized AWS
  load balancers (ALB/NLB/CLB) using Terraform, CloudWatch metrics, and AWS
  cost reports. Checks DNS, listener, target group, blue-green, and DR
  dependencies before flagging for deletion.
user_invocable: false
---

# FinOps ELB Analysis Skill

## Scope

Identify idle or overprovisioned load balancers while preserving active
traffic paths, blue-green deployments, DR standby capacity, and
certificate/WAF dependencies.

## Required Evidence

| File | Used For | If Missing |
|------|----------|------------|
| `main.tf` | `aws_lb`, `aws_alb`, `aws_elb`, listeners, target groups, certificates, WAF, DNS records | Cannot analyze; ask for path |
| `metrics.json` | RequestCount, ActiveConnectionCount, NewConnectionCount, ProcessedBytes, HealthyHostCount, UnHealthyHostCount | Mark metrics unavailable |
| `cost_report.json` | Monthly ELB/ALB cost per resource | Mark cost unavailable |

Missing facts → write `Not available in the provided data; verify in the real environment.`

## Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| LB1 | Zero requests AND zero active connections over observation period | HIGH | REVIEW_DELETE_IDLE_ALB |
| LB2 | Very low request rate (<100/day) with all healthy targets | MEDIUM | REVIEW_CONSOLIDATE |
| LB3 | NLB with no TLS offload or WAF requirement (ALB features unused) | LOW | REVIEW_DOWNGRADE_TO_NLB |
| LB4 | Classic Load Balancer (CLB) still in use | MEDIUM | MIGRATE_TO_ALB |
| LB5 | Listener exists but all target groups are empty | HIGH | REVIEW_DELETE_STALE_LISTENER |

## Safety Guardrails

- Do not flag for deletion when DNS records (Route 53 or external) point to
  the load balancer — check `aws_route53_record` aliases in the Terraform slice.
- Do not flag when blue-green or canary deployment evidence is present (multiple
  target groups, weighted routing, or `deployment_group` references).
- Do not flag when the load balancer is a DR standby (tagged `Environment=dr`
  or `Purpose=standby`).
- Treat incomplete metrics (observation window <7 days) as confidence=LOW.
- NLB metrics differ from ALB — `ActiveFlowCount` replaces `ActiveConnectionCount`;
  adjust rule LB1 accordingly.

## Output Contract

Write `result/elb_skill_analysis.json` conforming to
`schemas/skill-analysis.schema.json` before running LangGraph.

LangGraph reads this file and assigns `finding_id`, `savings_group`, and
`evidence_facts`. Do not include those fields in the skill output.

```json
{
  "schema_version": "1.0",
  "domain": "elb",
  "skill_version": "2.0",
  "findings": [
    {
      "rule_id": "ELB_LB1_UNUSED",
      "resource": "<tf_resource_name>",
      "severity": "HIGH",
      "confidence": "HIGH",
      "estimated_monthly_saving_usd": 0.0,
      "evidence": ["request_count_sum=0", "active_connection_count_max=0", "no Route53 alias found"],
      "recommendation": "Verify DNS, certificates, WAF, and DR dependencies, then delete if confirmed idle.",
      "optimized_replacement": null
    }
  ]
}
```

Allowed `rule_id` values: `ELB_LB1_UNUSED`, `ELB_LB2_LOW_UTILIZATION`,
`ELB_LB3_REVIEW_NLB_DOWNGRADE`, `ELB_LB4_MIGRATE_CLB`, `ELB_LB5_STALE_LISTENER`.

Set `estimated_monthly_saving_usd` to `0.0` when cost data is unavailable.
