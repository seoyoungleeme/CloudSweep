---
name: finops-ecs
description: >
  FinOps ECS/Fargate Analysis Skill. Detects cost waste in AWS ECS services running
  on Fargate caused by over-provisioned task CPU and memory, static desired_count
  without Auto Scaling, and stale platform versions. Use for Terraform configurations,
  CloudWatch metrics, and AWS cost reports containing aws_ecs_service and
  aws_ecs_task_definition resources.
  Keywords: "ECS cost", "Fargate waste", "task right-sizing", "vCPU over-provisioned",
  "memory over-provisioned", "Fargate optimization".
user_invocable: false
---

# FinOps ECS/Fargate Analysis Skill

## Directory Layout

| Variable  | Path | Purpose |
|-----------|------|---------|
| SKILL_DIR | Base directory of this skill | Contains rules/ assets |
| WORK_DIR  | Directory containing input files | Read inputs, write outputs |

---

## Step 1 — Locate Input Files

Scan WORK_DIR for:

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | ECS service and task definition resources | Cannot continue — ask user |
| `metrics/metrics.json` or `metrics.json` | CloudWatch `cpu_percent` and `memory_percent` per service (30-day hourly) | Mark metrics section as "Not available in the provided data" |
| `cost_report.json` | Monthly ECS + Fargate spend | Mark cost section as "Not available in the provided data" |

---

## Step 2 — Parse Infrastructure

From `main.tf`, extract for each `aws_ecs_service`:
- `name`, `desired_count`, `launch_type`, `platform_version`
- Reference to its `aws_ecs_task_definition` (via `task_definition`)

From each linked `aws_ecs_task_definition`:
- `cpu` (vCPU units: 256/512/1024/2048/4096/8192/16384)
- `memory` (MB)
- Container definitions — note any per-container CPU/memory overrides

Group: each service + task_definition pair forms one analysis unit.

---

## Step 3 — Analyze Metrics

For each service, read `cpu_percent` and `memory_percent` from metrics.

Compute:
- `cpu_avg_pct`: mean of all 720 datapoints
- `cpu_p95_pct`: 95th percentile (sort datapoints, take 684th value)
- `cpu_max_pct`: maximum value
- `memory_avg_pct`: mean
- `memory_p95_pct`: 95th percentile
- `memory_max_pct`: maximum

Actual usage (absolute):
- `cpu_p95_actual_units` = provisioned_cpu × cpu_p95_pct / 100
- `memory_p95_actual_mb` = provisioned_memory_mb × memory_p95_pct / 100

**Safety rule**: Do NOT recommend reducing CPU or memory if:
- `cpu_max_pct ≥ 80%` — task has hit near-capacity CPU; investigate before reducing
- `memory_max_pct ≥ 90%` — task may be OOM-risk; do not reduce memory without investigation

---

## Step 4 — Apply Detection Rules

Read `rules/fargate_rightsizing.json` for thresholds. Apply each rule to every service.

### Rule E1 — CPU Over-Provisioned

Condition: `launch_type == FARGATE AND cpu_avg_pct < 20 AND cpu_p95_pct < 50 AND cpu_max_pct < 80`

Severity: HIGH

Action: `RIGHTSIZE_CPU`

Right-sized CPU:
1. `cpu_p95_actual_units × 1.3` (30% safety headroom)
2. Round up to next valid Fargate CPU value: 256, 512, 1024, 2048, 4096, 8192, 16384
3. Confirm the selected CPU supports the target memory (Fargate valid combinations apply)

### Rule E2 — Memory Over-Provisioned

Condition: `launch_type == FARGATE AND memory_avg_pct < 20 AND memory_p95_pct < 50 AND memory_max_pct < 90`

Severity: HIGH

Action: `RIGHTSIZE_MEMORY`

Right-sized memory:
1. `memory_p95_actual_mb × 1.3` (30% safety headroom)
2. Round up to nearest 512 MB boundary
3. Must satisfy: valid Fargate memory range for the target CPU value

