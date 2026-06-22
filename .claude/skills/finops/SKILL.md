---
name: finops
description: Run CloudSweep LangGraph analysis, review machine findings, and deterministically finalize AWS FinOps outputs.
user_invocable: true
---

# FinOps Orchestrator

## Authority Boundary

**Simple and GenAI domains** (lambda, s3, dynamodb, bedrock, sagemaker, ec2,
ebs, cloudwatch, cloudwatch-alarm, sqs, kinesis, nat, tgw, organizations):
LangGraph Python analyzers own detection, thresholds, savings arithmetic, and
Terraform remediation candidates. Claude is the reviewer only.

**Complex domains** (rds, elb, ecs, elasticache):
LangGraph owns deterministic candidate detection, thresholds, savings arithmetic,
and Terraform candidates. Claude domain skills own contextual disposition:
`accepted`, `rejected`, or `needs_evidence`. Claude must not add candidates or
change LangGraph arithmetic.

## Inputs

Set `WORK_DIR` to the workload or scenario directory. CloudSweep inventories
supported evidence such as Terraform, metrics, parsed input, cost reports,
GenAI evidence, Cost Explorer responses, anomaly results, and CloudTrail events.

All generated artifacts belong under `<WORK_DIR>/result/`.

## Required Workflow

1. Inventory evidence under `WORK_DIR` and detect which domains are present.

   When evidence comes from MiniStack, collect it before domain analysis:

```text
python -m cloudsweep <WORK_DIR> --from-ministack --collect-only
```

2. Run LangGraph once. For each complex domain it writes
   `result/{domain}_skill_request.json` containing deterministic candidates.

3. **For each complex domain request** (rds, elb, ecs, elasticache), run the
   corresponding Claude skill so it writes contextual decisions:

   | Domain | Skill | Output file |
   |--------|-------|-------------|
   | rds | finops-rds | `result/rds_skill_analysis.json` |
   | elb | finops-elb | `result/elb_skill_analysis.json` |
   | ecs | finops-ecs | `result/ecs_skill_analysis.json` |
   | elasticache | finops-elasticache | `result/elasticache_skill_analysis.json` |

   Simple and GenAI domains do not need a pre-run step.

4. Rerun the LangGraph machine analysis:

```text
python -m cloudsweep <WORK_DIR>
```

   LangGraph loads any `result/{domain}_skill_analysis.json` files it finds and
   enriches them with `finding_id`, `savings_group`, and `evidence_facts`.
   If a complex-domain decision output is missing, LangGraph emits only
   `needs_skill_review` candidates and `result/{domain}_skill_request.json`.
   Those candidates must have zero savings and no Terraform patch. Run the
   missing domain Skill and rerun LangGraph; never treat the candidates as the
   final complex-domain analysis.

5. Read `result/cloudsweep_graph_state.json`. Treat an `unsupported` status in
   `analyzer_coverage` as an error. Do not replace a missing analyzer with
   Claude arithmetic.

6. Review every finding using its `finding_id` and `evidence_facts`.
   For complex domain findings, preserve the domain Skill disposition and focus
   this review on cross-domain patterns and final safety constraints.
   Choose exactly one disposition: `accepted`, `rejected`, or `needs_evidence`.

7. Use pricing or documentation MCP only for findings whose machine enrichment
   is `evidence_only` or `unavailable`. Reuse already verified sources.

8. Write `result/claude_review.json` using
   `schemas/claude-review.schema.json`. Claude may add review confidence,
   rationale, documentation links, and fact-backed cross-domain statements. It
   may not add or change `estimated_monthly_saving_usd`.

9. Finalize deterministically:

```text
python -m cloudsweep finalize <WORK_DIR> --review <WORK_DIR>/result/claude_review.json
```

## Review Rules

- Cite `fact_id` values for every observed cross-domain statement.
- Mark an unobserved relationship as `hypothesis`; exclude it from savings.
- Prefer `needs_evidence` when ownership, SLA, compliance, dependency, peak,
  or cross-account evidence is missing.
- Never apply Terraform. The finalizer only writes a candidate file.
- Accept a Terraform candidate only when its source hash still matches.
- Do not double count alternative findings or organization and workload savings.

## Outputs

Machine outputs:

```text
result/cloudsweep_graph_state.json
result/cloudsweep_graph_report.md
result/cloudsweep_main_optimized.tf
```

Claude output:

```text
result/claude_review.json
```

Finalizer outputs:

```text
result/finops_report.md
result/main_optimized.tf
```
