# FinOps Cost Anomaly Report

**Scenario**: LV-001
**Analysis date**: 2026-06-01
**Data range**: 2026-05-26T00:00:00Z - 2026-05-27T06:00:00Z

---

## 1. Spike Window

| Metric | Value |
|--------|-------|
| Spike start | 2026-05-27T01:00:00Z |
| Baseline window | 3 prior datapoints |
| Baseline mean | $12.41/hr |
| Baseline stddev | $0.46/hr |
| Previous datapoint cost | $13.01/hr |
| Spike cost | $58.74/hr |
| Absolute delta vs baseline | +$46.33/hr |
| Pct change vs previous | +351.5% |
| Flags fired | statistical (cost $58.74 > mean+2s $13.33); pct-change (+351.5% > 100%) |
| Affected account(s) | 123456789012 |

> Sparse data note: this mock has only a few sampled hourly points, so the statistical baseline is directional. The anomaly API is used as confirmation.

---

## 2. Impact (from GetAnomalies)

| Service | AnomalyScore | TotalImpact | TotalActualSpend | TotalExpectedSpend |
|---------|--------------|-------------|------------------|--------------------|
| Amazon Elastic Compute Cloud | 0.88 | $312.45 | $478.20 | $165.75 |
| Amazon Simple Storage Service | 0.65 | $78.60 | $128.40 | $49.80 |

**Total anomaly impact: $391.05**

---

## 3. Drilldown by Service

**Spike at 2026-05-27T01:00:00Z**

| Rank | Service | Baseline Avg/hr | Spike Cost/hr | Delta | Delta Share | UsageType |
|------|---------|-----------------|---------------|-------|-------------|-----------|
| 1 | Amazon Elastic Compute Cloud | $8.60 | $45.30 | +$36.70 | 79.2% | APN2-BoxUsage:c5.4xlarge |
| 2 | Amazon S3 | $2.07 | $9.80 | +$7.73 | 16.7% | APN2-Requests-Tier1 |
| 3 | Amazon RDS | $1.75 | $3.64 | +$1.89 | 4.1% | Not in GetAnomalies - Suspected |

---

## 4. Anomaly API Confirmation

**Amazon Elastic Compute Cloud**
- Region: ap-northeast-2 | LinkedAccount: 123456789012 | UsageType: `APN2-BoxUsage:c5.4xlarge`

**Amazon Simple Storage Service**
- Region: ap-northeast-2 | LinkedAccount: 123456789012 | UsageType: `APN2-Requests-Tier1`

---

## 5. CloudTrail Correlation

CloudTrail mock not provided - instrumentation gap. Cannot confirm triggering event.

Recommended collection window: spike start minus 60 minutes through spike start.
Recommended EC2-related eventSources: `ec2.amazonaws.com`, `autoscaling.amazonaws.com`, `ecs.amazonaws.com`, `cloudformation.amazonaws.com`.

---

## 6. Likely Root Cause

Primary driver: Amazon Elastic Compute Cloud increased from $8.60/hr to $45.30/hr, contributing 79.2% of the total delta. UsageType attribution: `APN2-BoxUsage:c5.4xlarge`.
Secondary driver: Amazon S3 increased from $2.07/hr to $9.80/hr (16.7% of delta), UsageType `APN2-Requests-Tier1`.
Triggering event confidence remains low until CloudTrail events in the pre-spike window are available.

---

## 7. Remediation

- [ ] Elastic Compute Cloud: inspect instance launches, Auto Scaling changes, ECS service updates, and CloudFormation stack updates in the pre-spike window. If unintentional, revert capacity changes or terminate surplus instances — Est. prevention: $312.45 if root cause confirmed.
- [ ] Elastic Compute Cloud: if the new compute level is legitimate and recurring, evaluate Savings Plans or rightsizing after confirming sustained utilization.
- [ ] Simple Storage Service: reduce Tier-1 request volume by removing redundant PUT/LIST loops, batching writes, caching manifests/indexes, and adding request metrics by bucket or prefix — Est. prevention: $78.60 if root cause confirmed.
- [ ] Relational Database Service: review connection counts and query patterns during the spike window; consider read replicas or connection pooling if load was legitimate.
- [ ] Instrumentation: keep CloudTrail management events and enable service-specific metrics needed to tie spend spikes to deploy or scaling events.

---

## 8. Confidence

| Layer | Confidence | Reason |
|-------|------------|--------|
| Spike detection | High | Statistical and pct-change flags fired |
| Service attribution | Medium | Elastic Compute Cloud, S3 confirmed; others suspected (not in GetAnomalies) |
| Triggering event | Low | CloudTrail events not available in pre-spike window |
| Baseline reliability | Medium | Sparse window (3 prior datapoints) |

---

## 9. Deliverables Status

| Deliverable | Status |
|-------------|--------|
| `result/finops_report.md` | Generated for `/finops` convention |
| `result/solution.py` | Generated as scenario code artifact |
| `result/main_optimized.tf` | Generated placeholder; no Terraform changes for anomaly mode |
