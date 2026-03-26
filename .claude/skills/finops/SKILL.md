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

If multiple resource types are found, run the matching sub-skills in sequence.

If no matching sub-skill exists for a detected resource type, note it in the
report as "not yet supported" and continue with the types that are supported.

---

## Step 3 — Delegate to Sub-skill(s)

For each matched sub-skill, execute it by following that skill's SKILL.md
located at `.claude/skills/<sub-skill>/SKILL.md` relative to the project root.

Pass the same `WORK_DIR` and input file paths. Each sub-skill writes its own
`finops_report.md` (or a prefixed variant if multiple skills run).

---

## Step 4 — Summarize

If more than one sub-skill ran, output a combined summary listing:
- Which sub-skills were invoked
- Total issues found across all sub-skills
- Total estimated monthly and annual savings
