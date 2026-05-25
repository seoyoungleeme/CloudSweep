# Cross-Service Playbooks

Detailed templates and queries for cross-service remediations. Referenced from
`finops/SKILL.md` Cascade Patterns section and report Section 3 Proposed Solution.

---

## Cost Formulas

**NAT / VPC Endpoint** (apply when `aws_nat_gateway` + private-subnet compute exist):
```
avoidable_nat_gb_cost = S3_DynamoDB_GB_via_NAT × $0.045/GB   (Gateway Endpoint → $0)
avoidable_data_xfer   = cross_AZ_GB × $0.01/GB               (if applicable)
removable_nat_hours   = NAT_count × $0.045/hr × 730           (only if NAT can be deleted)
endpoint_cost         = AZ_count × $0.01/hr × 730 + GB × $0.01/GB  (Interface Endpoint)
```
Flag HIGH when private traffic to S3/DynamoDB routes through NAT with no Gateway Endpoint.

**Step Functions**:
```
sfn_standard   = max(transitions - 4000, 0) × $0.000025
sfn_express    = executions × $1.00/1_000_000
               + executions × avg_sec × billed_GB × $0.00001667
```
Express billed_GB rounds up to nearest 64 MB. No Express free tier unless in scenario data.

**CloudFront** (US/Canada/Europe defaults):
```
viewer_egress  = first 1 TB/month free; next 9 TB × $0.085/GB
http_requests  = $0.0075 / 10,000 ; https_requests = $0.0100 / 10,000
origin_fetch   = free for same-region S3/ALB
```
Primary savings lever: raise cache hit ratio → fewer origin requests/compute.

---

## Compute → Storage/API Request Amplification

Use this playbook when a compute service appears individually healthy, a
downstream storage/API service appears individually explainable, but the
combined workload spends money on repeated reads, polling, or dependency calls.
Do not trigger this from a scenario ID or assignment title; use evidence.

### Required Signals

Look for at least two of these signals:
- compute `Invocations` or request count co-moves with downstream GET/read/API
  request count
- `downstream_requests_per_invocation` is repeatedly high or rising
- storage/API request cost is material even when storage/capacity utilization
  is not the main driver
- no cache layer is visible in Terraform or metrics
- compute duration p95/p99 increases with downstream request rate

If invocation or cache-hit metrics are missing, classify the finding as
`Suspected request amplification` and recommend instrumentation before a
destructive or service-local change.

### Attribution Formula

```text
downstream_requests_per_invocation =
  downstream_request_count / compute_invocation_count

avoidable_request_cost =
  avoidable_downstream_requests × request_price_per_request

avoidable_compute_cost =
  compute_invocations × avoidable_dependency_ms / 1000
  × allocated_memory_gb × compute_price_per_gb_second

net_savings =
  avoidable_request_cost + avoidable_compute_cost - cache_operating_cost
```

Use scenario `cost_report` first when it gives authoritative request savings.
Otherwise use AWS Pricing MCP, then static fallback pricing with `[estimate]`.

### Remediation Patterns

Choose the smallest cache that matches consistency and sharing needs:
- Lambda execution-context in-memory TTL cache for small, read-mostly objects
  that can be reused across warm invocations.
- Lambda extension or sidecar cache when multiple handlers need a local cache
  boundary.
- ElastiCache/Redis when cache state must be shared across concurrent compute
  workers or has invalidation requirements.
- CloudFront or API Gateway cache for HTTP/object reads where edge or regional
  caching semantics are acceptable.
- Batch prefetch or request coalescing when many invocations read the same
  object/prefix during a short window.

Post-change metrics:
- cache hit rate
- downstream requests per invocation
- compute duration p95/p99
- downstream request cost and throttling/error rate

---

## VPC Flow Logs + Athena

Use when NAT, data transfer, or network cost is suspicious and route/subnet
evidence alone cannot attribute traffic to a specific caller.

