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

Use this skill when a workspace contains AWS infrastructure files and the user
asks for cloud cost, waste, or FinOps analysis. The orchestrator inspects
available files, identifies the AWS services in scope, then either delegates to
a single service skill (single-domain) or dispatches parallel subagents
(multi-domain).

## Inputs

Look for these files anywhere under the working directory:

| File | Purpose |
|------|---------|
| `main.tf` | Terraform infrastructure definition |
| `metrics.json` | CloudWatch or scenario metrics |
| `cost_report.json` | Monthly cost and waste evidence |
| `findings.json` | Existing analyzer output, when available |
| `parsed_input.json` | Existing parser output, when available |

If required evidence is missing, state exactly what is unavailable and avoid
guessing.

## Domain Detection

After reading `main.tf`, list every service domain present using this table:

| Resource keyword | Domain | Skill |
|-----------------|--------|-------|
| `aws_lb`, ALB, ELB | elb | `finops-elb` |
| `aws_ebs_snapshot` | ebs | `finops-ebs` |
| `aws_db_instance`, RDS | rds | `finops-rds` |
| `aws_s3_bucket`, lifecycle/versioning | s3 | `finops-s3` |
| `aws_lambda_function` | lambda | `finops-lambda` |
| `aws_dynamodb_table` | dynamodb | `finops-dynamodb` |
| `aws_elasticache_replication_group` | elasticache | `finops-elasticache` |
| `aws_sqs_queue` | sqs | `finops-sqs` |
| `aws_kinesis_stream` | kinesis | `finops-kinesis` |
| `aws_nat_gateway`, VPC endpoints | nat | `finops-nat` |
| `aws_ec2_transit_gateway`, TGW attachment, VPC peering | tgw | `finops-tgw` |
| AWS Organizations, RI/SP pooling | organizations | `finops-organizations` |
| `aws_cloudwatch_metric_alarm`, high-resolution metric | cloudwatch-alarm | `finops-cloudwatch-alarm` |
| `aws_cloudwatch_log_group`, retention policy | cloudwatch | `finops-cloudwatch` |

## MCP Integration

Two MCP servers are available. Use them at every opportunity — they provide
real-time pricing and authoritative documentation that static rule files cannot.

### aws-pricing MCP

| Tool | When to call |
|------|-------------|
| `mcp__aws-pricing__get_pricing_service_codes` | Once per run to confirm the correct service code before any pricing query |
| `mcp__aws-pricing__get_pricing` | For every savings calculation when `cost_report.json` has no `pricing_note`, or to verify a `pricing_note` against live prices |

**Service code map** (use with `get_pricing`):

| Domain | service_code |
|--------|-------------|
| lambda | `AWSLambda` |
| dynamodb | `AmazonDynamoDB` |
| s3 | `AmazonS3` |
| elb | `AWSELB` |
| rds | `AmazonRDS` |
| elasticache | `AmazonElastiCache` |
| kinesis | `AmazonKinesis` |
| sqs | `AmazonSQS` |
| nat / ebs / ec2 | `AmazonEC2` |
| cloudwatch | `AmazonCloudWatch` |

Always pass `region` matching the Terraform provider region (default `us-east-1`).
Use `output_options: {"pricing_terms": ["OnDemand"]}` to keep responses small.

### aws-docs MCP

| Tool | When to call |
|------|-------------|
| `mcp__aws-docs__search_documentation` | For every remediation recommendation — fetch the canonical doc URL and cite it in the report |

Typical queries: `"DynamoDB auto scaling provisioned capacity"`,
`"S3 lifecycle configuration Glacier transition"`,
`"Lambda memory power tuning"`.

---

## Single-Domain Routing

If **exactly one domain** is detected: read `.claude/skills/finops-[service]/SKILL.md`
and follow its full instructions directly (no subagent needed).

## Multi-Domain Dispatch

If **two or more domains** are detected in `main.tf`:

### Step 1 — Prepare per-domain inputs

For each detected domain, extract:

- **TF chunk** — `resource` blocks whose type matches the domain (from the
  Domain Detection table) **plus all associated configuration resources**
  (e.g., `aws_s3_bucket_lifecycle_configuration` and
  `aws_s3_bucket_versioning` belong to the s3 domain;
  `aws_appautoscaling_target` for a DynamoDB table belongs to the dynamodb
  domain). Preserve section comment headers so the subagent can orient itself.
- **Metrics slice** — filter `metrics.json` by resource key prefix that maps
  to that domain's resources. Use Grep on the metrics file with each resource
  name from the TF chunk to locate its key, then Read only those line ranges.
  For large metrics files (>100 KB), pass statistical summaries (min/max/avg/
  p95/p99 per metric) rather than raw datapoints.
- **Cost slice** — the matching `services[]` entry from `cost_report.json`
  plus the `summary.pricing_note` substring relevant to that domain.

