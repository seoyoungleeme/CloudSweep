---
name: finops-lambda
description: >
  FinOps Lambda Analysis Skill. Detects Lambda cost inefficiencies from memory
  over-allocation, timeout misconfiguration, provisioned concurrency, ephemeral
  storage, architecture choice, and error/retry behavior using Terraform,
  CloudWatch metrics, and AWS cost reports.
user_invocable: false
---

# FinOps Lambda Analysis Skill

## Scope

Analyze AWS Lambda cost from a FinOps perspective. The goal is to reduce
unnecessary compute, request, provisioned concurrency, ephemeral storage, and
retry/error cost without increasing latency, throttling, cold-start risk, or
failure rates.

Important safety rule:

Do not downsize memory based only on average memory usage. Lambda memory also
controls CPU/network allocation, and lower memory can increase duration enough
to erase savings. Use p95/p99 duration, max memory used, error rate, throttles,
cold starts, and cost modeling before changing memory.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_lambda_function`, aliases, provisioned concurrency, event source mappings, environment, ephemeral storage, architecture, and tags | Cannot analyze; ask user for path |
| `metrics.json` | Duration avg/p95/p99/max, max memory used, invocations, errors, throttles, timeouts, concurrent executions, provisioned concurrency, iterator age, and cold-start evidence | Mark metrics section as unavailable |
| `cost_report.json` | Monthly Lambda cost history, pricing notes, architecture, requests, compute GB-seconds, provisioned concurrency, and ephemeral storage | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/overprovisioned_lambda.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| L1 | Memory appears over-allocated and modeled lower tier reduces total cost without latency/error risk | HIGH | RIGHTSIZE_MEMORY |
| L2 | Timeout greatly exceeds p99 duration and timeout/error path is costly | MEDIUM | REDUCE_TIMEOUT |
| L3 | Provisioned concurrency is enabled but utilization is low or schedule is too broad | HIGH | TUNE_PROVISIONED_CONCURRENCY |
| L4 | Ephemeral storage above free baseline without usage evidence | MEDIUM | REVIEW_EPHEMERAL_STORAGE |
| L5 | x86 function may be cheaper on arm64 and dependencies support it | LOW | MODEL_ARM64 |
| L6 | Errors, retries, throttles, or event-source backlog drive cost | MEDIUM | FIX_ERROR_RETRY_COST |

### Required Safety Checks

Before changing memory:

- Use `MaxMemoryUsed` and enough headroom, not average memory only.
- Model duration at the target memory tier when data exists, or recommend AWS
  Lambda Power Tuning instead of changing directly.
- Check p95/p99 duration, timeout rate, errors, throttles, concurrency, and cold
  start sensitivity.
- Preserve performance requirements for latency-sensitive functions.

Before reducing timeout:

- Use p99 or max successful duration, not average duration.
- Include upstream/downstream timeout contracts.
- Do not reduce timeout below expected batch, stream, or network retry needs.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Function count, runtime, architecture, memory size, timeout, ephemeral storage,
  reserved/provisioned concurrency, event source mappings, VPC config, and tags.
- Batch size, retry policy, maximum event age, DLQ/on-failure destination, and
  stream/queue source settings when visible.

### 3.2 Metric Evidence

- Invocations, duration avg/p95/p99/max.
- Max memory used and memory utilization.
- Errors, timeouts, throttles, retries, iterator age/backlog for stream/queue
  sources, concurrent executions, and provisioned concurrency utilization.
- Cold-start evidence when provided.

If only average duration or average memory is provided, lower confidence and
prefer a tuning experiment instead of a direct Terraform change.

### 3.3 Cost Evidence

- Monthly Lambda spend trend.
- Request cost, compute GB-seconds, provisioned concurrency, ephemeral storage,
  data transfer/VPC-related costs where available.
- Architecture-specific and region-specific pricing assumptions. Prefer cost
  report or AWS Pricing MCP over static fallback prices.
- Separate savings by source: memory, timeout/error path, provisioned
  concurrency, ephemeral storage, architecture, and retry reduction.

### 3.4 Root Cause

Frame root cause as architecture or governance, such as:

- Memory was set high for CPU performance but never power-tuned.
- Timeout is a broad default rather than workload-specific.
- Provisioned concurrency is enabled 24/7 for a workload with narrow peak hours.
- Retries or errors are inflating billed duration and downstream work.
- Ephemeral storage was increased for a temporary workload and not revisited.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like Lambda line items.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback prices in the rule file only as estimates.

Formula:

```text
compute_cost = invocations * duration_ms / 1000 * memory_gb * gb_second_price
request_cost = requests / 1,000,000 * request_price
provisioned_concurrency_cost = provisioned_concurrency_gb_seconds * pc_price
ephemeral_storage_cost = billable_ephemeral_storage_gb_seconds * ephemeral_price
```

Do not assume memory reduction saves linearly. Recalculate with modeled duration
at the new memory tier.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- If p95/p99 and cost model are incomplete, add a review or power-tuning plan
  instead of changing memory.
- Set memory to a valid Lambda memory value between 128 MB and 10,240 MB in
  1 MB increments when evidence supports it.
- Reduce timeout only when p99/max duration and upstream contracts support it.
- Tune provisioned concurrency schedules/values only when utilization evidence
  supports it.
- Add comments explaining evidence, expected savings, and rollback/monitoring.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps Lambda Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Lambda memory, timeout, provisioned concurrency, or retry inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<memory, timeout, runtime, architecture, concurrency, storage, event source config>

### Metrics
<duration p95/p99, max memory, errors, throttles, concurrency, retry/backlog>

### Cost Report
<compute, request, provisioned concurrency, storage, and pricing assumptions>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
1. Run Lambda Power Tuning for high-cost functions.
2. Alert on low memory utilization plus flat duration, high errors, and low provisioned concurrency utilization.
3. Review timeouts and retry policies per event source.

## Estimated Monthly Savings
$XX.XX, separated by savings source.

## Optimized Terraform
<real resource-based optimized Terraform or tuning plan>
```

Generated by: finops-lambda skill
