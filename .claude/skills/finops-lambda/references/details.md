# finops-lambda — Detailed Rules

## Required Safety Checks

### Before changing memory
- Use `MaxMemoryUsed` and adequate headroom, not average memory only.
- Model duration at the target memory tier when data exists, or recommend AWS
  Lambda Power Tuning instead of changing directly.
- Check p95/p99 duration, timeout rate, errors, throttles, concurrency, cold-start sensitivity.
- Preserve performance requirements for latency-sensitive functions.

### Before reducing timeout
- Use p99 or max successful duration, not average.
- Include upstream/downstream timeout contracts.
- Don't reduce below expected batch, stream, or network retry needs.

## Deep Architectural Analysis

### Infrastructure
- Function count, runtime, architecture, memory size, timeout, ephemeral storage,
  reserved/provisioned concurrency, ESMs, VPC config, tags.
- Batch size, retry policy, max event age, DLQ/on-failure destination, stream/queue source settings.

### Metrics
- Invocations, duration avg/p95/p99/max.
- Max memory used and memory utilization.
- Errors, timeouts, throttles, retries, iterator age/backlog for stream/queue
  sources, concurrent executions, provisioned-concurrency utilization.
- Cold-start evidence when provided.

If only avg duration or avg memory provided, lower confidence and prefer a
tuning experiment over a direct Terraform change.

### Cost
- Monthly Lambda spend trend.
- Request cost, compute GB-seconds, provisioned concurrency, ephemeral storage,
  data transfer/VPC-related costs.
- Architecture- and region-specific pricing — prefer cost report or aws-pricing MCP.
- Separate savings by source: memory, timeout/error path, provisioned
  concurrency, ephemeral storage, architecture, retry reduction.

### Root Cause (governance frame)
- Memory set high for CPU performance but never power-tuned.
- Timeout is a broad default rather than workload-specific.
- Provisioned concurrency enabled 24/7 for narrow peak hours.
- Retries/errors inflate billed duration and downstream work.
- Ephemeral storage increased for temporary workload and not revisited.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → aws-pricing MCP → rule fallback.

```
compute_cost                = invocations * duration_ms / 1000 * memory_gb * gb_second_price
request_cost                = requests / 1,000,000 * request_price
provisioned_concurrency_cost= provisioned_concurrency_gb_seconds * pc_price
ephemeral_storage_cost      = billable_ephemeral_storage_gb_seconds * ephemeral_price
```

Do not assume memory reduction saves linearly. Recalculate with modeled duration
at the new memory tier.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- If p95/p99 and cost model are incomplete, add a review or power-tuning plan
  instead of changing memory.
- Memory: valid Lambda value 128 MB – 10,240 MB in 1 MB increments.
- Reduce timeout only when p99/max duration and upstream contracts support it.
- Tune provisioned-concurrency schedules/values only when utilization supports it.
- Comments explain evidence, expected savings, rollback/monitoring.

## Preventive Actions

1. Run Lambda Power Tuning for high-cost functions.
2. Alert on low memory utilization + flat duration, high errors, low provisioned-concurrency utilization.
3. Review timeouts and retry policies per event source.
