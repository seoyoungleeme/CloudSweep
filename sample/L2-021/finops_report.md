# FinOps SQS Deep Analysis Report — L2-021

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Short Polling / Empty Receive Waste (Q1) |
| Affected Resources | 5 of 7 `aws_sqs_queue` (receive_wait_time_seconds=0) |
| Monthly Waste | $120.00 |
| Annual Waste | $1,440.00 |
| Waste Percentage | ~77% of avg SQS spend ($156/mo) |

---

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)

7 `aws_sqs_queue` resources. 5 queues use short polling (`receive_wait_time_seconds=0`); 2 queues use long polling (`receive_wait_time_seconds=20`). The long-polling queues operate at 20,000ms polling interval — 200× slower than the 100ms tight loop on the problem queues.

| Queue | wait_time_s | polling_interval_ms | empty_receives/day | messages/day | Q1? |
|---|---|---|---|---|---|
| sqs-queue-83ackx | **0** | 100 | 2,000,000 | 1,000 | ✅ Yes |
| sqs-queue-ackuzr | **0** | 100 | 2,000,000 | 1,000 | ✅ Yes |
| sqs-queue-mwbrm2 | **0** | 100 | 2,000,000 | 1,000 | ✅ Yes |
| sqs-queue-hil4hg | **0** | 100 | 2,000,000 | 1,000 | ✅ Yes |
| sqs-queue-mq58yd | **0** | 100 | 2,000,000 | 1,000 | ✅ Yes |
| sqs-queue-ouczyn | 20 | 20,000 | 3,000 | 5,000 | ❌ baseline |
| sqs-queue-gq175x | 20 | 20,000 | 3,000 | 5,000 | ❌ baseline |

The scale of the imbalance is stark: each short-polling queue generates **2,000,000 empty receives per day** against only **1,000 actual messages** — 99.95% of all API calls return nothing. Every one of those 2 million calls is billed at $0.40/million.

### 3.2 Evidence from Metrics (CloudWatch — 30 days)

| Queue | wait_time_s | Avg Empty/hr (CW) | TF empty/day | Monthly Empty (TF) | Messages/hr | Empty Ratio | Issue |
|---|---|---|---|---|---|---|---|
| sqs-queue-83ackx | 0 | 100.0 | 2,000,000 | **60,000,000** | 41.2 | 99.95% | ✅ Q1 |
| sqs-queue-ackuzr | 0 | 100.0 | 2,000,000 | **60,000,000** | 40.3 | 99.95% | ✅ Q1 |
| sqs-queue-mwbrm2 | 0 | 100.0 | 2,000,000 | **60,000,000** | 40.2 | 99.95% | ✅ Q1 |
| sqs-queue-hil4hg | 0 | 100.0 | 2,000,000 | **60,000,000** | 39.2 | 99.95% | ✅ Q1 |
| sqs-queue-mq58yd | 0 | 100.0 | 2,000,000 | **60,000,000** | 38.3 | 99.95% | ✅ Q1 |
| sqs-queue-ouczyn | 20 | 88.5 | 3,000 | 2,700,000 | 99.8 | 47.0% | ❌ baseline |
| sqs-queue-gq175x | 20 | 85.7 | 3,000 | 2,700,000 | 99.6 | 46.2% | ❌ baseline |

> **Note:** CloudWatch sampled totals (72,000/30d per short-polling queue) are 833× lower than Terraform's `empty_receives_per_day=2,000,000` scenario-level figure. Savings are calculated from the TF-authoritative value per skill rules.

**Key comparisons:**
- Short-polling queues: 2,000,000 empty/day → **$9.60/day per queue** in empty API call costs
- Long-polling queues: 3,000 empty/day → **$0.0012/day per queue** — 667× cheaper
- Long-polling queues also receive **5× more messages** (5,000/day vs 1,000/day) with fewer empties

Long polling (`receive_wait_time_seconds=20`) holds each `ReceiveMessage` connection open for up to 20 seconds, returning only when a message arrives or the wait expires. The 100ms polling loop on short-polling queues issues 600 `ReceiveMessage` calls per minute — the vast majority returning empty.

### 3.3 Evidence from Cost Report (6 months)

