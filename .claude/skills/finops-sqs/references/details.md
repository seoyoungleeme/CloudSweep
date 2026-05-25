# finops-sqs — Detailed Rules

## Required Safety Checks

Before setting `receive_wait_time_seconds = 20`:
- Consumer HTTP/read timeout > wait time.
- Business latency requirements tolerate long polling.
- Lambda ESMs / SDK consumers behave correctly.
- Check `ApproximateAgeOfOldestMessage`, visible/not-visible message counts,
  errors, retries, DLQ movement.
- For FIFO queues: check message groups and throughput behavior.

## Deep Architectural Analysis

### Infrastructure
- Queue count, standard vs FIFO, `receive_wait_time_seconds`, visibility
  timeout, message retention, redrive policy, DLQ, encryption, tags.
- ESMs or consumer hints when present.

### Metrics
- Empty receives, total receives, empty-receive ratio, messages sent/deleted,
  visible/not-visible counts, age of oldest message, DLQ movement, errors.
- Distinguish idle queues from inefficient polling under real traffic.

### Cost
- Monthly SQS spend trend.
- Request cost by action when available.
- Region pricing — prefer cost report or aws-pricing MCP.
- Separate savings from long polling, batching, retry reduction, queue cleanup.

### Root Cause (configuration frame)
- Consumers short poll frequently while queues are often empty.
- Batch APIs not used for high-volume send/delete/receive.
- Visibility timeout too low, causing repeated receives.
- DLQ/redrive behavior or application errors inflate request volume.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → request metrics × region pricing →
rule fallback.

Do not assume long polling eliminates all empty receives. Model partial
reduction and report assumptions.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Set `receive_wait_time_seconds = 20` only for flagged queues where client
  timeout/latency constraints are acceptable, or explicitly unknown with a
  review comment.
- Comments explain client-timeout validation and post-change monitoring.
- Do not change visibility timeout, DLQ, or FIFO settings without evidence.

## Preventive Actions

1. Default new queues to long polling unless latency exception is documented.
2. Alert on high empty-receive ratio and message age.
3. Review batching and DLQ metrics monthly.
