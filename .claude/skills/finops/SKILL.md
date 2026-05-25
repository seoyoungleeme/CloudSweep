---
name: finops
description: >
  FinOps Orchestrator — Inspects input files and routes to the appropriate
  resource-specific FinOps skill. Invoke for any FinOps cost analysis request
  when the specific resource type is unknown or mixed. Keywords: "FinOps",
  "cloud cost", "cost analysis", "AWS waste", "비용 분석".
user_invocable: false
---

# FinOps Orchestrator Skill

## Purpose

Use when a workspace contains AWS infrastructure files and the user asks for
cloud cost or FinOps analysis. Inspect inputs, identify domains, then route to
a single service skill (single-domain) or dispatch parallel subagents
(multi-domain).

## Input Slice Contract

**Multi-domain mode** — subagents receive inline slices only:
- `=== TERRAFORM ===`, `=== METRICS ===`, `=== COST REPORT ===`, `WORKLOAD_PATH`,
  and `RELATED_CONTEXT` in the subagent prompt are the **authoritative, complete
  inputs** for that domain.
- Subagents **must not** read `main.tf`, `metrics.json`, or `cost_report.json`
  from WORK_DIR. Full file reads are forbidden in this mode.
- If a section reads `"No matching metrics found..."` or `"No cost data..."`,
  state that in the report — do not rescan WORK_DIR.

**Standalone mode** (single domain, no inline slices) — full file access is
permitted; the domain skill's own Step 1 file-location rules apply.

## Inputs

| File | Purpose |
|------|---------|
| `main.tf` | Terraform infrastructure definition |
| `metrics.json` | CloudWatch or scenario metrics |
| `cost_report.json` | Monthly cost and waste evidence |
| `findings.json` | Existing analyzer output, when available |
| `parsed_input.json` | Existing parser output, when available |

If required evidence is missing, state exactly what is unavailable.

## Output Directory

Write all generated artifacts under `<WORK_DIR>/result/` (create if missing).
Example: `sample/season2/MA-001` → `sample/season2/MA-001/result/`.

---

## Domain Detection

After reading `main.tf`, list every service domain present:

| Resource keyword | Domain | Skill |
|-----------------|--------|-------|
| `aws_lb`, ALB, ELB | elb | `finops-elb` |
| `aws_ebs_snapshot` | ebs | `finops-ebs` |
| `aws_db_instance`, RDS | rds | `finops-rds` |
| `aws_s3_bucket` and lifecycle/versioning/policy | s3 | `finops-s3` |
| `aws_lambda_function`, aliases, concurrency, ESMs; `aws_iam_role` only when assume-role contains `lambda.amazonaws.com` | lambda | `finops-lambda` |
| `aws_dynamodb_table`, `aws_appautoscaling_target/policy`, GSI | dynamodb | `finops-dynamodb` |
| `aws_elasticache_replication_group` | elasticache | `finops-elasticache` |
| `aws_sqs_queue` | sqs | `finops-sqs` |
| `aws_kinesis_stream` | kinesis | `finops-kinesis` |
| `aws_nat_gateway`, VPC endpoints | nat | `finops-nat` |
| `aws_ec2_transit_gateway`, TGW attachment, peering | tgw | `finops-tgw` |
| AWS Organizations, RI/SP pooling | organizations | `finops-organizations` |
| `aws_cloudwatch_metric_alarm`, high-resolution metric | cloudwatch-alarm | `finops-cloudwatch-alarm` |
| `aws_cloudwatch_log_group` (non-lambda-scoped) | cloudwatch | `finops-cloudwatch` |
| `aws_sfn_state_machine`; `aws_cloudwatch_event_target` with `states` arn | stepfunctions | cross-service |
| `aws_cloudfront_distribution`, cache/origin | cloudfront | cross-service |
| `aws_vpc_endpoint`, private subnet → AWS svc via NAT | vpc-endpoint | via nat |

---

## Cross-Service Coupling

Run **after** domain detection, **before** routing.

This step must infer workload behavior from Terraform, metrics, cost, and
RELATED_CONTEXT. Do not use scenario IDs, filenames, assignment titles, or
hint text as proof of a finding. They can suggest what to inspect, but the
report must cite observable evidence or state the evidence gap.

### Workload Path

Trace: caller → network → compute → storage/API → egress.

| Layer | Resources |
|-------|-----------|
| Entry | `aws_lb`, `aws_api_gateway_*`, `aws_cloudfront_distribution`, SQS/S3 trigger |
| Compute | `aws_lambda_function`, `aws_ecs_service`, `aws_instance` |
| Network | `aws_vpc`, subnets, `aws_nat_gateway`, `aws_vpc_endpoint`, `aws_ec2_transit_gateway` |
| Storage/DB | `aws_s3_bucket`, `aws_dynamodb_table`, `aws_db_instance`, `aws_elasticache_replication_group` |
| Orchestration | `aws_sfn_state_machine`, `aws_cloudwatch_event_rule` |
| Egress | `aws_internet_gateway`, `aws_nat_gateway`, `aws_cloudfront_distribution` |

