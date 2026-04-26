# FinOps Lambda Deep Analysis Report — L2-015

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Timeout Misconfiguration (M2) |
| Affected Resources | 2 of 3 `aws_lambda_function` (timeout=900s) |
| Monthly Waste | $360.00 |
| Annual Waste | $4,320.00 |
| Waste Percentage | ~80% of avg Lambda spend ($453/mo) |

---

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)

3 `aws_lambda_function` resources. 2 functions are configured with `timeout=900` (the Lambda maximum). 1 function runs with `timeout=30` — serving as a healthy low-timeout baseline.

| Function | memory_size (MB) | timeout (s) | Runtime | M2? |
|---|---|---|---|---|
| lambda-function-zspoqd | 1024 | **900** | nodejs18.x | ✅ Yes |
| lambda-function-mfra1j | 1024 | **900** | nodejs18.x | ✅ Yes |
| lambda-function-6apyi7 | 1024 | 30 | nodejs18.x | — baseline |

Setting `timeout=900` is the Lambda maximum and a common "set it and forget it" safety practice. The real cost emerges only on error paths: when a function errors or times out, Lambda charges for the **full timeout duration** in GB-seconds.

### 3.2 Evidence from Metrics (CloudWatch — 30 days)

Rule M1: `memory_used_mb` absent → M1 not applicable.
Rule M2: `duration_ms` + `error_rate_pct` present, `timeout=900s ≥ 300s` threshold → M2 applies.

**Duration / timeout analysis:**

| Function | Timeout (s) | Avg Duration (ms) | p99 Duration (ms) | Timeout/p99 Ratio | Issue |
|---|---|---|---|---|---|
| lambda-function-zspoqd | 900 | 2,016.4 | 5,897.4 | **152.6×** | ✅ M2 |
| lambda-function-mfra1j | 900 | 2,013.9 | 5,349.8 | **168.2×** | ✅ M2 |
| lambda-function-6apyi7 | 30 | 100.0 | 100.0 | 300× | — baseline |

**Error rate (confirms pricing_note assumptions):**

| Function | Avg Error Rate | Error invocations/day (×50k) | Cost per error at 900s / 1024MB |
|---|---|---|---|
| lambda-function-zspoqd | **2.1%** | ~1,050 | 900 GB-sec × $0.0000167 = **$0.015** |
| lambda-function-mfra1j | **1.9%** | ~950 | 900 GB-sec × $0.0000167 = **$0.015** |
| lambda-function-6apyi7 | 0.1% | ~50 | 30 × 1 GB-sec × negligible | 

The p99 at ~5.9s confirms that 99% of successful invocations complete within 6s. The configured 900s timeout provides 150× more runway than needed — all of it billed on every error.

**Recommended timeout:**
- Formula: `ceil(5897.4 / 1000) × 3 = 18s`
- `pricing_note` target: **10s** (authoritative) → used as final recommendation

### 3.3 Evidence from Cost Report (6 months)

| Month | Lambda Spend | Total Spend | Lambda % |
|---|---|---|---|
| M-5 | $401.78 | $3,588.58 | 11.2% |
| M-4 | $489.20 | $3,793.48 | 12.9% |
| M-3 | $475.27 | $3,504.75 | 13.6% |
| M-2 | $449.10 | $3,487.89 | 12.9% |
| M-1 | $535.65 | $4,040.91 | 13.3% |
| M-0 | $366.55 | $3,488.17 | 10.5% |
| **Avg** | **$452.93** | **$3,650.63** | **12.4%** |

`pricing_note`: *"에러 시 900초 × 1024MB = 900 GB-초/호출. 하루 50000 × 2% = 1000 에러 호출 × 900 GB-초. 타임아웃을 10초로 줄이면 에러 비용 99% 절감. 함수당 약 $180/mo (2 함수 합계 $360/mo)."*

Estimated waste ($360/mo) represents **~80% of avg Lambda spend** ($453/mo) — the majority of Lambda cost in this account is burned on error-path timeout duration.

### 3.4 Root Cause

Both flagged functions were given `timeout=900` (Lambda maximum) as a precautionary default during deployment. This is a common practice intended to prevent silent failures — but it creates a hidden cost multiplier. Every error invocation is charged for up to 900 GB-seconds instead of ~6 GB-seconds (p99 × 1024MB). With 2% error rates and 50,000 daily invocations:

- **Per function per day**: 1,000 error calls × (900 − 10) seconds × 1 GB = **890,000 GB-sec wasted**
- **Per function per month**: 890,000 × 30 × $0.0000166667 ≈ **$445/mo** in error-path duration waste

The `lambda-function-6apyi7` with `timeout=30` and 0.1% errors demonstrates the correct pattern: a tightly bounded timeout eliminates runaway error costs entirely.

---

## Proposed Solution

### Immediate Actions (Week 1)
1. Apply `main_optimized.tf` — sets `timeout = 10` for both flagged functions.
2. Deploy to one function first; monitor `Errors`, `Throttles`, and `Duration` for 1 hour.
3. Confirm that no legitimate invocations approach 10s before applying to the second function.
   - p99 = 5.9s → 10s gives 4.1s buffer; review any outliers above p99 in the metrics.
4. `terraform plan -out=timeout_fix.plan` → review → `terraform apply timeout_fix.plan`.

### Preventive Actions (Week 2–4)
1. **Timeout policy**: Establish `timeout ≤ ceil(p99 × 3)` as a code-review requirement for all Lambda functions. Document in the team runbook.
2. **CloudWatch Alarm**: `Duration p99 > timeout × 0.8` → PagerDuty alert. Catches latency drift before it triggers timeouts.
3. **Terraform module**: Set `timeout = 30` as default in the shared Lambda module; require explicit justification comment for `timeout > 60`.
4. **AWS Compute Optimizer**: Enable for Lambda — surfaces timeout recommendations alongside memory recommendations.

---

## Estimated Monthly Savings (USD)

| Function | Current Timeout (s) | Recommended Timeout (s) | Error Rate | Monthly Savings |
|---|---|---|---|---|
| lambda-function-zspoqd | 900 | 10 | 2.1% | $180.00 |
| lambda-function-mfra1j | 900 | 10 | 1.9% | $180.00 |
| **Total** | | | | **$360.00/mo** |

**Annual savings: $4,320.00**

---

## Optimized Terraform

See `main_optimized.tf` for the complete modified configuration.

```bash
# Safety verification before applying:
# 1. terraform plan -out=timeout_fix.plan
# 2. Confirm only 'timeout' attribute changes in plan output
# 3. terraform apply timeout_fix.plan
# 4. Monitor Lambda Duration p99 and Errors for 1 hour post-apply
#    Rollback: terraform apply -var timeout=900 if p99 approaches 10s
```

---

*Generated by: finops-lambda skill — Claude Code*
