---
name: finops
description: >
  FinOps Orchestrator — Inspects input files and routes to the appropriate
  resource-specific FinOps skill. Invoke for any FinOps cost analysis request
  when the specific resource type is unknown or mixed.
  Keywords: "FinOps", "cloud cost", "cost analysis", "AWS waste", "비용 분석".
user_invocable: true
---

# FinOps Orchestrator Skill

This skill inspects the provided input files, determines which AWS resource
types are involved, and delegates to the appropriate sub-skill.

---

## Step 1 — Locate Input Files

Search for input files in `WORK_DIR`, then `WORK_DIR/sample/`.
Accept any combination of the following:

| File | Description |
|------|-------------|
| `main.tf` | Terraform resource definitions |
| `metrics.json` | CloudWatch metrics per resource |
| `cost_report.json` | Monthly cost/waste totals |

If no files are found, ask the user for the paths.

---

## Step 2 — Detect Resource Types

Read `main.tf` and identify which `resource "aws_*"` types are present.
Map each type to its sub-skill:

| Terraform Resource | Sub-skill |
|--------------------|-----------|
| `aws_lb`, `aws_alb` | `finops-elb` |
| `aws_db_instance` | `finops-rds` |

If multiple resource types are found, run the matching sub-skills in sequence.

If no matching sub-skill exists for a detected resource type, note it in the
report as "not yet supported" and continue with the types that are supported.

---

## Step 3 — Delegate to Sub-skill(s)

Each sub-skill always writes to fixed filenames (`findings.json`, `parsed_input.json`,
`finops_report.md`, `main_optimized.tf`). The orchestrator must snapshot these files
between sub-skill runs to prevent overwriting.

### Per sub-skill execution loop

For each matched sub-skill `<SKILL>` (e.g. `elb`, `rds`):

**a. Execute the sub-skill** by reading and following its SKILL.md at
   `.claude/skills/finops-<SKILL>/SKILL.md`. Pass the same `WORK_DIR` and input file paths.

**b. After it completes**, use the Bash tool to snapshot its output files:

```bash
cp WORK_DIR/findings.json       WORK_DIR/findings_<SKILL>.json
cp WORK_DIR/parsed_input.json   WORK_DIR/parsed_input_<SKILL>.json
cp WORK_DIR/finops_report.md    WORK_DIR/finops_report_<SKILL>.md
# main_optimized.tf is written by the agent (Write tool), not the scripts —
# read it and remember its content for the merge step, or copy:
cp WORK_DIR/main_optimized.tf   WORK_DIR/main_optimized_<SKILL>.tf
```

Proceed to the next sub-skill. The next sub-skill will overwrite the base filenames,
which is expected — the snapshots preserve each skill's output.

---

## Step 4 — Summarize and Merge

**If only ONE sub-skill ran**: the base output files (`finops_report.md`,
`main_optimized.tf`) are already the final combined outputs. No merge needed.

**If MORE THAN ONE sub-skill ran**, produce merged final outputs using the Write tool:

### 4a. Merge `WORK_DIR/finops_report.md`

Read each `finops_report_<SKILL>.md` in order. Write a single `WORK_DIR/finops_report.md` that:

1. Combined header:
   ```
   # FinOps Combined Analysis Report
   - Sub-skills run: finops-elb, finops-rds, ...
   - Total resources checked: N
   - Total issues found: N
   ```

2. Each sub-skill's full report content under its own heading:
   ```
   ## ELB Analysis (finops-elb)
   <full content of finops_report_elb.md>

   ## RDS Analysis (finops-rds)
   <full content of finops_report_rds.md>
   ```

3. Unified savings table at the bottom:
   ```
   ## Total Savings Summary
   | Sub-skill  | Issues | Monthly Savings | Annual Savings |
   |------------|--------|-----------------|----------------|
   | finops-elb | N      | $X              | $Y             |
   | finops-rds | N      | $X              | $Y             |
   | **TOTAL**  | **N**  | **$X**          | **$Y**         |
   ```

### 4b. Merge `WORK_DIR/main_optimized.tf`

Read each `main_optimized_<SKILL>.tf` in order. Write a single `WORK_DIR/main_optimized.tf` that:

1. Shared `terraform {}` and `provider "aws" {}` blocks — included **once** (from any sub-skill)
2. Each sub-skill's resource blocks in sequence, preceded by a section comment:
   ```hcl
   # ══════════════════════════════════════════
   # ELB changes — finops-elb
   # ══════════════════════════════════════════
   <resource blocks from main_optimized_elb.tf>

   # ══════════════════════════════════════════
   # RDS changes — finops-rds
   # ══════════════════════════════════════════
   <resource blocks from main_optimized_rds.tf>
   ```
