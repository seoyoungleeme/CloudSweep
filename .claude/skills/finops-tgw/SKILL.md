---
name: finops-tgw
description: >
  FinOps Transit Gateway Analysis Skill. Detects avoidable Transit Gateway
  data processing charges and attachment costs by identifying VPC-to-VPC
  traffic patterns that could be served more cheaply by VPC Peering,
  over-engineered hub-spoke topologies for simple connectivity, and
  cross-AZ routing overhead.
user_invocable: false
---

# FinOps Transit Gateway Analysis Skill

## Scope

Analyze AWS Transit Gateway cost from a FinOps perspective. The goal is to
reduce avoidable data processing and attachment charges without breaking
network connectivity, security segmentation, routing policy, or multi-account
architecture requirements.

Important safety rule:

Do not recommend replacing Transit Gateway with VPC Peering without confirming
the routing topology. TGW is required for hub-spoke multi-account architectures,
transitive routing, centralized inspection (Network Firewall, third-party
appliances), and SD-WAN/Direct Connect integration. VPC Peering does not support
transitive routing and requires a separate peering connection per VPC pair.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_ec2_transit_gateway`, `aws_ec2_transit_gateway_vpc_attachment`, `aws_vpc_peering_connection`, route tables, and related networking resources | Cannot analyze; ask user for path |
| `metrics.json` | TGW bytes processed, packet count per attachment, cross-AZ traffic, and flow direction evidence | Mark metrics section as unavailable |
| `cost_report.json` | Monthly TGW attachment, TGW data processing, VPC, and data transfer cost history | Mark cost section as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read the input files and apply detection rules from
`rules/tgw_rightsizing.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| T1 | TGW data processing charges exist for same-region VPC-to-VPC traffic that could use VPC Peering (especially same-AZ, which is free) | HIGH | REPLACE_TGW_WITH_VPC_PEERING |
| T2 | TGW has <= 3 VPC attachments for simple point-to-point connectivity with no transitive routing, multi-account, or inspection requirement | MEDIUM | EVALUATE_VPC_PEERING_REPLACEMENT |
| T3 | TGW attachment charge persists for attachments with no or minimal traffic | MEDIUM | REVIEW_IDLE_ATTACHMENT |
| T4 | Traffic routed cross-AZ through TGW when same-AZ TGW or peering path exists | MEDIUM | REVIEW_AZ_LOCAL_ROUTING |

### Required Safety Checks

Before recommending TGW to VPC Peering migration:

- Confirm topology is simple point-to-point (not hub-spoke, not transitive).
- Confirm no centralized inspection appliance (Network Firewall, third-party
  IDS/IPS) relies on TGW routing.
- Confirm no Direct Connect or VPN attachment shares the TGW.
- Confirm no multi-account routing depends on TGW.
- VPC Peering requires one peering connection per VPC pair; confirm the number
  of pairs is manageable (<= 10 pairs is generally acceptable).
- Confirm security groups and NACLs allow traffic over the peering connection.

Before removing TGW attachments:

- Confirm no active traffic flows through the attachment.
- Confirm no route table references the attachment.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure Evidence

- TGW count, description, route table settings, and DNS support.
- VPC attachment count, VPC pairs, and inferred topology (hub-spoke vs. mesh).
- Existing VPC Peering connections, same_region flag, monthly data volume.
- Route table associations and propagation settings.

### 3.2 Metric Evidence

- TGW bytes processed per hour and total monthly volume.
- Packet count and traffic stability.
- Cross-AZ traffic evidence when available.
- Whether traffic pattern is consistent enough to commit to architectural change.

### 3.3 Cost Evidence

- Monthly TGW attachment charges vs. data processing charges.
- VPC and data transfer line items.
- Pricing note savings model when available.

### 3.4 Root Cause

Frame root cause as architecture or over-engineering:

- TGW was deployed for future scalability but current topology is simple
  point-to-point and could use VPC Peering.
- TGW data processing charges accumulate on high-volume same-region traffic
  that is free over VPC Peering within the same AZ.
- Attachment charges persist for attachments with no active routing need.

## Savings Calculation

Prefer this order of evidence:

1. Use explicit savings from `cost_report.json` pricing_note (authoritative).
2. Use TGW data processing bytes x $0.02/GB from metrics.
3. Use TGW attachment count x $0.05/hr x 720 hr/mo for attachment savings if
   removal is confirmed safe.
4. Use static fallback prices in the rule file only as estimates.

TGW pricing (us-east-1):
- Attachment charge: $0.05/attachment-hour
- Data processing: $0.02/GB

VPC Peering pricing (us-east-1):
- Same-AZ: free
- Cross-AZ: $0.01/GB per direction ($0.02/GB round-trip)
- Cross-region: varies by region pair

Do not count attachment savings unless removal is confirmed safe (no active
routes, no other dependencies on the TGW).

## Step 4 - Optimized Terraform

Create `WORK_DIR/main_optimized.tf` from the actual `main.tf` content when a
Terraform change is appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resource names.
- For T1/T2 (replace with VPC Peering): show the desired end state with
  `aws_vpc_peering_connection` as primary path and TGW as REVIEW target.
  Include tags for the peering connection.
- For T3 (idle attachment): mark attachment for review with a comment;
  do not remove without explicit confirmation.
- Add comments explaining topology assumptions, safety checks, and rollback plan.
- For TGW removal, provide an operational plan (multi-step, not one Terraform
  apply) since route table changes must precede attachment deletion.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps Transit Gateway Analysis Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Avoidable TGW data processing or attachment charges |
| Affected Resources | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure
<TGW, attachments, VPC pairs, existing peering, route tables>

### Metrics
<bytes processed, traffic volume, AZ distribution, traffic stability>

### Cost Report
<TGW attachment, data processing, VPC, transfer cost assumptions>

## Root Cause
<architecture or routing governance cause>

## Proposed Solution

### Immediate Actions
1. Validate topology: confirm no transitive routing, inspection, or multi-account dependency.
2. Route high-volume VPC-to-VPC traffic through VPC Peering.
3. Monitor TGW attachment traffic for 7 days before detaching.

### Preventive Actions
1. Default to VPC Peering for <= 10 VPC pairs in a single account.
2. Require TGW justification (transitive routing, inspection, Direct Connect)
   for any new Transit Gateway deployment.
3. Alert on TGW data processing cost > $50/month without documented need.

## Estimated Monthly Savings
$XX.XX with assumptions and confidence.

## Optimized Terraform / Operational Plan
<real resource-based plan>
```

## Scoring Guardrails

- Always treat existing `aws_vpc_peering_connection` resources as potential
  compliant/decoy resources. Preserve them unless the provided files explicitly
  flag them as problematic.
- Do not delete TGW resources in one Terraform step. Show a migration end state
  and an operational cutover plan: create/validate peering routes, shift traffic,
  monitor, then detach TGW attachments.
- Use `cost_report.json` pricing_note as the preferred savings source when it
  gives a scenario-specific TGW data processing figure. If monthly service spend
  appears lower than the pricing note, state the inconsistency and keep the
  pricing-note estimate as scenario-provided evidence.
- Include unit economics for L3 scenarios: cost per GB, cost per order, and
  cost per 1k requests where business metrics are present.
- Always produce both `finops_report.md` and `main_optimized.tf`.

Generated by: finops-tgw skill v1.1.0
