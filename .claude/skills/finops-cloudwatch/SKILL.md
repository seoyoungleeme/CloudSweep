---
name: finops-cloudwatch
description: >
  FinOps CloudWatch Analysis Skill. Detects AWS CloudWatch Logs storage waste
  caused by missing, infinite, or excessive log retention policies on
  aws_cloudwatch_log_group resources. Use for Terraform configurations,
  CloudWatch metrics, and AWS cost reports that include CloudWatch Logs data.
  Keywords: "CloudWatch cost", "log group", "retention policy",
  "log storage waste", "retention_in_days".
user_invocable: false
---

# FinOps CloudWatch Log Group Analysis Skill

## Scope

Analyze CloudWatch Logs retention from a FinOps perspective. The goal is to
reduce unnecessary CloudWatch Logs storage cost while preserving operational,
security, audit, and compliance requirements.

Important Terraform distinction:

- The valid Terraform AWS provider attribute is `retention_in_days`.
- Some training scenarios may use `retention_days` as input data. Treat it as
  scenario evidence only, and convert optimized Terraform to `retention_in_days`.
- Missing `retention_in_days` or `retention_in_days = 0` means logs are retained
  indefinitely unless another external process changes retention.

Do not recommend deletion or retention reduction solely from cost evidence when
the log group may contain audit, security, incident response, regulated, or
business-critical logs. Flag those cases for owner validation.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` for all files before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_cloudwatch_log_group` resources | Cannot analyze; ask user for path |
| `metrics.json` | CloudWatch metrics such as `log_bytes_ingested`, `IncomingBytes`, or `StoredBytes` per log group | Mark metrics evidence as unavailable |
| `cost_report.json` | Monthly CloudWatch cost history and any pricing notes | Mark cost evidence as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/missing_retention_policy.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| C1 | `retention_in_days` missing or `retention_in_days == 0` | HIGH | SET_RETENTION |
| C2 | `retention_in_days > environment_max` and no documented exception | MEDIUM | REDUCE_RETENTION |
| C3 | No ingestion and no recent events for the full observation window | LOW | REVIEW_DELETE_CANDIDATE |
| C4 | Log group uses invalid or scenario-only Terraform retention attributes | MEDIUM | NORMALIZE_TERRAFORM |

### Retention Baselines

Use these as default baselines, not absolute compliance rules:

| Environment / Data Class | Default Recommendation | Notes |
|--------------------------|------------------------|-------|
| dev / test / sandbox | 14-30 days | Prefer 30 days when owner is unknown |
| staging / preprod | 30-90 days | Prefer 90 days when release debugging needs are unclear |
| prod application logs | 90-365 days | Choose based on incident response and support needs |
| audit / security / compliance | Organization policy first | Long-term retention should usually move to S3, Glacier, SIEM, or security tooling |
| unknown / untagged | 90 days provisional | Require owner validation before aggressive reduction |

When environment is inferred from names or tags, state the inference and its
confidence. If no environment evidence exists, use `unknown` and default to
90 days for the optimized Terraform.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total `aws_cloudwatch_log_group` count.
- Retention state per log group: missing, zero/infinite, excessive, compliant,
  or unknown.
- Any invalid Terraform attributes, such as `retention_days`, that should be
  normalized to `retention_in_days` in optimized output.
- Environment or data-class evidence from names, tags, resource relationships,
  or provided metadata.

### 3.2 Metric Evidence

- Prefer `StoredBytes` for current stored volume when available.
- Use ingestion metrics such as `IncomingBytes` or `log_bytes_ingested` to
  estimate future steady-state storage.
- Distinguish active log groups from silent log groups.
- Treat zero-ingestion findings as deletion review candidates only. Require
  evidence of no recent events, owner confirmation, and retired upstream
  service before recommending deletion.

### 3.3 Cost Evidence

- Monthly CloudWatch spend trend.
- Storage cost evidence from `pricing_note`, Cost and Usage Report line items,
  or metrics.
- Region-specific pricing when available. If only a static rule price exists,
  say it is an estimate and verify against AWS Pricing for the target region.
- Separate ingestion savings from storage savings. Retention changes reduce
  stored log volume; they do not reduce ongoing ingestion cost.

### 3.4 Root Cause

Explain the governance or architecture issue, such as:

- Log groups were created without a required retention standard.
- Terraform modules or service teams create logs implicitly with infinite
  retention.
- Environment/data classification is missing, making retention choices
  inconsistent.
- Compliance archival is being kept in CloudWatch Logs instead of a cheaper
  long-term archive path.

## Savings Calculation

Prefer this order of evidence:

1. Use provided cost report storage line items or pricing note.
2. Use `StoredBytes` per log group when available.
3. Estimate steady-state storage from per-group daily ingestion and target
   retention days.

Formula:

```text
current_storage_gb = observed stored GB from cost report or StoredBytes
target_storage_gb = sum(daily_ingestion_gb_per_group * target_retention_days)
storage_savings_usd = max(current_storage_gb - target_storage_gb, 0) * storage_price_per_gb_month
monthly_savings_usd = storage_savings_usd
```

Never count ingestion cost as savings from retention policy changes unless the
proposed remediation also reduces log volume, sampling, or verbosity.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Use the valid Terraform attribute `retention_in_days`.
- Convert scenario-only `retention_days` to `retention_in_days`.
- Remove simulation-only attributes not valid in Terraform, such as
  `daily_ingestion_gb`.
- Set missing or infinite retention to the recommended value for the inferred
  environment. Use 90 days for unknown environments.
- Do not reduce audit/security/compliance log retention without explicit
  evidence that the target retention satisfies policy.
- Add short inline comments only where they explain cost-control or policy
  changes.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps CloudWatch Log Group Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | CloudWatch Logs missing or excessive retention policy |
| Affected Resources | X of Y log groups |
| Monthly Waste | $XX estimated storage waste |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<retention settings, environment/data-class inference, invalid Terraform attributes>

### Metrics
<stored bytes and ingestion table; active vs silent groups>

### Cost Report
<monthly spend table, pricing note, region/pricing assumptions>

## Root Cause
<architecture or governance cause>

## Proposed Solution

### Immediate Actions
1. ...

### Preventive Actions
1. Enforce `retention_in_days` in Terraform policy checks.
2. Enable AWS Config rule `cloudwatch-log-group-retention-period-check`.
3. Add EventBridge/Lambda remediation or module defaults for implicitly created log groups.
4. Export long-term audit/security logs to S3, Glacier, or SIEM where appropriate.

## Estimated Monthly Savings
$XX.XX from storage reduction only; ingestion cost unchanged unless separately optimized.

## Optimized Terraform
<real resource-based optimized Terraform>
```

Generated by: finops-cloudwatch skill
