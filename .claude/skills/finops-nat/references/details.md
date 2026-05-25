# finops-nat — Detailed Rules

## Required Safety Checks

### Before adding endpoints
- Endpoint service region matches provider/workload region.
- Route tables for all intended private subnets are associated.
- Endpoint policy allows required buckets/tables/actions.
- For interface endpoints: private DNS, security groups, subnet/AZ placement,
  hourly cost, per-GB cost modeled.

### Before removing NAT
- No internet or unsupported-service egress remains.
- No third-party/SaaS/package repo/OS update dependency remains.
- All private subnet route tables have correct endpoint or alternative routes.
- HA requirements and per-AZ routing preserved.

## Deep Architectural Analysis

### Infrastructure
- NAT gateway count, AZ placement, subnet mapping, route tables, default routes.
- Existing gateway endpoints for S3/DynamoDB and their route table associations.
- Existing interface endpoints, subnet/AZ placement, private DNS, endpoint
  policies, security groups.
- Tags: Owner, Environment, Purpose, CostCenter, Application.

### Metric and Flow Evidence
- NAT bytes processed by gateway and by AZ/subnet.
- Destination service mix: S3, DynamoDB, ECR, CloudWatch Logs, STS, Secrets
  Manager, SSM, third-party internet, unknown.
- Cross-AZ NAT usage and data transfer evidence.
- Endpoint traffic after migration when provided.

If destination service mix is unavailable, recommend enabling VPC Flow Logs or
CUR usage analysis before large architecture changes.

### Cost
- Monthly NAT gateway hourly cost and NAT data processing cost.
- Data transfer cost, especially cross-AZ or internet egress.
- Gateway endpoint cost (S3/DynamoDB: no additional endpoint hourly) and
  interface endpoint hourly/per-GB cost.
- Region pricing — prefer cost report or aws-pricing MCP.

### Root Cause (governance frame)
- Private subnets route AWS service traffic through NAT by default.
- S3/DynamoDB gateway endpoint route table associations missing.
- Interface endpoints not modeled against NAT data processing volume.
- NAT gateways centralized across AZs, causing cross-AZ transfer.
- NAT gateway remained after workload egress requirements changed.

## Savings Calculation

Evidence order: `cost_report.json` / CUR → destination service bytes from VPC
Flow Logs or metrics → rule fallback.

```
nat_data_processing_savings = offloadable_gb * nat_gateway_per_gb_price
nat_hourly_savings          = removable_nat_gateway_count * nat_gateway_hourly_price * hours_per_month
interface_endpoint_net_savings = avoided_nat_processing_cost - endpoint_hourly_cost - endpoint_data_processing_cost
```

Do not count NAT hourly savings unless all egress through that NAT gateway is
no longer needed or replaced safely.

## Optimized Terraform Rules

- No placeholders; preserve real resource names and unchanged resources.
- Add S3/DynamoDB gateway endpoints and route table associations based on real route tables.
- Add interface endpoints only when cost modeling supports them.
- Preserve NAT gateways unless evidence supports removal.
- Add endpoint policies and tags where appropriate.
- Comments explain route impact, validation, and rollback.

## Preventive Actions

1. Require S3/DynamoDB gateway endpoints in private-subnet VPC modules.
2. Review NAT destination mix monthly.
3. Alert on cross-AZ NAT routing and high NAT data processing cost.