### Step 2 — Spawn parallel subagents

Use the **Agent tool** to launch one subagent per domain simultaneously.
Do NOT run them sequentially.

Each subagent prompt must include all of the following inline:

```
You are a [Lambda / S3 / DynamoDB / …] FinOps domain expert.

Step 1 — Read the skill rules:
  Read .claude/skills/finops-[service]/SKILL.md and follow its analysis rules.

Step 2 — Fetch live pricing (REQUIRED):
  Call mcp__aws-pricing__get_pricing with:
    service_code: [see service code map in finops/SKILL.md]
    region: [from Terraform provider, default us-east-1]
    output_options: {"pricing_terms": ["OnDemand"]}
  Use the returned prices for savings arithmetic.
  If the MCP call fails, fall back to cost_report pricing_note, then rule file.

Step 3 — Fetch documentation reference (REQUIRED):
  Call mcp__aws-docs__search_documentation with a query specific to the
  waste pattern found (e.g. "Lambda memory right-sizing power tuning").
  Include the top result URL in the report under each remediation.

Step 4 — Produce output:
1. Waste findings — resource name, pattern ID, severity, evidence.
2. Optimized Terraform fragment — real resource names, no placeholders.
3. Monthly savings estimate — show full arithmetic with MCP-sourced prices.
4. Confidence level — High / Medium / Low with reason.
5. Doc reference — URL from aws-docs MCP per finding.

WORK_DIR: <absolute path to the scenario directory>

=== TERRAFORM (this domain only) ===
<filtered TF chunk>

=== METRICS (this domain only — statistical summaries for large files) ===
<filtered metrics slice>

=== COST REPORT (this domain only) ===
<filtered cost slice as JSON>
```

### Step 3 — Aggregate results

After all subagents complete:

1. Merge all domain findings into one `finops_report.md` (sections per domain,
   summary table at the top).
2. Merge all optimized TF fragments into one `main_optimized.tf` (preserve
   unchanged resources from every domain).
3. Add a **Cross-Domain Interactions** section noting emergent findings only
   visible when all domains are in view (e.g., Lambda calling an
   over-provisioned DynamoDB table — both wastes compound).
4. Sum savings with a per-domain breakdown table.
5. If any subagent skipped the MCP pricing step (e.g., due to tool denial),
   call `mcp__aws-pricing__get_pricing` directly here for that domain and
   patch the savings figure before writing the final report.

## Analysis Rules

- Base conclusions on cross-file evidence from the workspace.
- Always read `main.tf`, `metrics.json`, and `cost_report.json` when present
  before choosing a remediation.
- Mark missing facts as `Not available in the provided data; verify in the
  real environment`.
- Do not claim live AWS state unless it is explicitly present in the files.
- Keep Terraform changes scoped to the affected resources.
- Preserve real resource names and avoid placeholders.
- Preserve decoy or healthy resources. Never delete or modify resources whose
  tags, metrics, or cost evidence mark them as compliant, active, retained, or
  outside the detected waste pattern.
- Compute savings from the provided cost report or official AWS unit prices and
  show the arithmetic. Keep estimates tied to the affected resources only.
- Always produce `finops_report.md`; `main_optimized.tf` alone is incomplete.
- Prefer configuration fixes over deletion when the waste type is lifecycle,
  retention, polling, rightsizing, or routing related.

## Scoring Guardrails

Use this checklist before final output:

1. Scenario match: every detected domain has a corresponding finding.
2. Cross evidence: every finding cites Terraform, metrics, and cost evidence,
   or clearly states what is unavailable.
3. Decoy preservation: normal resources remain unchanged in `main_optimized.tf`.
4. Savings accuracy: savings are within a reasonable range of cost evidence.
5. Report completeness: `finops_report.md` includes problem, evidence, root
   cause, remediation, prevention, and savings for each domain.

## Outputs

When enough evidence is present, produce:

1. `finops_report.md` — all domain findings, cross-domain interactions, savings
   summary.
2. `main_optimized.tf` — merged optimized Terraform for all affected domains.
3. A concise final response with changed files, per-domain recall, and any
   verification gaps.

### Required Measurement Block (multi-domain runs only)

Include this table at the top of `finops_report.md`:

```markdown
## Analysis Metrics
| Metric | Value |
|--------|-------|
| Recall | X / Y patterns found |
| Domains analyzed | N |
| Agent count | 1 orchestrator + N domain experts |
| Total tokens (est.) | input + output across all agents |
| Wall-clock time (est.) | seconds from dispatch to aggregation |
| Est. analysis cost | tokens × $0.000003/token (Sonnet) |
```

Recall denominator comes from the count of seeded or known waste patterns
(check `cost_report.json` `_fusion_components` or scenario metadata).

Generated by: finops orchestrator skill — Claude Code
