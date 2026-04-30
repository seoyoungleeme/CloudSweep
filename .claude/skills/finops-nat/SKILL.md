---
name: finops-nat
description: >
  FinOps NAT Gateway Analysis Skill. Detects avoidable NAT Gateway hourly,
  data processing, and cross-AZ routing cost by identifying traffic that can use
  S3/DynamoDB gateway endpoints, cost-effective interface endpoints, or
  architecture changes.
user_invocable: false
---

# FinOps NAT Gateway Analysis Skill

## Scope

Analyze NAT Gateway cost from a FinOps perspective. The goal is to reduce
avoidable NAT hourly and per-GB data processing charges while preserving
private subnet egress, security policy, route correctness, availability, and
service access.

Important safety rule:

Do not remove NAT gateways just because endpoint candidates exist. Gateway and
interface endpoints can offload AWS service traffic, but workloads may still
need NAT for internet egress, third-party APIs, package repositories, OS
updates, SaaS endpoints, or services without VPC endpoint support.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform NAT gateways, route tables, subnets, VPC endpoints, endpoint route table associations, endpoint policies, security groups, and tags | Cannot analyze; ask user for path |
| `metrics.json` | NAT bytes/packets, source subnet/AZ, destination service mix, VPC Flow Logs summary, endpoint traffic, and route table evidence | Mark metrics section as unavailable |
| `cost_report.json` | Monthly NAT, VPC endpoint, data processing, and data transfer cost history | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read `main.tf`, `metrics.json`, and `cost_report.json`. Apply detection rules
from `rules/s3_nat_bypass.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| N1 | Same-region S3 traffic goes through NAT and no correct S3 gateway endpoint route exists | HIGH | ADD_S3_GATEWAY_ENDPOINT |
| N2 | Same-region DynamoDB traffic goes through NAT and no correct DynamoDB gateway endpoint route exists | HIGH | ADD_DYNAMODB_GATEWAY_ENDPOINT |
| N3 | High-volume AWS service traffic through NAT may be cheaper through interface endpoint after hourly/GB modeling | MEDIUM | MODEL_INTERFACE_ENDPOINT |
| N4 | Cross-AZ private subnet traffic uses NAT in another AZ | MEDIUM | REVIEW_AZ_LOCAL_NAT_OR_ENDPOINTS |
| N5 | NAT gateway hourly cost remains after traffic offload and no internet egress need is evidenced | LOW | REVIEW_NAT_REMOVAL |
| N6 | Endpoint exists but route table association, service region, DNS, policy, or security group is wrong | HIGH | FIX_ENDPOINT_CONFIGURATION |

### Required Safety Checks

Before adding endpoints:

- Confirm endpoint service region matches provider/workload region.
- Confirm route tables for all intended private subnets are associated.
- Confirm endpoint policy allows required buckets/tables/actions.
- For interface endpoints, confirm private DNS, security groups, subnet/AZ
  placement, hourly cost, and per-GB cost are modeled.

Before removing NAT:

- Confirm no internet or unsupported service egress remains.
- Confirm no third-party/SaaS/package repository/OS update dependency remains.
- Confirm all private subnet route tables have correct endpoint or alternative
  routes.
- Confirm HA requirements and per-AZ routing are preserved.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- NAT gateway count, AZ placement, subnet mapping, route tables, and default
  routes.
- Existing gateway endpoints for S3/DynamoDB and their route table associations.
- Existing interface endpoints, subnet/AZ placement, private DNS, endpoint
  policies, and security groups.
- Tags such as Owner, Environment, Purpose, CostCenter, and Application.

### 3.2 Metric and Flow Evidence

- NAT bytes processed by gateway and by AZ/subnet when available.
- Destination service mix: S3, DynamoDB, ECR, CloudWatch Logs, STS, Secrets
  Manager, SSM, third-party internet, and unknown.
- Cross-AZ NAT usage and data transfer evidence.
- Endpoint traffic after migration when provided.

If destination service mix is unavailable, recommend enabling VPC Flow Logs or
CUR usage analysis before large architecture changes.

### 3.3 Cost Evidence

- Monthly NAT gateway hourly cost and NAT data processing cost.
- Data transfer cost, especially cross-AZ or internet egress when available.
- Gateway endpoint cost (normally no additional endpoint hourly charge for
  S3/DynamoDB) and interface endpoint hourly/per-GB cost.
- Region-specific pricing assumptions. Prefer cost report or AWS Pricing MCP
  over static fallback prices.

### 3.4 Root Cause

Frame root cause as architecture or governance, such as:

- Private subnets route AWS service traffic through NAT by default.
- S3/DynamoDB gateway endpoint route table associations are missing.
- Interface endpoints were not modeled against NAT data processing volume.
- NAT gateways are centralized across AZs, causing cross-AZ transfer.
- NAT gateway remained after workload egress requirements changed.

## Savings Calculation

Prefer this order of evidence:

1. Use `cost_report.json` or CUR-like NAT/VPC endpoint line items.
2. Use destination service bytes from VPC Flow Logs or metrics.
3. Use static fallback prices in the rule file only as estimates.

Formula:

```text
nat_data_processing_savings = offloadable_gb * nat_gateway_per_gb_price
nat_hourly_savings = removable_nat_gateway_count * nat_gateway_hourly_price * hours_per_month
interface_endpoint_net_savings = avoided_nat_processing_cost - endpoint_hourly_cost - endpoint_data_processing_cost
```

Do not count NAT hourly savings unless all egress through that NAT gateway is no
longer needed or replaced safely.

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names and unchanged resources.
- Add S3/DynamoDB gateway endpoints and route table associations based on the
  real route tables.
- Add interface endpoints only when cost modeling supports them.
- Preserve NAT gateways unless evidence supports removal.
- Add endpoint policies and tags where appropriate.
- Include comments explaining route impact, validation, and rollback.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps NAT Gateway Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Avoidable NAT Gateway data processing or hourly cost |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<NATs, routes, endpoints, endpoint policies, subnet/AZ placement>

### Metrics and Flow Logs
<NAT bytes, service mix, cross-AZ evidence, endpoint traffic>

### Cost Report
<NAT hourly, NAT data processing, endpoint, and transfer cost assumptions>

## Root Cause
<architecture or route governance cause>

## Proposed Solution

### Immediate Actions
1. Add or fix gateway endpoints for S3/DynamoDB where evidence supports it.
2. Model interface endpoints for high-volume supported AWS services.
3. Preserve NAT until remaining egress is verified.

### Preventive Actions
1. Require S3/DynamoDB gateway endpoints in private-subnet VPC modules.
2. Review NAT destination mix monthly.
3. Alert on cross-AZ NAT routing and high NAT data processing cost.

## Estimated Monthly Savings
$XX.XX, separated into NAT data processing, NAT hourly, and endpoint net savings.

## Optimized Terraform
<real resource-based optimized Terraform or review plan>
```

Generated by: finops-nat skill
