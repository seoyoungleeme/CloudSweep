# FinOps Lambda Analysis Report - L2-014

## Problem Identification

| Category | Details |
|----------|---------|
| Waste Type | Lambda memory over-allocation — 3008 MB provisioned, ~100 MB used (3.3% utilization) |
| Affected Resources | 3 of 5 functions (primary); 2 of 5 (secondary) |
| Provisioned Memory | 3008 MB × 3 functions |
| Actual Max Memory | ~100 MB across all 3 affected functions |
| Monthly Waste | **~$750** |
| Annual Waste | **~$9,000** |
| Confidence | **High** — 30-day memory and duration metrics confirm chronic under-utilization; zero errors/throttles; cost_report provides authoritative savings estimate |

---

## Evidence

### 3.1 Infrastructure Evidence (Terraform)

`main.tf` declares **5 `aws_lambda_function`** resources in `us-east-1`, all using `runtime = "python3.11"` and `timeout = 30`.

| Function | Memory | Timeout | Architecture | Provisioned Concurrency | Status |
|----------|--------|---------|-------------|------------------------|--------|
| `lambda-function-192d7g` | **3008 MB** | 30s | x86_64 | None | **Affected** |
| `lambda-function-ctcl0s` | **3008 MB** | 30s | x86_64 | None | **Affected** |
| `lambda-function-jfafoa` | **3008 MB** | 30s | x86_64 | None | **Affected** |
| `lambda-function-7fw8rk` | 512 MB | 30s | x86_64 | None | Secondary |
| `lambda-function-q49wt1` | 512 MB | 30s | x86_64 | None | Secondary |

All three affected functions are identical: 3008 MB (near the top of the Lambda range) with a 30-second timeout. No provisioned concurrency, no ephemeral storage above the 512 MB free baseline — compute GB-seconds is the sole waste driver.

3008 MB assigns approximately 2.9 vCPU to each function. This is typically chosen to maximize CPU for compute-intensive work, but the 100ms flat duration and 100 MB memory usage show the workload is neither CPU-bound nor memory-intensive.

### 3.2 Metric Evidence (30 days)

**Affected functions — all three show the same pattern**

| Metric | Avg | p95 | Max | Provisioned | Utilization |
|--------|-----|-----|-----|-------------|-------------|
| `memory_used_mb` | 100 MB | 100 MB | 100 MB | 3008 MB | **3.3%** |
| `duration_ms` | 100 ms | 100 ms | 100 ms | — | — |
| Errors | 0 | — | 0 | — | — |
| Throttles | 0 | — | 0 | — | — |

**Secondary functions (512 MB)**

| Function | Memory Used | Utilization | Duration avg |
|----------|------------|-------------|-------------|
| `lambda-function-7fw8rk` | 100 MB | **19.5%** | 100 ms |
| `lambda-function-q49wt1` | 100 MB | **19.5%** | 100 ms |

**Safety check (per rule L1 requirements):**
- Max memory used 100 MB — well below the 75% safety block at 3008 MB (would need 2256 MB to trigger block)
- Duration flat at 100ms max — workload is not CPU-bound; reducing memory will not meaningfully increase duration
- Zero errors and zero throttles over the full 30-day window — no reliability risk
- No event source mappings or retry behavior in Terraform — no backlog/retry cost concern

### 3.3 Cost Evidence (6 months)

| Month | Lambda Spend | Total AWS Spend |
|-------|-------------|-----------------|
| M-5 | $739.92 | $11,493.42 |
| M-4 | $766.49 | $10,543.94 |
| M-3 | $947.19 | $10,166.22 |
| M-2 | $877.28 | $11,268.00 |
| M-1 | $893.73 | $11,123.46 |
| M-0 | $851.99 | $10,671.84 |
| **Avg** | **$846.10** | **$10,877.81** |

**Cost decomposition (authoritative, from pricing_note):**

| Item | Current | After right-sizing |
|------|---------|--------------------|
| 3 × 3008 MB functions (compute GB-seconds) | ~$750/mo | ~$0 (reduced) |
| 2 × 512 MB functions | ~$96/mo | ~$96/mo |
| **Total Lambda** | **~$846/mo** | **~$96/mo** |
| **Monthly savings** | | **~$750/mo** |