Build `caller → [NAT|Endpoint] → compute → [S3|DynamoDB|RDS] → egress` and
pass as `WORKLOAD_PATH` in every subagent prompt.

### Request-Amplification Check

For every compute domain connected to storage/API domains, check whether
downstream calls are the cost driver before applying only service-local rules.

Evidence to derive when present:
- `downstream_requests_per_compute_invocation =
  downstream_request_count / compute_invocation_count`
- co-movement of compute duration/cost and downstream request rate
- request-cost share versus storage/capacity share
- cache layer evidence: CloudFront, ElastiCache, DAX, API Gateway cache,
  Lambda execution-context/extension cache, or app-level cache metric

If request metrics exist but invocation/cache metrics are missing, report the
finding as `Suspected request amplification` with instrumentation required
instead of forcing an unrelated local remediation. If both sides are present
and the ratio is repeatedly high, prioritize request reduction/caching over
memory rightsizing, lifecycle, or capacity changes.

### Cascade Patterns

| Pattern | Surface | Driver | Signal |
|---------|---------|--------|--------|
| Compute → storage/API request amplification | Compute duration + request spend | Repeated downstream calls; no cache evidence | downstream requests / invocation |
| Lambda → S3 GET no cache | Lambda duration | S3 GETs + transfer | GetObject/invocation ratio |
| Polling Lambda → SFN | SFN transitions | Lambda × retry multiplier | ExecutionsFailed ratio |
| Private subnet → AWS svc via NAT | NAT GB | Eliminable with Gateway Endpoint | Route table, no endpoint |
| Low CloudFront hit → origin | CF spend | Origin compute | CacheHitRate < 80% |
| Retry loop | Lambda/ECS errors | DB writes + NAT + logs | Errors + ConsumedWCU spike |
| ECS → S3/DynamoDB via NAT | NAT GB | Gateway Endpoint eliminates it | Private subnet, no endpoint |

Formulas (NAT/Endpoint, Step Functions, CloudFront) and remediation templates:
`references/cross-service-playbooks.md`.

---

## Pricing & MCP

Default policy: scenario `cost_report` → aws-pricing MCP → rule fallback →
`[estimate]`. MCP unavailable → fall back immediately, never block. Cite
`mcp__aws-docs__search_documentation` URL for each remediation. Service codes,
call template, and full pricing rules: `references/pricing-policy.md`.

---

## Single-Domain Routing

If **exactly one domain** is detected: read `.claude/skills/finops-[service]/SKILL.md`
and follow its instructions in **standalone mode** (full file access permitted).

## Multi-Domain Dispatch

If **two or more domains** are detected: prefer parallel subagents; fall back
to sequential with isolated context per domain (no shared state).

### Step 1 — Build per-domain slices

Never pass an unsliced full file to any subagent.

**1-a. TF chunk** — Extract `resource` blocks from `main.tf` whose type matches
this domain's keywords. Include associated resources: autoscaling
targets/policies, lifecycle rules, log groups, route tables, endpoint
associations, target groups, listeners, GSI blocks. Preserve comment headers.
**Verify**: ≥ 1 `resource` block — empty chunk means false detection, remove domain.

**1-b. Metrics slice** — Identifiers per domain from the TF chunk:
- Terraform local name (`resource "TYPE" "NAME"`)
- Config values: `function_name`, `bucket`, `table_name`, `queue_name`,
  `stream_name`, `name`, `log_group_name`, cluster/service name, `tags.Name`, ARN suffix
- Associated resources (autoscaling target, GSI, log group, route table, target group, listener)

Grep `metrics.json` for each identifier (quoted). Read matched line ranges.
**Size gate**: raw slice > 20 KB → replace with per-metric summary:
`resource: NAME  metric: KEY  count: N  min/max/avg/p95/p99: X`.
**Verify**: no match → pass `"No matching metrics found for this domain"`. Never pass full file.

**1-c. Cost slice** — Match `service` (case-insensitive) using aliases in
`references/domain-aliases.md`. Aggregate from `monthly_data[].services[]`:
```
period_months          = cost_report.period_months  OR  len(monthly_data)
total_period_spend_usd = sum(matched spend_usd across months)
avg_monthly_spend_usd  = total_period_spend_usd / period_months
contains_waste         = any(matched contains_waste == true)
```
Include `monthly_series` only for anomaly/spike analysis. Extract
domain-relevant sentences from `summary.pricing_note`.