### Athena Table DDL

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS vpc_flow_logs (
  version       int,
  account_id    string,
  interface_id  string,
  srcaddr       string,
  dstaddr       string,
  srcport       int,
  dstport       int,
  protocol      bigint,
  packets       bigint,
  bytes         bigint,
  start         bigint,
  `end`         bigint,
  action        string,
  log_status    string
)
PARTITIONED BY (year string, month string, day string)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ' '
STORED AS TEXTFILE
LOCATION 's3://<flow-log-bucket>/AWSLogs/<account-id>/vpcflowlogs/<region>/';
```

### Top-Talker Query

```sql
-- Identify unexpected AWS-service traffic through NAT
SELECT srcaddr, dstaddr, dstport,
       sum(bytes)   AS total_bytes,
       sum(packets) AS total_packets
FROM vpc_flow_logs
WHERE year = 'YYYY' AND month = 'MM'
GROUP BY srcaddr, dstaddr, dstport
ORDER BY total_bytes DESC
LIMIT 50;
```

Look for:
- High bytes to AWS public IP ranges → should use VPC endpoints
- Cross-AZ traffic → prefer same-AZ endpoint or caching layer
- High packet count with low bytes → polling anti-pattern
- Unexpected external egress → security incident or misconfiguration

### Terraform: Enable Flow Logs

```hcl
resource "aws_flow_log" "vpc" {
  iam_role_arn    = aws_iam_role.flow_log.arn
  log_destination = aws_cloudwatch_log_group.flow_log.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.main.id
}
```

---

## VPC Gateway Endpoint (S3 / DynamoDB)

Use when private-subnet compute sends S3 or DynamoDB traffic through NAT.
Gateway Endpoints are free — no hourly or per-GB charge.

```hcl
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}
```

Savings: `S3_DynamoDB_GB_via_NAT × $0.045/GB` immediately.
NAT hourly savings: only if NAT can be fully deleted after all traffic migrates.

---

## SFN Callback Pattern (replace polling)

Replace Wait-state polling loop with `.waitForTaskToken` to eliminate polling transitions.

**Before (polling — expensive):**
```json
"WaitForJob": {
  "Type": "Wait",
  "Seconds": 30,
  "Next": "CheckJobStatus"
}
```

**After (callback — zero polling transitions):**
```json
"WaitForJob": {
  "Type": "Task",
  "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
  "Parameters": {
    "QueueUrl": "<queue-url>",
    "MessageBody": { "TaskToken.$": "$$.Task.Token" }
  },
  "Next": "JobComplete"
}
```

Savings: `executions/month × avg_poll_transitions × $0.000025`

---

## CloudFront Cache Tuning

Use when `CacheHitRate` < 80%.

```hcl
resource "aws_cloudfront_cache_policy" "optimized" {
  name        = "optimized-cache-policy"
  default_ttl = 86400
  max_ttl     = 31536000
  min_ttl     = 1

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config  { cookie_behavior = "none" }
    headers_config  { header_behavior = "none" }
    query_strings_config { query_string_behavior = "none" }
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
  }
}
```

After cache hit ratio improves, savings come primarily from:
- Fewer origin Lambda invocations / ALB requests
- Fewer S3 GET requests
- Reduced origin compute cost

Not from viewer egress spread (direct $0.09/GB vs CF $0.085/GB is minimal).

---

## Cost Anomaly Detection

Use for any recurring spike pattern detected in `cost_report.json`.

```hcl
resource "aws_ce_anomaly_monitor" "service" {
  name              = "service-anomaly-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "alert" {
  name      = "service-anomaly-alert"
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.service.arn]

  subscriber {
    type    = "SNS"
    address = aws_sns_topic.cost_alerts.arn
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_PERCENTAGE"
      values        = ["20"]
      match_options = ["GREATER_THAN_OR_EQUAL"]
    }
  }
}
```

### Spike Incident Playbook

| Spike type | First action | Root cause signal | Resolution |
|------------|-------------|-------------------|------------|
| Normal growth | Verify trend vs. traffic | Monotonic increase matches user growth | No action or capacity plan |
| Release-driven | Check deploy timestamp | Spike starts at deploy time | Rollback or config fix |
| Misconfiguration | Check infra changes | Sudden step function in cost | Identify changed resource |
| Retry loop | Check error metrics | Lambda/ECS errors + downstream surge | Fix error handling / circuit breaker |
| Security incident | Check CloudTrail | Unexpected API calls or egress | Isolate, rotate credentials |
