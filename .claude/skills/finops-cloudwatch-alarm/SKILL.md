---
name: finops-cloudwatch-alarm
description: >
  FinOps CloudWatch Metric Alarm Analysis Skill. Detects cost waste in
  aws_cloudwatch_metric_alarm resources caused by unnecessary high-resolution
  metric publishing (1-second period) when standard resolution (60-second) is
  sufficient. High-resolution custom metrics cost $0.90/metric/month vs
  $0.30/metric/month for standard. Use for Terraform configurations, CloudWatch
  metrics, and AWS cost reports containing aws_cloudwatch_metric_alarm resources.
  Keywords: "CloudWatch alarm cost", "high resolution metric", "metric resolution",
  "custom metric overprovisioning", "alarm overprovisioning".
user_invocable: false
---

# FinOps CloudWatch Metric Alarm Analysis Skill

## Scope

Analyze AWS CloudWatch Metric Alarm configuration from a FinOps perspective.
The goal is to reduce unnecessary custom metric cost by downgrading alarms from
high-resolution (1-second period) to standard resolution (60-second period)
when sub-minute granularity provides no operational benefit.

Important distinction:

- **High-resolution custom metrics** use `period = 1` (or `resolution_seconds = 1`
  in scenario data) and cost **$0.90/metric/month**.
- **Standard resolution custom metrics** use `period = 60` and cost
  **$0.30/metric/month**.
- AWS built-in metrics (EC2, RDS, etc.) are always standard resolution and are
  not affected by this rule.
- Do not downgrade alarms where the use case genuinely requires sub-minute
  detection: payment fraud, real-time safety systems, sub-60s SLA breach alerts,
  or any alarm explicitly documented as requiring high-resolution.

Scenario data may use fictional attributes (`resolution_seconds`,
`actual_required_resolution_seconds`, `metric_type`, `evaluation_period_minutes`)
to represent resolution intent. Treat these as evidence only. The valid Terraform
AWS provider attribute for alarm period is `period` (seconds).

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` for all files before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_cloudwatch_metric_alarm` resources | Cannot analyze; ask user for path |
| `metrics.json` | Per-alarm metrics such as `metric_count`, alarm state history | Mark metrics evidence as unavailable |
| `cost_report.json` | Monthly CloudWatch cost history and pricing notes | Mark cost evidence as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/high_resolution_alarm.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| M1 | `resolution_seconds = 1` (or `period = 1`) AND `actual_required_resolution_seconds >= 60` | HIGH | DOWNGRADE_TO_STANDARD |
| M2 | `metric_type = "high_resolution"` with evaluation period >= 1 minute and no sub-minute SLA evidence | HIGH | DOWNGRADE_TO_STANDARD |
| M3 | Alarm count in high-resolution state is large and metric_count data shows no spikes requiring sub-minute detection | MEDIUM | REVIEW_HIGH_RESOLUTION |
| M4 | Scenario-only Terraform attributes present (`resolution_seconds`, `actual_required_resolution_seconds`, `metric_type`, `evaluation_period_minutes`) | MEDIUM | NORMALIZE_TERRAFORM |

### Resolution Downgrade Safety Check

Before recommending a downgrade, confirm:

- No documented sub-minute SLA or detection requirement.
- `evaluation_period_minutes >= 1` (alarms evaluating over 1+ minutes do not
  benefit from 1-second data points).
- Alarm namespace is a custom namespace (e.g. `Custom/Application`), not an
  AWS service namespace that already provides standard-resolution data.
- No evidence of anomaly detection or real-time dashboards depending on
  1-second granularity.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total `aws_cloudwatch_metric_alarm` count.
- Count of alarms using high-resolution (1s) vs standard (60s) period.
- Namespace for each group of alarms (custom vs AWS service).
- Evaluation period and whether it is >= 60 seconds.
- Evidence of `actual_required_resolution_seconds` or equivalent attribute
  indicating the true operational need.
