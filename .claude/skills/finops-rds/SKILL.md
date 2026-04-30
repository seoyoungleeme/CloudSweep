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

Analyze Amazon RDS cost from a FinOps perspective. The goal is to reduce
unnecessary database spend while preserving availability, durability,
performance, backup/restore, compliance, and maintenance requirements.

Important safety rule:

Do not downsize or disable Multi-AZ based only on average CPU or environment
tags. Check p95/max CPU, memory/freeable memory, connections, IOPS, storage,
latency, queue depth, failover/SLA requirements, backup/DR requirements, and
reserved instance coverage first.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_db_instance`, storage, Multi-AZ, backups, replicas, monitoring, and tags | Cannot analyze; ask user for path |
| `metrics.json` | CPU avg/p95/max, connections, freeable memory, read/write IOPS, throughput, latency, storage, queue depth, replicas, and failover evidence | Mark metrics section as unavailable |
| `cost_report.json` | Monthly RDS cost history, pricing notes, RI coverage, Extended Support, storage, IOPS, backup, and transfer cost | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/overprovisioned_rds.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| R1 | Multi-AZ enabled on non-production with no SLA/DR requirement evidence | MEDIUM | REVIEW_SINGLE_AZ |
| R2 | Instance class underutilized across CPU, memory, connections, and I/O with safe p95/max | HIGH | REVIEW_DOWNSIZE |
| R3 | Provisioned storage, IOPS, or throughput exceeds observed needs | MEDIUM | REVIEW_STORAGE_IOPS |
| R4 | Old engine version incurs Extended Support cost | HIGH | UPGRADE_ENGINE |
| R5 | Steady retained baseline lacks Reserved DB Instance coverage | LOW | MODEL_RESERVED_INSTANCE |
| R6 | Performance risk exists: high CPU, low memory, high I/O, high latency, or throttling | INFO | DO_NOT_DOWNSIZE_REVIEW_PERFORMANCE |

### Required Safety Checks

Before downsizing:

- Check CPU avg, p95, and max.
- Check FreeableMemory, SwapUsage, connections, read/write IOPS, throughput,
  latency, DiskQueueDepth, storage free space, and burst balance where relevant.
- Check read replicas, Multi-AZ, backup window, maintenance window, and engine
  family compatibility.
- Check reserved instance coverage before changing instance class/family.
- Prepare snapshot, maintenance window, rollback, and post-change monitoring.

Before disabling Multi-AZ:

- Confirm workload is non-production or has explicit reduced availability
  tolerance.
- Confirm RTO/RPO, failover, backup, restore, and maintenance needs.
- Confirm no compliance or customer-facing SLA requires Multi-AZ.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- DB instance count, engine, version, instance class, storage type/size,
  allocated/max storage, IOPS/throughput, Multi-AZ, replicas, backups, deletion
  protection, Performance Insights, monitoring, and tags.

### 3.2 Metric Evidence

- CPU avg/p95/max, connections, freeable memory, swap, IOPS, throughput,
  latency, disk queue, storage free, replica lag, and failover/maintenance
  evidence when available.
- Lower confidence if only CPU average is available.

### 3.3 Cost Evidence

- Monthly RDS spend trend.
- Instance hours, Multi-AZ, storage, IOPS, backup, data transfer, Extended
  Support, Performance Insights, and RI coverage when available.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.

### 3.4 Root Cause

Frame root cause as architecture or governance, such as:

- Instance class was selected for a historical peak and never revisited.
- Multi-AZ is applied uniformly to non-production without SLA review.
- Storage/IOPS settings are static and not tied to observed workload.
- Engine versions are past standard support.
- RI coverage does not match the retained database baseline.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like RDS line items.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback prices in the rule file only as estimates.

Separate savings by source: instance class, Multi-AZ, storage, IOPS/throughput,
backup, Extended Support, and RI coverage. Do not count RI purchase savings
unless utilization and term risk are modeled.

For R5 (Reserved Instance coverage): if the applicable RI term options, payment
options, or engine-specific eligibility (e.g. Aurora vs RDS, custom engine
versions) are unclear from the provided data, call `aws-docs` to verify before
modeling savings. Do not call aws-docs when term and engine are already confirmed
in cost_report or the rule file covers the case.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- If metric coverage is incomplete, generate a review plan instead of changing
  instance class or Multi-AZ.
- For confirmed downsizing, use conservative target classes and include a
  snapshot, maintenance window, rollback, and 7-14 day monitoring plan.
- Do not disable Multi-AZ when SLA/DR/compliance requirements are unknown.
- Add comments explaining evidence and risk controls.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps RDS Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | RDS instance, availability, storage, or commitment inefficiency |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<engine, class, Multi-AZ, storage, backups, replicas, RI coverage>

### Metrics
<CPU, memory, connections, IOPS, latency, storage, replica/failover evidence>

### Cost Report
<instance, Multi-AZ, storage, IOPS, backup, Extended Support, RI cost>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
1. Review rightsizing quarterly.
2. Alert on low utilization and performance risk.
3. Track RI coverage for retained steady databases.

## Estimated Monthly Savings
$XX.XX, separated by savings source.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```

Generated by: finops-rds skill