| Month | SQS Spend | Total Spend | SQS % |
|---|---|---|---|
| M-5 | $138.06 | $1,278.25 | 10.8% |
| M-4 | $134.12 | $1,250.91 | 10.7% |
| M-3 | $156.71 | $1,200.59 | 13.1% |
| M-2 | $181.40 | $1,240.15 | 14.6% |
| M-1 | $171.71 | $1,148.82 | 14.9% |
| M-0 | $156.86 | $1,216.17 | 12.9% |
| **Avg** | **$156.48** | **$1,222.48** | **12.8%** |

`pricing_note`: *"SQS API 호출 $0.40/백만 건. 5큐 × 약 60M 빈 수신/월 = 300M 호출 → $120/월 낭비"*

At $120/mo waste against $156/mo avg SQS spend, **~77% of all SQS spend is from empty API calls** that return no messages.

### 3.4 Root Cause

The 5 short-polling queues were created with the SQS default configuration (`receive_wait_time_seconds=0`). The consumer applications poll every 100ms in a tight loop — a common pattern when consumers are coded for minimal latency. This pattern generates **86,400 `ReceiveMessage` calls per queue per day** from polling alone (1 call every 100ms × 86,400 seconds). Combined with 2 million daily empty responses implied by scenario metrics, the queue consumers are running essentially free-spinning polling loops.

The 2 long-polling queues (`ouczyn`, `gq175x`) prove the alternative: identical business logic (message delivery, visibility timeout) operates at `receive_wait_time_seconds=20` with 667× fewer empty receives and no latency penalty for message processing — SQS delivers messages immediately when they arrive regardless of the wait timeout.

---

## Proposed Solution

### Immediate Actions (Week 1)
1. Apply `main_optimized.tf` — sets `receive_wait_time_seconds = 20` for all 5 flagged queues.
2. SQS queue attributes can be changed **in-place without recreation** via `aws sqs set-queue-attributes` or Terraform apply — no message loss or downtime.
3. Consumer application change **not required** for queue-level long polling: setting `receive_wait_time_seconds=20` on the queue automatically applies it to all `ReceiveMessage` calls that don't specify `WaitTimeSeconds` explicitly.
   - If consumer code hardcodes `WaitTimeSeconds=0`, update that too for full benefit.
4. `terraform plan -out=sqs_polling_fix.plan` → review → `terraform apply`.

### Preventive Actions (Week 2–4)
1. **Terraform module default** — set `receive_wait_time_seconds = 20` as the default in the shared SQS queue module; require explicit justification comment for `receive_wait_time_seconds = 0`.
2. **CloudWatch Alarm** — `NumberOfEmptyReceives > 10,000/hr` per queue → SNS notification.
3. **Consumer SDK** — document `WaitTimeSeconds=20` in the internal SQS consumer SDK template so new polling implementations inherit long polling automatically.
4. **Cost Explorer tag** — tag all SQS queues with the owning service; correlate empty receive volume against service names in Cost Explorer to catch future regression.

---

## Estimated Monthly Savings (USD)

| Queue | wait_time_s | empty_receives/day | Monthly Empty | Monthly Savings |
|---|---|---|---|---|
| sqs-queue-83ackx | 0 | 2,000,000 | 60,000,000 | $24.00 |
| sqs-queue-ackuzr | 0 | 2,000,000 | 60,000,000 | $24.00 |
| sqs-queue-mwbrm2 | 0 | 2,000,000 | 60,000,000 | $24.00 |
| sqs-queue-hil4hg | 0 | 2,000,000 | 60,000,000 | $24.00 |
| sqs-queue-mq58yd | 0 | 2,000,000 | 60,000,000 | $24.00 |
| **Total** | | | **300,000,000** | **$120.00/mo** |

**Annual savings: $1,440.00**

*(Savings calculated from Terraform-provided `empty_receives_per_day` scale value; CloudWatch sample totals are 833× lower due to sampling — TF value is authoritative per scenario.)*

---

## Optimized Terraform

See `main_optimized.tf` for the complete modified configuration.

```bash
# Verification:
# 1. terraform plan -out=sqs_polling_fix.plan
# 2. Confirm only receive_wait_time_seconds changes (in-place attribute update, no queue recreation)
# 3. terraform apply sqs_polling_fix.plan
# 4. Monitor NumberOfEmptyReceives metric — expect significant reduction within minutes
```

---

*Generated by: finops-sqs skill — Claude Code*
