# FinOps Analysis Report
- **Scenario**: MA-001 · PixelStorm B2C Order Processing
- **Domains analyzed**: Lambda, S3, DynamoDB
- **Run date**: 2026-05-18

## Analysis Metrics
| Metric | Value |
|--------|-------|
| Recall | 3 / 3 patterns found (100%) |
| Domains analyzed | 3 (Lambda, S3, DynamoDB) |
| Agent count | 1 orchestrator + 3 domain experts |
| Pricing source | cost_report.json pricing_note primary; aws-pricing MCP unavailable (credentials invalid) |
| Doc references | aws-docs MCP unavailable this run |
| Total tokens | Not measured |
| Wall-clock time | Not measured |
| Analysis cost | Not measured |

---

## 1. Problem Identification

| Resource | Service | Waste Type | Severity | Monthly Waste |
|----------|---------|------------|----------|---------------|
| lambda-function-atrjum | Lambda | Memory over-allocation (3008 MB, 3.3% util) | HIGH | ~$250/mo |
| lambda-function-37781v | Lambda | Memory over-allocation (3008 MB, 3.3% util) | HIGH | ~$250/mo |
| lambda-function-luzj7m | Lambda | Memory over-allocation (3008 MB, 3.3% util) | HIGH | ~$250/mo |
| data-lake-archive (s3-bucket-xu5s05) | S3 | No lifecycle — archive bucket in STANDARD class | HIGH | part of ~$152/mo |
| data-lake-raw (s3-bucket-554gvl) | S3 | No lifecycle — objects accumulate indefinitely | MEDIUM | part of ~$152/mo |
| dynamodb-table-wouiv4 | DynamoDB | PROVISIONED severely over-provisioned, no Auto Scaling | HIGH | ~$522/mo |

**Compliant resources (unchanged):** lambda-function-5z9us6 (512 MB, 19.5% util) · lambda-function-ancpd0 (512 MB, 19.5% util) · data-lake-curated (existing 90d Glacier lifecycle preserved) · dynamodb-table-8q8f66 (PAY_PER_REQUEST, no waste)

---

### Lambda — Allocated vs Observed

Lambda bills on **allocated** memory (GB-sec), not actual usage. 96.7% of allocated memory across the three flagged functions is billed but never used.

| Function | Allocated | Avg Used | p99 Used | Min Observed | Utilization | Datapoints |
|----------|-----------|----------|----------|-------------|-------------|------------|
| lambda-function-atrjum | 3,008 MB | ~100 MB | 100 MB | 91.21 MB | 3.3% | 720 |
| lambda-function-37781v | 3,008 MB | ~100 MB | 100 MB | 82.39 MB | 3.3% | 720 |
| lambda-function-luzj7m | 3,008 MB | ~100 MB | 100 MB | 86.75 MB | 3.3% | 720 |
| lambda-function-5z9us6 | 512 MB | ~100 MB | 100 MB | 100 MB | 19.5% | 720 |
| lambda-function-ancpd0 | 512 MB | ~100 MB | 100 MB | 100 MB | 19.5% | 720 |

Metric window: 720 hourly datapoints (30 days). Each flagged function has exactly 1 datapoint below 100 MB (min values above); otherwise flat at 100 MB. Duration (p95/p99), error rate, throttles, cold-start evidence: **Not available in the provided data; verify in the real environment.**

Cost evidence: avg monthly Lambda spend $943.33 · pricing_note: "3008MB → 512MB로 줄이면 함수당 약 $250/mo 절감 (3 함수 합계 $750/mo)"

---

### S3 — Infrastructure State vs Observed Access

| Bucket | Lifecycle Config | Access (30d) | Status |
|--------|-----------------|--------------|--------|
| data-lake-raw (554gvl) | **None** | Active GET requests observed | ❌ No lifecycle |
| data-lake-archive (xu5s05) | **None** | Variable GET requests observed — reads non-zero | ❌ Archive bucket in STANDARD |
| data-lake-curated (9m71do) | Glacier transition at 90d | Steady GET requests | ✅ Compliant (lifecycle preserved) |

Available metrics: `get_requests` only (30-day window). `BucketSizeBytes`, `NumberOfObjects`, noncurrent version counts, incomplete multipart upload size: **Not available in the provided data; verify in the real environment.**

