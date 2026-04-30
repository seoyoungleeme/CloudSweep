---
name: finops-sqs
description: >
  FinOps SQS Analysis Skill. Detects SQS cost inefficiencies from short polling,
  excessive empty receives, inefficient batching, retry/DLQ behavior, and
  queue configuration mismatches using Terraform, CloudWatch metrics, and AWS
  cost reports.
user_invocable: false
---

# FinOps SQS Analysis Skill

## Scope

Analyze Amazon SQS cost from a FinOps perspective. The goal is to reduce
unnecessary API requests and retry waste while preserving latency, consumer
throughput, message visibility, FIFO ordering, DLQ behavior, and application
timeouts.

Important safety rule:

Long polling is usually a strong cost optimization for empty receives, but do
not blindly set every queue to 20 seconds without checking consumer HTTP/read
timeouts, latency requirements, Lambda event source behavior, FIFO throughput,
and backlog/age metrics.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_sqs_queue`, redrive policy, queue policy, event source mapping, and tags | Cannot analyze; ask user for path |
| `metrics.json` | Empty receives, receives, messages sent/deleted, visible/not visible messages, age of oldest message, DLQ movement, and consumer metrics | Mark metrics section as unavailable |
| `cost_report.json` | Monthly SQS request cost history and pricing notes | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/short_polling_sqs.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| Q1 | `receive_wait_time_seconds = 0` and empty receives are high | HIGH | ENABLE_LONG_POLLING |
| Q2 | Long polling is already enabled but empty receives remain high | MEDIUM | REVIEW_CONSUMER_POLLING |
| Q3 | Receive/delete/send request volume suggests batching opportunity | MEDIUM | REVIEW_BATCHING |
| Q4 | High retries, DLQ movement, or message age drives repeated receives | MEDIUM | FIX_RETRY_VISIBILITY |
| Q5 | Client timeout or latency constraints are unknown | INFO | VALIDATE_CLIENT_TIMEOUTS |

### Required Safety Checks

Before setting `receive_wait_time_seconds = 20`:

- Confirm consumer HTTP/read timeout is greater than wait time.
- Confirm business latency requirements tolerate long polling.
- Confirm Lambda event source mappings or SDK consumers behave correctly.
- Check `ApproximateAgeOfOldestMessage`, visible/not visible message counts,
  errors, retries, and DLQ movement.
- For FIFO queues, check message groups and throughput behavior.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Queue count, standard vs FIFO, `receive_wait_time_seconds`, visibility
  timeout, message retention, redrive policy, DLQ, encryption, and tags.
- Event source mappings or consumer hints when present.

### 3.2 Metric Evidence

- Empty receives, total receives, empty receive ratio, messages sent/deleted,
  visible/not visible messages, age of oldest message, DLQ movement, and error
  evidence.
- Distinguish idle queues from inefficient polling under real traffic.

### 3.3 Cost Evidence

- Monthly SQS spend trend.
- Request cost by action when available.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.
- Separate savings from long polling, batching, retry reduction, and queue
  cleanup.

### 3.4 Root Cause

Frame root cause as consumer or queue configuration:

- Consumers short poll frequently while queues are often empty.
- Batch APIs are not used for high-volume send/delete/receive.
- Visibility timeout is too low, causing repeated receives.
- DLQ/redrive behavior or application errors inflate request volume.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like SQS API request line items.
2. Use request metrics and region-specific pricing.
3. Use static fallback pricing only as an estimate.

Do not assume long polling eliminates all empty receives. Model partial
reduction and report assumptions.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Set `receive_wait_time_seconds = 20` only for flagged queues where client
  timeout/latency constraints are acceptable or explicitly unknown with a review
  comment.
- Add comments explaining client timeout validation and post-change monitoring.
- Do not change visibility timeout, DLQ, or FIFO settings without evidence.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps SQS Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | SQS polling, batching, or retry inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<queue settings, DLQ, visibility, event sources, tags>

### Metrics
<empty receives, request ratio, message age, backlog, DLQ/retry evidence>

### Cost Report
<request cost and pricing assumptions>

## Root Cause
<consumer or queue configuration cause>

## Proposed Solution

### Immediate Actions
1. Validate client read timeouts and latency requirements.
2. Enable long polling for flagged queues.
3. Review batching and retry behavior where relevant.

### Preventive Actions
1. Default new queues to long polling unless latency exception is documented.
2. Alert on high empty receive ratio and message age.
3. Review batching and DLQ metrics monthly.

## Estimated Monthly Savings
$XX.XX, separated by savings source.

## Optimized Terraform
<real resource-based optimized Terraform>
```

Generated by: finops-sqs skill
