---
name: finops-elb
description: >
  FinOps ELB Analysis Skill. Detects idle or potentially unused AWS load
  balancers using Terraform, CloudWatch metrics, DNS/listener/target evidence,
  and AWS cost reports. Supports ALB-focused analysis and flags when NLB/CLB
  metrics need separate treatment.
user_invocable: false
---

# FinOps ELB Analysis Skill

## Scope

Analyze Elastic Load Balancing cost from a FinOps perspective. The goal is to
remove truly idle load balancers and related fixed costs without breaking DNS,
TLS, routing, WAF, private connectivity, health checks, or blue/green rollout
paths.

Important safety rule:

Do not recommend immediate load balancer deletion based only on average request
or connection metrics. Require a full observation window with zero traffic and
dependency checks for DNS, listeners, target groups, certificates, WAF, access
logs, security groups, and deployment workflows.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_lb`, listeners, listener rules, target groups, DNS records, security groups, WAF associations, certificates, and tags | Cannot analyze; ask user for path |
| `metrics.json` | ELB CloudWatch metrics such as request count, active/new connections, processed bytes, LCU, healthy hosts, and target responses | Mark metrics section as unavailable |
| `cost_report.json` | Monthly ELB cost history, fixed hours, LCU/NLCU/GLCU, and pricing notes | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/unused_elb.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| LB1 | Full observation window has zero requests, zero connections, zero processed bytes/LCU, and no target/DNS dependency evidence | HIGH | REVIEW_DELETE |
| LB2 | No requests but connections, healthy hosts, DNS, or listener dependencies exist | MEDIUM | INVESTIGATE |
| LB3 | Low traffic but nonzero LCU or processed bytes | LOW | OPTIMIZE_OR_SHARE |
| LB4 | Load balancer has no owner/environment/purpose tags | MEDIUM | ADD_GOVERNANCE_TAGS |
| LB5 | Deletion protection enabled or deployment/DR role identified | INFO | DO_NOT_DELETE_WITHOUT_OWNER |

### Required Deletion Checks

Before reporting confirmed savings or generating deletion Terraform:

- Verify no Route 53, CNAME, CloudFront origin, API Gateway VPC link, PrivateLink,
  service discovery, or external DNS points to the load balancer.
- Verify listeners, listener rules, target groups, certificates, WAF, access
  logs, security groups, and dependencies are safe to remove.
- Verify target groups have no healthy production targets or active rollout
  role.
- Verify the load balancer is not part of blue/green, canary, disaster recovery,
  migration, private/internal, or maintenance traffic paths.
- Require owner approval before destructive cleanup.

If dependency evidence is missing, mark savings as potential.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- Total `aws_lb` count and type: application, network, gateway, or classic when
  available.
- Scheme: internet-facing or internal.
- Listeners, listener rules, target groups, healthy target evidence, DNS records,
  certificates, WAF associations, deletion protection, access logs, security
  groups, and tags.

### 3.2 Metric Evidence

Use load balancer type appropriate metrics:

- ALB: `RequestCount`, `ActiveConnectionCount`, `NewConnectionCount`,
  `ProcessedBytes`, `ConsumedLCUs`, target response metrics, healthy hosts.
- NLB: active/new flows, processed bytes, `ConsumedLCUs` or NLCU-related usage,
  TCP/TLS/UDP metrics, healthy hosts.
- CLB: request count, latency, backend connection errors, healthy hosts.

Prefer sum/min/max over average for zero-traffic detection. An average of zero
is not enough if datapoints are missing.

### 3.3 Cost Evidence

- Monthly ELB spend trend.
- Fixed load balancer-hour cost and variable LCU/NLCU/GLCU cost.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.
- Related costs that may remain after deletion, such as data transfer, WAF,
  NAT, logs, or target compute.

### 3.4 Root Cause

Frame root cause as lifecycle or architecture governance:

- Environment teardown left the load balancer behind.
- DNS or listener migration was incomplete.
- Test/preview environments lack TTL-based cleanup.
- Ownership tags are missing, preventing safe cleanup.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like ELB line items.
2. Use region-specific pricing from AWS Pricing MCP/API when available.
3. Use static fallback prices in the rule file only as estimates.

Formula:

```text
monthly_fixed_cost = lb_hourly_price * hours_per_month
monthly_lcu_cost = observed_lcu_hours * lcu_hourly_price
monthly_savings = monthly_fixed_cost + removable_lcu_cost
```

For truly idle ALBs, LCU cost may be zero while fixed hourly cost remains. Do
not count downstream target, data transfer, WAF, or logging savings unless the
remediation explicitly removes those costs.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- For deletion candidates, comment the load balancer and dependent resources
  with verification steps. Do not silently delete resources when dependency
  evidence is incomplete.
- Preserve active load balancers.
- Add or preserve deletion protection and required tags for retained production
  or shared load balancers.
- Include a cleanup order: DNS, traffic drain, listener/target group validation,
  load balancer deletion, security group cleanup.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps ELB Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Idle or potentially unused load balancers |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<LB type, listeners, target groups, DNS, WAF, certificates, tags>

### Metrics
<request, connection, bytes, LCU, healthy host evidence>

### Cost Report
<fixed and variable cost assumptions>

## Root Cause
<architecture or lifecycle cause>

## Proposed Solution

### Immediate Actions
1. Verify dependencies and owner approval.
2. Drain traffic and remove DNS safely.
3. Delete only confirmed idle load balancers and dependent resources.

### Preventive Actions
1. Enforce owner/environment/purpose tags.
2. Add teardown automation for ephemeral environments.
3. Alert on sustained zero traffic and missing ownership.

## Estimated Monthly Savings
$XX.XX, separated into fixed LB-hour and LCU savings.

## Optimized Terraform
<real resource-based optimized Terraform or cleanup plan>
```

Generated by: finops-elb skill