Lambda bills `invocations × duration_s × memory_GB × $0.0000166667`. At 3008 MB vs 512 MB (5.875× memory reduction), with duration unchanged, compute cost drops by ~83%. The pricing_note confirms $250/mo savings per function × 3 = $750/mo total.

### 3.4 Root Cause

**3008 MB was set to maximize CPU allocation for a workload that is I/O-bound and completes in 100ms regardless of CPU tier.**

Lambda assigns CPU proportionally to memory: at 3008 MB, functions receive ~2.9 vCPU; at 512 MB, ~0.5 vCPU. This high-memory pattern is correct for CPU-intensive workloads (ML inference, image processing, data transformation) where more CPU directly reduces duration and can lower total cost. For lightweight workloads that complete in 100ms flat, the extra CPU allocation is idle the entire invocation — billed, but unused.

The three affected functions (`192d7g`, `ctcl0s`, `jfafoa`) show no correlation between memory and duration: identical 100ms completion at 3008 MB, meaning they're not benefiting from the CPU premium. The two correctly-sized functions (`7fw8rk`, `q49wt1`) already run at 512 MB, suggesting a later, more careful provisioning decision was made for those functions while the original three were never revisited.

---

## Proposed Solution

### Immediate Actions

1. **Reduce `memory_size` from 3008 MB to 512 MB** on `192d7g`, `ctcl0s`, and `jfafoa`. Apply `main_optimized.tf`.

2. **Monitor for 7 days post-deployment:**
   ```bash
   # Duration regression check — should remain ~100ms
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Lambda --metric-name Duration \
     --dimensions Name=FunctionName,Value=lambda-function-192d7g \
     --start-time $(date -d '7 days ago' --iso-8601=seconds) \
     --end-time $(date --iso-8601=seconds) \
     --period 3600 --statistics Average,Maximum

   # Errors check
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Lambda --metric-name Errors \
     --dimensions Name=FunctionName,Value=lambda-function-192d7g \
     --start-time $(date -d '7 days ago' --iso-8601=seconds) \
     --end-time $(date --iso-8601=seconds) \
     --period 86400 --statistics Sum
   ```
   Roll back to the previous function version if duration increases > 20% or errors appear.

3. **Secondary: run Lambda Power Tuning on `7fw8rk` and `q49wt1`** before reducing to 256 MB. At 19.5% memory utilization both are below the threshold, but the duration impact at 256 MB should be confirmed with the Power Tuning tool before applying (~$48/mo additional savings if confirmed).

### Preventive Actions

1. **Alert on low memory utilization** — set a CloudWatch alarm triggering when `MaxMemoryUsed / MemorySize < 15%` for 7 consecutive days on any function.

2. **Require Lambda Power Tuning for functions > 512 MB** — make power tuning a standard step in the deployment process for any new function provisioned above 512 MB. The [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning) tool automates the cost-vs-latency sweep.

3. **Set a memory ceiling policy** — require justification (benchmark results or explicit latency SLA) for any `memory_size > 1024 MB` at infrastructure review time. Default starting memory should be 256–512 MB.

4. **Model arm64** — all five functions use x86_64. Switching to `arm64` on Python 3.11 workloads typically reduces GB-second cost by ~20% with no code changes. Validate first on a non-production function.

---

## Estimated Monthly Savings

**~$750 / month**
**~$9,000 / year**

| Function | Before | After | Monthly Savings |
|----------|--------|-------|-----------------|
| `lambda-function-192d7g` | 3008 MB | 512 MB | **~$250** |
| `lambda-function-ctcl0s` | 3008 MB | 512 MB | **~$250** |
| `lambda-function-jfafoa` | 3008 MB | 512 MB | **~$250** |
| `lambda-function-7fw8rk` | 512 MB | 256 MB *(secondary)* | ~$24 est. |
| `lambda-function-q49wt1` | 512 MB | 256 MB *(secondary)* | ~$24 est. |
| **Primary total** | | | **~$750/mo** |
| Secondary (after Power Tuning) | | | ~$48/mo est. |

> **Confidence: High.** Memory max never exceeded 100 MB in 30 days at 3008 MB. Zero errors, zero throttles. Duration flat at 100ms — no CPU-bound behavior. Savings of $750/mo are authoritative from `cost_report.json` pricing_note. Secondary savings (~$48/mo) are list-price estimates only.

---

*Generated by: finops-lambda skill v1.1.0 — Claude Code | Scenario: L2-014 (MedCloud)*