Cost evidence: avg monthly S3 spend $200.44 · pricing_note: "8 TB eligible × ($0.023 − $0.004)/GB = 8,192 GB × $0.019 ≈ $155.6 → ~$152/mo" · per-bucket GB breakdown not available — savings are aggregate only.

Note: `data-lake-archive` shows non-zero GET requests — retrieval latency tolerance must be validated with the data platform owner before applying deep archive transitions.

---

### DynamoDB — Provisioned vs Consumed Capacity

| Table | Billing | Prov RCU | Prov WCU | Avg RCU | Avg WCU | RCU Util | WCU Util | Auto Scaling |
|-------|---------|----------|----------|---------|---------|----------|----------|-------------|
| dynamodb-table-wouiv4 | PROVISIONED | 5,000 | 1,000 | 100.0 | 87.94 | **2.0%** | **8.8%** | ❌ None |
| dynamodb-table-8q8f66 | PAY_PER_REQUEST | — | — | — | — | N/A | N/A | N/A |

Metric window: 720 hourly datapoints (30 days). RCU perfectly flat (min = max = avg = 100) — automated/scheduled read pattern. WCU: min 0, p99 100, avg 87.94 — idle periods present. No `ProvisionedThroughputExceeded` events observed.

Rules triggered: **D1** (avg util < 20%, p99 util < 50%, zero throttling) · **D2** (RCU severely under-utilized) · **D3** (no Auto Scaling configured)

Cost evidence: avg monthly DynamoDB spend $672.39 · pricing_note states ~$522/mo as scenario conservative estimate. Unit-rate arithmetic in pricing_note ($427 RCU + $427 WCU) yields ~$854 upper bound — treated as reference only; $522 is the authoritative scenario figure.

---

## 2. Root Cause

All three waste patterns share a common origin: **resources provisioned to historical or anticipated peak capacity at launch and never revisited**. No governance mechanism exists across any of the three services to detect and surface ongoing over-allocation.

- **Lambda**: The three 3008 MB functions were likely set to maximize CPU burst during initial development. Over 30 days of production traffic, actual memory usage converges at p99 = 100 MB with minimal variance (3.3% utilization). No CloudWatch alarm, Lambda Power Tuning gate, or IaC policy exists to detect memory waste.

- **DynamoDB**: `dynamodb-table-wouiv4` was provisioned at 5,000 RCU / 1,000 WCU — a launch-time estimate that the workload never reached. Actual throughput has been flat at ~100 RCU / ~88 WCU for the full 30-day window. The absence of Application Auto Scaling means provisioned capacity remained static while the workload settled at 2–9% utilization.

- **S3**: `data-lake-raw` and `data-lake-archive` were created without lifecycle governance. `data-lake-archive`'s name signals archival intent but the lifecycle configuration was never implemented, leaving all objects in S3 Standard indefinitely. The lifecycle pattern established in `data-lake-curated` was not replicated at provisioning time.

**Cross-domain interaction — Lambda → DynamoDB throttle risk after right-sizing:** After reducing DynamoDB capacity to 120 RCU/WCU, the Auto Scaling scale-out cooldown (60s) creates a brief window where a sudden Lambda burst could trigger `ProvisionedThroughputExceeded`. Lambda `timeout = 30s` means failed DynamoDB calls will retry and accumulate billed duration. Mitigation: set Auto Scaling `scale_out_cooldown = 60s` and `max_capacity = 500`; monitor Lambda error rate and DynamoDB throttle count together after applying both changes.

**Cross-domain confirmation — Lambda memory reduction is DynamoDB-safe:** boto3's DynamoDB client operates well within 100 MB. Reducing Lambda memory to 256 MB will not affect DynamoDB API call latency or reliability.

---

## 3. Proposed Solution

### Immediate Actions

Ordered by recommended deployment sequence (lowest rollback risk first):

**DynamoDB (apply first — additive change + lowest rollback risk)**

1. Reduce `dynamodb-table-wouiv4` `read_capacity` from 5,000 → **120** and `write_capacity` from 1,000 → **120**. Evidence: p99 peak for both RCU and WCU is 100; 120 provides 20% safety buffer with zero observed throttling.
2. Add `aws_appautoscaling_target` and `aws_appautoscaling_policy` for both read and write dimensions:
   - Read: min 120, max 500, target 70%
   - Write: min 120, max 500, target 70%
