# finops-elb — Detailed Rules

## Required Deletion Checks

Before reporting confirmed savings or generating deletion Terraform:
- No Route 53, CNAME, CloudFront origin, API Gateway VPC link, PrivateLink,
  service discovery, or external DNS points to the LB.
- Listeners, listener rules, target groups, certificates, WAF, access logs,
  security groups, and dependencies are safe to remove.
- Target groups have no healthy production targets or active rollout role.
- LB is not part of blue/green, canary, DR, migration, private/internal, or
  maintenance traffic paths.
- Require owner approval before destructive cleanup.

If dependency evidence is missing, mark savings as potential.

## Deep Architectural Analysis

### Infrastructure Evidence
- Total `aws_lb` count and type: application, network, gateway, or classic.
- Scheme: internet-facing or internal.
- Listeners, listener rules, target groups, healthy target evidence, DNS records,
  certificates, WAF associations, deletion protection, access logs, security
  groups, tags.

### Metric Evidence
LB-type-appropriate metrics:
- ALB: `RequestCount`, `ActiveConnectionCount`, `NewConnectionCount`,
  `ProcessedBytes`, `ConsumedLCUs`, target response, healthy hosts.
- NLB: active/new flows, processed bytes, `ConsumedLCUs`/NLCU, TCP/TLS/UDP,
  healthy hosts.
- CLB: request count, latency, backend connection errors, healthy hosts.

Prefer sum/min/max over average for zero-traffic detection. Average of zero is
not enough if datapoints are missing.

### Cost Evidence
- Monthly ELB spend trend.
- Fixed LB-hour vs variable LCU/NLCU/GLCU.
- Region-specific pricing — prefer cost report or aws-pricing MCP.
- Related costs that may remain after deletion: data transfer, WAF, NAT, logs,
  target compute.

### Root Cause (frame as governance)
- Environment teardown left LB behind.
- DNS/listener migration incomplete.
- Test/preview environments lack TTL cleanup.
- Ownership tags missing.

## Savings Calculation

Evidence order: cost_report → aws-pricing MCP → rule fallback (estimate).

```
monthly_fixed_cost = lb_hourly_price * hours_per_month
monthly_lcu_cost   = observed_lcu_hours * lcu_hourly_price
monthly_savings    = monthly_fixed_cost + removable_lcu_cost
```

For truly idle ALBs, LCU cost may be zero while fixed hourly remains. Do not
count downstream target, transfer, WAF, or logging savings unless the
remediation removes those costs.

## Optimized Terraform Rules

- No placeholders (`<resource-name>` etc.).
- Preserve real resource names and unchanged resources.
- For deletion candidates, comment the LB and dependent resources with
  verification steps. Do not silently delete when dependency evidence is incomplete.
- Preserve active load balancers.
- Add/preserve deletion protection and required tags for retained production
  or shared LBs.
- Include cleanup order: DNS → traffic drain → listener/target group validation
  → LB deletion → SG cleanup.