Pass only:
```json
{
  "avg_monthly_spend_usd": <number>,
  "total_period_spend_usd": <number>,
  "period_months": <int>,
  "contains_waste": <bool>,
  "pricing_note": "<domain-relevant substring>"
}
```
**Verify**: no match → pass `"No cost data for this domain in cost_report.json"`. Never pass full file.

**1-d. RELATED_CONTEXT** — Build once from the workload path and adjacent
domain summaries, then pass the relevant subset to each subagent.
- dependency edges inferred from Terraform references, env vars, IAM policies,
  event sources, resource names, tags, or scenario metrics keys
- compute-side metrics: invocations/request count, duration avg/p95/p99,
  errors/retries/timeouts when available
- storage/API-side metrics: GET/HEAD/LIST/read/write request count, throttles,
  request-cost share, storage/capacity share when available
- derived ratios: downstream requests per invocation, cache hit rate, and
  co-movement notes; use `Not available` for missing inputs
- cache evidence: CloudFront, ElastiCache, DAX, API Gateway cache, Lambda
  extension/execution-context cache, or app-level cache metric

Never fill RELATED_CONTEXT from scenario ID alone. If the ratio cannot be
computed, preserve the question for the subagent as an instrumentation gap.

### Step 2 — Spawn parallel subagents

Each subagent prompt must include:

```
You are a [DOMAIN] FinOps domain expert. Analyze ONLY the inline slices below.
Do NOT read WORK_DIR/main.tf, metrics.json, or cost_report.json — those are off-limits.

Step 1 — Read .claude/skills/finops-[service]/SKILL.md. The skill's file-location
  instructions do not apply; your inputs are the inline slices.

Step 2 — Verify pricing via mcp__aws-pricing__get_pricing (service_code per
  references/pricing-policy.md, region from provider, tight filters,
  max_results=10, output_options={"pricing_terms":["OnDemand"]}).
  Cross-check only; scenario pricing_note is the final estimate.

Step 3 — Fetch a doc URL via mcp__aws-docs__search_documentation (REQUIRED).

Step 4 — Cross-service check: using WORKLOAD_PATH and RELATED_CONTEXT, identify
  upstream drivers and downstream impacts. If cascade confirmed:
  total_workload_cost = compute + requests + storage_or_db + network + logs + orchestration
  Always run the generic request-amplification/cache-miss check when compute
  and storage/API domains are both present. Do not infer it from scenario_id;
  cite invocation/request/cache evidence or mark the instrumentation gap.

Step 5 — Per finding output:
  1. Resource name, rule ID, severity, evidence (+ cascade sub-row if any).
  2. Optimized TF fragment (real names, no placeholders).
  3. Monthly savings with arithmetic and pricing source.
  4. Confidence: High / Medium / Low with reason.
  5. Doc URL.
  6. MCP result: called / unavailable / skipped.

WORK_DIR: <path>
RESULT_DIR: <WORK_DIR>/result
DOMAIN: <domain>
RESOURCES: <TF local names>
WORKLOAD_PATH: <e.g. "ALB → Lambda → DynamoDB via NAT">
RELATED_CONTEXT: <upstream/downstream names; route/NAT/endpoint facts;
  dependency edges; invocation/request ratios; cache-layer evidence; request
  cost share; avg_monthly_spend_usd + GB summary for adjacent domains. Raw
  file content excluded.>

=== TERRAFORM ([DOMAIN] — [N] blocks) ===
<TF chunk from Step 1-a>

=== METRICS ([DOMAIN]) ===
<Metrics slice or "No matching metrics found for this domain">

=== COST REPORT ([DOMAIN]) ===
<Cost slice JSON or "No cost data for this domain in cost_report.json">
```

### Step 3 — Aggregate

Merge findings into `result/finops_report.md` (template: `references/report-template.md`)
and merge optimized TF into `result/main_optimized.tf`. Full aggregation and
scoring rules: `references/scoring.md`.

---

## Outputs

1. `result/finops_report.md` — unified 4-section report.
2. `result/main_optimized.tf` — merged optimized Terraform across all domains.
3. Concise final response: changed files, per-domain recall, verification gaps.

---

## Reference Index

| When to read | File | Look for |
|-------------|------|----------|
| Building cost slice | `references/domain-aliases.md` | service alias table |
| Pricing / MCP call | `references/pricing-policy.md` | service codes, call template |
| Cascade formulas, remediations | `references/cross-service-playbooks.md` | Request-Amplification, Cost Formulas, VPC Endpoint, SFN, CloudFront, Athena, Anomaly |
| Report writing | `references/report-template.md` | 4-section layout, Agent Performance JSON |
| Aggregation / scoring | `references/scoring.md` | guardrails, recall denominator, aggregation steps |

Generated by: finops orchestrator skill — Claude Code
