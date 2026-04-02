---
name: finops-s3
description: >
  FinOps Analysis Skill — Detects cost waste in AWS S3 buckets caused by
  versioning-enabled buckets without a lifecycle policy, leading to unbounded
  noncurrent version accumulation. Automatically executes when given a
  Terraform configuration (main.tf), CloudWatch metrics (metrics.json), and an
  AWS cost report (cost_report.json) containing aws_s3_bucket resources.
  Keywords: "S3 cost", "S3 versioning", "noncurrent version", "lifecycle policy", "FinOps S3".
user_invocable: false
---

# FinOps S3 Analysis Skill

## Directory Layout

| Variable | Path | Purpose |
|----------|------|---------|
| `SKILL_DIR` | Base directory of this skill (e.g. `.claude/skills/finops-s3`) | Contains `scripts/` and `rules/` |
| `WORK_DIR` | Current working directory | Contains the input data files to analyze |

---

## Step 1 — Locate Input Files

Recursively scan `WORK_DIR` for all files:

```bash
find WORK_DIR -type f | sort
```

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform — `aws_s3_bucket`, `aws_s3_bucket_versioning`, `aws_s3_bucket_lifecycle_configuration` | Cannot analyze — ask user for path |
| `metrics.json` | CloudWatch metrics: `storage_bytes`, `noncurrent_version_count` per bucket | Mark section "Cannot confirm from provided data — real-environment verification required" |
| `cost_report.json` | Monthly S3 cost history with pricing_note | Mark section "Cannot confirm from provided data — real-environment verification required" |

Print the found file paths before proceeding.

---

## Step 2 — Run Pipeline Scripts

```bash
# 1. Parse
python SKILL_DIR/scripts/parser.py \
  --tf      <main.tf path> \
  --metrics <metrics.json path> \
  --cost    <cost_report.json path> \
  --out     WORK_DIR/parsed_input.json

# 2. Analyze
python SKILL_DIR/scripts/analyzer.py \
  --input WORK_DIR/parsed_input.json \
  --rules SKILL_DIR/rules/missing_lifecycle_policy.json \
  --out   WORK_DIR/findings.json

# 3. Format (also writes main_optimized.tf automatically)
python SKILL_DIR/scripts/formatter.py \
  --findings    WORK_DIR/findings.json \
  --original-tf <main.tf path> \
  --out         WORK_DIR/finops_report.md
```

If `python` is not found, try `python3`. If Python is unavailable, fall back to Step 2-alt.

> **Note**: Unlike other FinOps skills, the formatter writes both `finops_report.md`
> **and** `main_optimized.tf` in a single pass. No separate Write step is needed for
> the Terraform file when using scripts.

---

## Step 2-alt — Fallback (No Python)

Read all three input files with the Read tool and apply the rule below manually.

**Detection rule (from `rules/missing_lifecycle_policy.json`):**

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| V1 | `aws_s3_bucket_versioning.status == "Enabled"` AND no `aws_s3_bucket_lifecycle_configuration` (or existing one has no `noncurrent_version_expiration`) AND `noncurrent_version_count` slope > 0.1/hr | HIGH | ADD_LIFECYCLE_POLICY |

**Trend detection**: compute `slope = (last_datapoint - first_datapoint) / total_datapoints`.
If slope > 0.1, noncurrent versions are actively accumulating.

**Savings estimate** (priority order):
1. Parse dollar amount from `pricing_note` in `cost_report.json` → split across flagged buckets
2. `noncurrent_storage_gb` from pricing_note × `$0.023/GB-month` → split across flagged buckets
3. `avg_s3_monthly × 0.8` / number_of_flagged_buckets

**Lifecycle recommendations by environment** (inferred from bucket name):
| Environment | Noncurrent Expiry | Versions Kept | Multipart Abort |
|-------------|-------------------|---------------|-----------------|
| prod        | 90 days           | 5             | 7 days          |
| staging     | 30 days           | 3             | 3 days          |
| dev / test  | 14 days           | 2             | 3 days          |
| unknown     | 30 days           | 3             | 7 days          |

---

## Step 3 — Deep Architectural Analysis

### Analysis Principles

- **Cross-evidence principle**: All conclusions must be based on cross-evidence from the files found in `WORK_DIR`. Do not draw conclusions from a single source alone.
- **Uncertainty principle**: Information not present in the provided files must be labeled **"Cannot confirm from provided data — real-environment verification required"**.
- **Scope principle**: Do not describe AWS Console, real infrastructure, or external system state beyond what the files confirm.

Use the Read tool to read `main.tf` and `WORK_DIR/findings.json`. Analyze:

**3.1 Evidence from Infrastructure (Terraform)**
- Total `aws_s3_bucket` count, buckets with versioning enabled
- Which buckets have / are missing `aws_s3_bucket_lifecycle_configuration`
- Which existing lifecycle configs are missing `noncurrent_version_expiration`

**3.2 Evidence from Metrics (30 days)**
- `noncurrent_version_count` trend per bucket: show first/last values and slope
- `storage_bytes` trend: growing or stable

**3.3 Evidence from Cost Report (6 months)**
- Monthly S3 spend trend
- `pricing_note` noncurrent storage cost breakdown

**3.4 Root Cause**
- Why noncurrent versions are accumulating (missing lifecycle policy)
- Why this is often overlooked (S3 billing doesn't separate current vs noncurrent)

**Proposed Solution**
- Immediate: apply the `aws_s3_bucket_lifecycle_configuration` Terraform blocks
- Preventive: AWS Config rule, Org-level module enforcement, budget alerts

**Optimized Terraform rules**:
- The formatter script already generates `main_optimized.tf` with the original content
  plus new lifecycle blocks appended. If scripts ran successfully, verify the file exists.
- If running fallback: Use the Write tool to create `WORK_DIR/main_optimized.tf` containing:
  1. The original `main.tf` content unchanged
  2. New `aws_s3_bucket_lifecycle_configuration` blocks (one per flagged bucket)
     using actual resource names and lifecycle values from the recommendations table above.
- Do NOT use placeholders. Use the real resource names from `main.tf`.

---

## Step 4 — Write Final Report

Use the Write tool to save `WORK_DIR/finops_report.md` (the formatter script handles this
automatically; only use Write manually if running in fallback mode). Then output the full
report in the response.

Verify that both files exist after the skill completes:
- `WORK_DIR/finops_report.md`
- `WORK_DIR/main_optimized.tf`

### Report format:

```
# FinOps S3 Deep Analysis Report — <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Unbounded S3 Noncurrent Version Accumulation |
| Affected Resources | X of Y aws_s3_bucket |
| Detection Signal | noncurrent_version_count growing at N/hr over 30 days |
| Monthly Waste | $XX |

## Root Cause

### 3.1 Evidence from Infrastructure (Terraform)
<analysis>

### 3.2 Evidence from Metrics (30 days)
| Bucket | NCV Start | NCV End | Slope (per hr) | Trend |
|--------|-----------|---------|----------------|-------|

### 3.3 Evidence from Cost Report (6 months)
| Month | S3 Spend | Total Spend |
|-------|----------|-------------|

### 3.4 Root Cause
<root cause>

## Proposed Solution

### Immediate Actions (Week 1)
1. Apply lifecycle Terraform blocks in main_optimized.tf

### Preventive Actions (Week 2-4)
1. ...

## Estimated Monthly Savings (USD)
$XX.XX

## Optimized Terraform
<lifecycle configuration blocks>
```

---

*Generated by: finops-s3 skill — Claude Code*
