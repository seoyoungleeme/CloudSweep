# FinOps Lambda Deep Analysis Report — L2-014

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Memory Overprovisioning (M1) |
| Affected Resources | 3 of 5 `aws_lambda_function` (3008 MB tier) |
| Monthly Waste | $750.00 |
| Annual Waste | $9,000.00 |
| Waste Percentage | ~89% of avg Lambda spend ($846/mo) |

---

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)

5 `aws_lambda_function` resources detected. 3 functions are provisioned at 3008 MB; 2 functions already run at 512 MB — the same runtime/handler configuration.

| Function | memory_size (MB) | timeout (s) | Runtime | Env |
|---|---|---|---|---|
| lambda-function-192d7g | **3008** | 30 | python3.11 | production |
| lambda-function-ctcl0s | **3008** | 30 | python3.11 | production |
| lambda-function-jfafoa | **3008** | 30 | python3.11 | production |
| lambda-function-7fw8rk | 512 | 30 | python3.11 | production |
| lambda-function-q49wt1 | 512 | 30 | python3.11 | production |

The 512 MB functions (`7fw8rk`, `q49wt1`) serve as a direct comparison baseline: identical runtime, identical workload profile, same environment — yet provisioned at 6× less memory with no functional difference apparent from available data.

### 3.2 Evidence from Metrics (CloudWatch — 30 days)

Rule M1 (`memory_used_mb` present). Rule M2 (`duration_ms` present, but `timeout=30s` < 300s threshold — M2 does not fire).

| Function | Provisioned (MB) | Avg Used (MB) | Max Used (MB) | Utilization % | Issue |
|---|---|---|---|---|---|
| lambda-function-192d7g | 3008 | 99.91 | 100.0 | **3.3%** | ✅ M1 |
| lambda-function-ctcl0s | 3008 | 99.99 | 100.0 | **3.3%** | ✅ M1 |
| lambda-function-jfafoa | 3008 | 99.89 | 100.0 | **3.3%** | ✅ M1 |
| lambda-function-7fw8rk | 512 | 100.00 | 100.0 | 19.5% | — (baseline) |
| lambda-function-q49wt1 | 512 | 100.00 | 100.0 | 19.5% | — (baseline) |

**Key finding:** All three 3008 MB functions consumed ≤ 100 MB across all 720 hourly datapoints (30-day window). Peak usage never exceeded 100 MB. Headroom-based target: `100 × 1.5 = 150 MB` → next valid tier = 256 MB. The `cost_report.json` pricing_note explicitly specifies `3008MB → 512MB` as the target tier, which is used as the authoritative recommended value.

### 3.3 Evidence from Cost Report (6 months)

| Month | Lambda Spend | Total Spend | Lambda % |
|---|---|---|---|
| M-5 | $739.92 | $11,493.42 | 6.4% |
| M-4 | $766.49 | $10,543.94 | 7.3% |
| M-3 | $947.19 | $10,166.22 | 9.3% |
| M-2 | $877.28 | $11,268.00 | 7.8% |
| M-1 | $893.73 | $11,123.46 | 8.0% |
| M-0 | $851.99 | $10,671.84 | 8.0% |
| **Avg** | **$846.10** | **$10,877.81** | **7.8%** |

`pricing_note`: *"Lambda 비용 = 요청 수 + (Duration x 할당 메모리 GB-초). 3008MB → 512MB로 줄이면 함수당 약 $250/mo 절감 (3 함수 합계 $750/mo)."*

At $750/mo waste against $846/mo avg Lambda spend, **~89% of all Lambda spend on these 3 functions is attributable to over-allocated memory**.

### 3.4 Root Cause

The three flagged functions were provisioned at 3008 MB — likely set during initial onboarding under a "provision generously to avoid cold-start memory pressure" policy — and never revisited. The actual workload is light: ≤ 100 MB peak in 30 days. The two 512 MB sibling functions demonstrate that the same Python 3.11/production workload runs correctly at 512 MB. The 3008 MB allocation provides no performance benefit; it inflates every GB-second billing unit by 5.875×.

---

## Proposed Solution

### Immediate Actions (Week 1)
1. Apply `main_optimized.tf` — sets `memory_size = 512` for the three flagged functions.
2. Deploy incrementally: reduce one function first, monitor `Duration` and `Errors` for one hour, then apply to remaining two.
3. Run `terraform plan -out=memory_fix.plan` and review before applying.

### Preventive Actions (Week 2–4)
1. **AWS Compute Optimizer** — enable for Lambda; it auto-recommends optimal memory based on invocation history.
2. **Lambda Power Tuning** (AWS open-source tool) — run against all Lambda functions on a monthly cadence to find cost/performance optimal tier.
3. **CloudWatch Alarm** — `Max(MemorySize) / Max(MemoryUsed) > 5` triggers a review notification.
4. **Terraform module default** — set `memory_size = 512` as the default in the shared Lambda module; require explicit override for larger tiers with a justification comment.

---

## Estimated Monthly Savings (USD)

| Function | Current (MB) | Recommended (MB) | Monthly Savings |
|---|---|---|---|
| lambda-function-192d7g | 3008 | 512 | $250.00 |
| lambda-function-ctcl0s | 3008 | 512 | $250.00 |
| lambda-function-jfafoa | 3008 | 512 | $250.00 |
| **Total** | | | **$750.00/mo** |

**Annual savings: $9,000.00**

---

## Optimized Terraform

```bash
# Safety verification before applying:
# 1. terraform plan -out=memory_fix.plan
# 2. Review plan output — confirm only memory_size changes
# 3. terraform apply memory_fix.plan
# 4. Monitor Lambda Duration/Errors metrics for 1 hour post-apply
```

See `main_optimized.tf` for the complete modified configuration.

---

*Generated by: finops-lambda skill — Claude Code*
