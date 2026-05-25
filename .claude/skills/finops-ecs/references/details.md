# finops-ecs — Detailed Rules

## Parse Infrastructure

From each `aws_ecs_service`:
- `name`, `desired_count`, `launch_type`, `platform_version`
- Reference to its `aws_ecs_task_definition` (`task_definition`)

From each linked `aws_ecs_task_definition`:
- `cpu` (vCPU units: 256/512/1024/2048/4096/8192/16384)
- `memory` (MB)
- Container definitions — note per-container CPU/memory overrides

Each service + task_definition pair forms one analysis unit.

## Analyze Metrics

For each service, read `cpu_percent` and `memory_percent`:
- `cpu_avg_pct`, `cpu_p95_pct`, `cpu_max_pct`
- `memory_avg_pct`, `memory_p95_pct`, `memory_max_pct`

Actual usage:
```
cpu_p95_actual_units  = provisioned_cpu * cpu_p95_pct / 100
memory_p95_actual_mb  = provisioned_memory_mb * memory_p95_pct / 100
```

**Safety**: do NOT recommend reducing if:
- `cpu_max_pct >= 80%` → task has hit near-capacity CPU.
- `memory_max_pct >= 90%` → OOM risk.

## Detection Rule Detail

### E1 — CPU Over-Provisioned (apply `rules/fargate_rightsizing.json`)
Condition: `launch_type == FARGATE AND cpu_avg_pct < 20 AND cpu_p95_pct < 50 AND cpu_max_pct < 80`
Severity: HIGH. Action: `RIGHTSIZE_CPU`.

Right-sized CPU:
1. `cpu_p95_actual_units * 1.3` (30% safety headroom).
2. Round up to next valid Fargate CPU value: 256, 512, 1024, 2048, 4096, 8192, 16384.
3. Confirm selected CPU supports target memory (see combinations below).

### E2 — Memory Over-Provisioned
Condition: `launch_type == FARGATE AND memory_avg_pct < 20 AND memory_p95_pct < 50 AND memory_max_pct < 90`
Severity: HIGH. Action: `RIGHTSIZE_MEMORY`.

Right-sized memory:
1. `memory_p95_actual_mb * 1.3` (30% headroom).
2. Round up to nearest 512 MB boundary.
3. Must satisfy valid Fargate memory range for target CPU.

### E3 — No Auto Scaling on Static Desired Count
Condition: `desired_count` static (no `aws_appautoscaling_target` references it).
Severity: MEDIUM. Action: `ADD_ECS_AUTOSCALING`.
Recommended baseline: Target Tracking on `ECSServiceAverageCPUUtilization` at 60–70%.

### E4 — Stale Fargate Platform Version
Condition: `platform_version != "LATEST"` (pinned e.g. "1.4.0").
Severity: LOW. Action: `UPDATE_PLATFORM_VERSION`.

## Valid Fargate CPU/Memory Combinations (us-east-1)

| CPU (units) | vCPU | Min Memory | Max Memory |
|-------------|------|------------|------------|
| 256 | 0.25 | 512 MB | 2 GB |
| 512 | 0.5 | 1 GB | 4 GB |
| 1024 | 1 | 2 GB | 8 GB |
| 2048 | 2 | 4 GB | 16 GB |
| 4096 | 4 | 8 GB | 30 GB |
| 8192 | 8 | 16 GB | 60 GB |
| 16384 | 16 | 32 GB | 120 GB |

## Savings Calculation

Priority: `cost_report.json` `pricing_note` (authoritative if breakdown given) →
Fargate list prices (us-east-1: vCPU-hour $0.04048, GB-hour $0.004445). If
Savings Plans/CRIs apply, effective savings may differ from list-price calculation.

```
savings_per_task_per_month = (
  old_cpu_units/1024 * 0.04048 + old_mem_gb * 0.004445
  - new_cpu_units/1024 * 0.04048 - new_mem_gb * 0.004445
) * 730h

total_savings = savings_per_task * desired_count * affected_services
```

## Output Files (under `WORK_DIR/result/`)

### `parsed_input.json`
- `scenario_id`, `skill`, `region`
- `total_services`, `total_task_definitions`
- Per-service: name, launch_type, desired_count, platform_version, cpu, memory,
  metrics summary, status, rules_fired
- `cost_data`: monthly spend array, avg, pricing_note, authoritative waste

### `findings.json`
- `analyzed_at`, `scenario_id`, `skill`, `rule_set`, `region`
- `findings_count`, `findings[]`: rule_id, resource_id, severity, confidence,
  condition_met, action, recommended_change, estimated_savings
- `compliant[]`: resources with no findings
- `cost_summary`

### `main_optimized.tf` Rules
- Preserve `terraform {}` and `provider {}` blocks.
- Add FinOps comment block at top of each modified task definition.
- Reduce `cpu`/`memory` in affected `aws_ecs_task_definition` resources.
- Keep `aws_ecs_service` unchanged (desired_count, platform_version).
- Inline comment on changed lines: `# was XXXX — right-sized to p95 × 1.3 safety factor`.
- Compliant resources: unchanged, with `# No changes — CPU/memory utilization within acceptable range`.

## Preventive Actions

1. Add ECS Auto Scaling.
2. Tag services with workload_pattern.
3. Alert on sustained < 20% CPU utilization.
