# finops-cloudwatch-alarm — Detailed Rules

## Resolution Pricing

- **High-resolution custom metric**: `period = 1` (or scenario `resolution_seconds = 1`)
  → **$0.90/metric/month**.
- **Standard resolution custom metric**: `period = 60` → **$0.30/metric/month**.
- AWS built-in metrics (EC2, RDS, etc.) are always standard resolution.

Do not downgrade alarms genuinely needing sub-minute detection: payment fraud,
real-time safety systems, sub-60s SLA alerts, or explicitly documented
high-resolution requirements.

Scenario-only attributes (`resolution_seconds`, `actual_required_resolution_seconds`,
`metric_type`, `evaluation_period_minutes`) are evidence — the valid Terraform
attribute for alarm period is `period` (seconds).

## Resolution Downgrade Safety Check

Before recommending a downgrade, confirm:
- No documented sub-minute SLA or detection requirement.
- `evaluation_period_minutes >= 1` (alarms over 1+ min don't benefit from 1-s points).
- Custom namespace (e.g. `Custom/Application`), not an AWS service namespace.
- No anomaly detection or real-time dashboards depend on 1-s granularity.

## Deep Architectural Analysis

### Infrastructure
- Total `aws_cloudwatch_metric_alarm` count.
- Count of alarms using high-resolution (1s) vs standard (60s) period.
- Namespace per alarm group (custom vs AWS service).
- Evaluation period and whether it is >= 60 seconds.
- Evidence of `actual_required_resolution_seconds` or equivalent.
- Scenario-only Terraform attributes to remove or normalize.

### Metrics
- `metric_count` pattern per alarm: flat, spiking, silent.
- Whether values change faster than once per minute (justifies high-res).
- Alarm state change frequency and 1-s vs 60-s behaviour comparison.

### Cost
- Monthly CloudWatch spend trend.
- Pricing note: high-resolution vs standard per-metric price.
- Affected alarm count and projected savings per alarm.
- Region pricing — label static prices as estimates.

### Root Cause (governance frame)
- High-resolution applied as default template without need evaluation.
- Evaluation periods set to 5+ minutes, making 1-s resolution irrelevant.
- No Terraform policy/module default enforcing standard resolution.
- Resolution cost not visible at alarm creation time.

## Savings Calculation

Evidence order: `cost_report.json` pricing_note → aws-pricing MCP → rule fallback.

```
high_resolution_price_per_metric     = $0.90 / metric / month
standard_resolution_price_per_metric = $0.30 / metric / month
savings_per_metric                   = $0.60 / metric / month
monthly_savings                      = affected_alarm_count * savings_per_metric
```

Also include API cost savings estimate: high-resolution requires more frequent
`PutMetricData` calls. If pricing_note includes an API overhead figure, add it.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Replace high-resolution signal with `period = 60` (valid AWS provider attribute).
- Remove scenario-only attributes: `resolution_seconds`,
  `actual_required_resolution_seconds`, `metric_type`, `evaluation_period_minutes`.
- Do not add placeholders for absent fields (`alarm_name`, `comparison_operator`,
  `metric_name`, `evaluation_periods`, `statistic`, `threshold`) — note in the
  report that they must be supplied before `terraform apply`.
- Short inline comment on each changed alarm explaining downgrade + monthly saving.

## Preventive Actions

1. Enforce `period = 60` as default in Terraform modules for custom-metric alarms.
2. Require explicit justification (tag/doc) for any alarm using `period = 1` or `10`.
3. AWS Config custom rule or OPA/Sentinel policy to flag high-resolution alarms
   without an approved exception.
4. Surface per-alarm metric cost in cost allocation tags.