- Scenario-only Terraform attributes that must be removed or normalized.

### 3.2 Metric Evidence

- `metric_count` pattern per alarm: flat, spiking, or silent.
- Whether metric values change faster than once per minute (would justify
  high-resolution).
- Alarm state change frequency and whether 1-second granularity changed
  alarm behaviour vs what 60-second would produce.

### 3.3 Cost Evidence

- Monthly CloudWatch spend trend.
- Pricing note from cost report (high-resolution vs standard per-metric price).
- Number of affected alarms and projected savings per alarm.
- Region-specific pricing when available. If only static prices exist, label
  them as estimates and note the AWS Pricing API for verification.

### 3.4 Root Cause

Explain the governance or architecture issue, such as:

- High-resolution was applied as a default template without evaluating whether
  sub-minute detection was needed.
- Evaluation periods were set to 5+ minutes, making 1-second resolution
  irrelevant — alarms average over the evaluation window regardless.
- No Terraform policy or module default enforced standard resolution for
  non-critical custom metrics.
- Cost impact of resolution choice was not visible at alarm creation time.

## Savings Calculation

Prefer this order of evidence:

1. Use pricing note from `cost_report.json` (price per metric per month and
   count of affected alarms).
2. Use region-specific pricing from AWS Pricing MCP/API.
3. Use static fallback prices from the rule file as estimates.

Formula:

```text
high_resolution_price_per_metric  = $0.90 / metric / month
standard_resolution_price_per_metric = $0.30 / metric / month
savings_per_metric = high_resolution_price_per_metric - standard_resolution_price_per_metric
monthly_savings = affected_alarm_count * savings_per_metric
```

Also include API cost savings estimate: high-resolution metrics require more
frequent `PutMetricData` API calls. If the cost report or pricing note includes
an API overhead figure, add it to the savings.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and all unchanged resources.
- Replace the high-resolution resolution signal with `period = 60` (the real
  Terraform AWS provider attribute for standard resolution).
- Remove all scenario-only attributes: `resolution_seconds`,
  `actual_required_resolution_seconds`, `metric_type`,
  `evaluation_period_minutes`. These are not valid Terraform AWS provider
  attributes for `aws_cloudwatch_metric_alarm`.
- Do not add placeholder values for attributes that were absent in the original
  scenario stub (`alarm_name`, `comparison_operator`, `metric_name`,
  `evaluation_periods`, `statistic`, `threshold`). These belong to the real
  alarm inventory, not the optimization. Note in the report that they must
  be supplied before `terraform apply`.
- Add a short inline comment on each changed alarm explaining the resolution
  downgrade and expected monthly saving.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps CloudWatch Metric Alarm Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | CloudWatch Metric Alarm unnecessary high-resolution (1s) period |
| Affected Resources | X of Y alarms |
| Monthly Waste | $XX estimated excess metric cost |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<alarm count, resolution settings, namespace, evaluation period, scenario attributes>

### Metrics
<metric_count pattern per alarm; evidence for or against sub-minute detection need>

### Cost Report
<monthly spend table, pricing note, affected alarm count, API overhead>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. Downgrade all affected alarms from `period = 1` to `period = 60`.
2. Remove scenario-only Terraform attributes and replace with valid AWS provider attributes.

### Preventive Actions
1. Enforce standard resolution (`period = 60`) as the default in Terraform modules for custom metric alarms.
2. Require explicit justification (tagged or documented) for any alarm using `period = 1` or `period = 10`.
3. Add AWS Config custom rule or OPA/Sentinel policy to flag high-resolution alarms without an approved exception.
4. Surface per-alarm metric cost in cost allocation tags so teams see the resolution cost impact.

## Estimated Monthly Savings
$XX.XX from resolution downgrade (X alarms × $0.60/alarm/month) plus ~$Y API call reduction.

## Optimized Terraform
<real resource-based optimized Terraform>
```

Generated by: finops-cloudwatch-alarm skill