### Valid Fargate CPU/Memory Combinations (us-east-1)

| CPU (units) | vCPU | Min Memory | Max Memory |
|-------------|------|------------|------------|
| 256 | 0.25 | 512 MB | 2 GB |
| 512 | 0.5 | 1 GB | 4 GB |
| 1024 | 1 | 2 GB | 8 GB |
| 2048 | 2 | 4 GB | 16 GB |
| 4096 | 4 | 8 GB | 30 GB |
| 8192 | 8 | 16 GB | 60 GB |
| 16384 | 16 | 32 GB | 120 GB |

### Rule E3 — No Auto Scaling on Static Desired Count

Condition: `desired_count` is static (no `aws_appautoscaling_target` referencing this service)

Severity: MEDIUM

Action: `ADD_ECS_AUTOSCALING`

Note: Static desired_count means tasks run at full cost even during low-traffic periods. Target Tracking on `ECSServiceAverageCPUUtilization` at 60–70% is the recommended baseline policy.

### Rule E4 — Stale Fargate Platform Version

Condition: `platform_version != "LATEST"` (pinned to specific version e.g. "1.4.0")

Severity: LOW

Action: `UPDATE_PLATFORM_VERSION`

Note: LATEST ensures access to security patches and feature improvements without manual version tracking.

---

## Step 5 — Calculate Savings

Priority order for pricing data:
1. `cost_report.json` `pricing_note` — use as authoritative if it contains a breakdown
2. Fargate list prices (us-east-1): vCPU-hour $0.04048, GB-hour $0.004445
3. If Savings Plans or CRIs are in effect, note that effective savings may differ from list-price calculation

Savings per task per month = (old_cpu_units/1024 × $0.04048 + old_mem_gb × $0.004445 - new_cpu_units/1024 × $0.04048 - new_mem_gb × $0.004445) × 730h

Total savings = savings_per_task × desired_count × affected_services

---

## Step 6 — Write Output Files

Write all four files to WORK_DIR:

### `parsed_input.json`
- `scenario_id`, `skill`, `region`
- `total_services`, `total_task_definitions`
- Per-service: name, launch_type, desired_count, platform_version, cpu, memory, metrics summary, status, rules_fired
- `cost_data`: monthly spend array, avg, pricing_note, authoritative waste

### `findings.json`
- `analyzed_at`, `scenario_id`, `skill`, `rule_set`, `region`
- `findings_count`, `findings[]`: rule_id, resource_id, severity, confidence, condition_met, action, recommended_change, estimated_savings
- `compliant[]`: resources with no findings
- `cost_summary`

### `finops_report.md`

```
# FinOps ECS/Fargate Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
...

## Evidence

### Infrastructure Evidence (Terraform)
<table of all services: name, CPU, memory, desired_count, launch_type, status>

### Metric Evidence (30 days)
<per-service table: cpu_avg_pct, cpu_p95_pct, cpu_max_pct, memory_avg_pct, memory_p95_pct, status>

### Cost Evidence (6 months)
<monthly table, avg, pricing_note breakdown>

### Root Cause
<architectural explanation>

## Proposed Solution

### Immediate Actions
1. Right-size task definitions
2. Roll out with staged deployment
3. Monitor for 7 days

### Preventive Actions
1. Add ECS Auto Scaling
2. Tag services with workload_pattern
3. Alert on sustained < 20% CPU utilization

## Estimated Monthly Savings
$XX / month
$XX / year
<savings table: before vs after>
```

### `main_optimized.tf`
- Preserve terraform {} and provider {} blocks
- Add FinOps comment block at top of each modified task definition
- Reduce `cpu` and `memory` in affected `aws_ecs_task_definition` resources
- Keep `aws_ecs_service` resources unchanged (desired_count, platform_version)
- Add inline comment on changed lines: `# was XXXX — right-sized to p95 × 1.3 safety factor`
- Compliant resources: unchanged, with a comment `# No changes — CPU/memory utilization within acceptable range`

---

*Generated by: finops-ecs skill v1.0.0 — Claude Code*
