# finops-cloudwatch — Detailed Rules

## Terraform Attribute Distinction

- Valid Terraform AWS provider attribute: `retention_in_days`.
- Scenarios may use `retention_days` as input — treat as evidence only;
  convert optimized Terraform to `retention_in_days`.
- Missing `retention_in_days` or `retention_in_days = 0` = retained indefinitely.

Do not recommend deletion or retention reduction from cost evidence alone when
the log group may contain audit, security, incident response, regulated, or
business-critical logs. Flag those for owner validation.

## Retention Baselines (defaults, not absolute rules)

| Environment / Data Class | Default Recommendation | Notes |
|--------------------------|------------------------|-------|
| dev / test / sandbox | 14-30 days | Prefer 30 when owner unknown |
| staging / preprod | 30-90 days | Prefer 90 when release debugging unclear |
| prod application logs | 90-365 days | Choose by incident/support needs |
| audit / security / compliance | Org policy first | Long-term retention should move to S3, Glacier, SIEM |
| unknown / untagged | 90 days provisional | Require owner validation before aggressive reduction |

If environment is inferred from names/tags, state the inference and confidence.
If no evidence exists, use `unknown` and default to 90 days.

## Deep Architectural Analysis

### Infrastructure
- Total `aws_cloudwatch_log_group` count.
- Retention state per group: missing, zero/infinite, excessive, compliant, unknown.
- Invalid Terraform attributes (e.g. `retention_days`) to normalize.
- Environment/data-class inference from names, tags, resource relationships.

### Metrics
- Prefer `StoredBytes` for current stored volume.
- Use `IncomingBytes` or `log_bytes_ingested` to estimate steady-state storage.
- Distinguish active vs silent log groups.
- Zero-ingestion = deletion review candidate only — require no-recent-events
  evidence, owner confirmation, retired upstream service before recommending deletion.

### Cost
- Monthly CloudWatch spend trend.
- Storage cost from `pricing_note`, CUR-like line items, or metrics.
- Region-specific pricing — label static rule price as estimate.
- Separate ingestion savings from storage savings. Retention changes reduce
  stored log volume; they do not reduce ongoing ingestion cost.

### Root Cause (governance frame)
- Log groups created without required retention standard.
- Modules/service teams create logs with implicit infinite retention.
- Environment classification missing → inconsistent retention.
- Compliance archive kept in CloudWatch Logs instead of cheaper long-term path.

## Savings Calculation

Evidence order: cost report storage line items / pricing_note → StoredBytes →
estimate from per-group daily ingestion × target retention days.

```
current_storage_gb  = observed stored GB from cost report or StoredBytes
target_storage_gb   = sum(daily_ingestion_gb_per_group * target_retention_days)
storage_savings_usd = max(current_storage_gb - target_storage_gb, 0) * storage_price_per_gb_month
monthly_savings_usd = storage_savings_usd
```

Never count ingestion cost as retention-policy savings unless remediation also
reduces log volume, sampling, or verbosity.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Use `retention_in_days` (valid Terraform attribute).
- Convert scenario-only `retention_days` → `retention_in_days`.
- Remove simulation-only attributes not valid in Terraform (e.g. `daily_ingestion_gb`).
- Set missing/infinite retention to recommended value for inferred environment;
  90 days for unknown.
- Do not reduce audit/security/compliance retention without explicit evidence
  that the target satisfies policy.
- Short inline comments only for cost-control or policy changes.

## Preventive Actions

1. Enforce `retention_in_days` in Terraform policy checks.
2. Enable AWS Config rule `cloudwatch-log-group-retention-period-check`.
3. EventBridge/Lambda remediation or module defaults for implicitly created log groups.
4. Export long-term audit/security logs to S3, Glacier, or SIEM where appropriate.