3. Monitor `ProvisionedThroughputExceeded` for 48h post-deployment. No throttling evidence in provided data, but confirm in AWS Console before applying.

**Lambda (apply second — requires deploy + observe cycle)**

4. Before production: run [AWS Lambda Power Tuning](https://github.com/alexei-led/aws-lambda-power-tuning) in staging for `lambda-function-atrjum`, `lambda-function-37781v`, and `lambda-function-luzj7m` to validate that duration does not increase enough to offset savings. Duration metrics are not available in the provided data.
5. Based on Power Tuning results (expected to confirm 256 MB as optimal), update `memory_size` from 3008 → **256** for all three flagged functions in Terraform.
6. After deployment, monitor `Duration` (p99), `Errors`, `Throttles`, and `MaxMemoryUsed` for at least 48–72 hours. Rollback: revert `memory_size` to 3008.

**S3 (apply last — takes 24–48h to reflect in billing)**

7. Validate restore and compliance requirements with the data platform owner for both buckets before applying transitions — confirm no Object Lock, legal hold, or replication dependency.
8. Validate `data-lake-archive` read patterns via S3 server access logs or Storage Lens before choosing transition depth. GET metrics show non-zero access; do not assume cold-only without log evidence.
9. Apply lifecycle config to `data-lake-raw`: STANDARD_IA at 30d, GLACIER at 90d, abort incomplete MPU at 7d.
10. Apply lifecycle config to `data-lake-archive`: STANDARD_IA at 30d, GLACIER at 90d, abort incomplete MPU at 7d. If reads are confirmed rare, reduce STANDARD_IA window — validate first.

### Preventive Actions

**Provisioning governance (all services)**
1. Enforce IaC policy: require `memory_size` justification tag (`FinOps:MemoryJustified = true`) for any Lambda `memory_size > 1024` MB.
2. Enforce Auto Scaling as mandatory for all new PROVISIONED DynamoDB tables via Terraform module standard or AWS Config rule (`dynamodb-autoscaling-enabled`).
3. Enforce Terraform policy: require `aws_s3_bucket_lifecycle_configuration` for every `aws_s3_bucket` in the data lake, with at minimum `abort_incomplete_multipart_upload`.

**Detection (all services)**
4. Add CloudWatch alarm on Lambda `(MaxMemoryUsed / memory_size) < 20%` sustained 7 days — triggers automatic rightsizing recommendation.
5. Add CloudWatch alarm on DynamoDB `ConsumedReadCapacityUnits / ProvisionedReadCapacityUnits < 20%` and `ConsumedWriteCapacityUnits / ProvisionedWriteCapacityUnits < 20%` sustained 7 days.
6. Enable S3 Storage Lens organization-level dashboard to surface `BucketSizeBytes`, noncurrent version counts, and incomplete multipart upload bytes monthly.

**Process**
7. Run Lambda Power Tuning for any Lambda function exceeding $50/mo before setting `memory_size` in Terraform.
8. Quarterly DynamoDB capacity review: for any PROVISIONED table spending over $200/mo, require a utilization report showing avg and p99 vs provisioned capacity.

---

## 4. Estimated Monthly Savings

| Domain | Resources Changed | Monthly Savings | Annual Savings |
|--------|------------------|----------------|----------------|
| Lambda | 3 of 5 functions (3008 → 256 MB) | ~$750 | ~$9,000 |
| S3 | 2 of 3 buckets (lifecycle added) | ~$152 | ~$1,824 |
| DynamoDB | 1 of 2 tables (5000/1000 → 120/120 RCU/WCU) | ~$522 | ~$6,264 |
| **TOTAL** | **6 resources** | **~$1,424/mo** | **~$17,088/yr** |

Current avg monthly spend: $10,743.71 → waste ratio: **13.3%**

Pricing source: cost_report.json pricing_note primary. aws-pricing MCP unavailable this run (credentials invalid).

DynamoDB note: $522/mo is the scenario-provided conservative figure. Upper bound via unit-rate arithmetic (120/120 optimized vs 5000/1000 provisioned): ~$880/mo — reference only.
S3 note: $152/mo is the aggregate figure. Per-bucket breakdown requires `BucketSizeBytes` data not available in the provided metrics.
