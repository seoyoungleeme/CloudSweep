# finops-tgw — Detailed Rules

## Required Safety Checks

### Before recommending TGW → VPC Peering migration
- Topology is simple point-to-point (not hub-spoke, not transitive).
- No centralized inspection appliance (Network Firewall, third-party IDS/IPS)
  relies on TGW routing.
- No Direct Connect or VPN attachment shares the TGW.
- No multi-account routing depends on TGW.
- Number of VPC pairs is manageable (<= 10 generally acceptable).
- Security groups and NACLs allow traffic over the peering connection.

### Before removing TGW attachments
- No active traffic flows through the attachment.
- No route table references the attachment.

## Deep Architectural Analysis

### Infrastructure
- TGW count, description, route table settings, DNS support.
- VPC attachment count, VPC pairs, inferred topology (hub-spoke vs mesh).
- Existing VPC Peering connections, same_region flag, monthly data volume.
- Route table associations and propagation settings.

### Metrics
- TGW bytes processed per hour and monthly total.
- Packet count and traffic stability.
- Cross-AZ traffic evidence.
- Whether traffic pattern is stable enough to commit to architectural change.

### Cost
- Monthly TGW attachment vs data processing charges.
- VPC and data transfer line items.
- Pricing-note savings model when available.

### Root Cause (over-engineering frame)
- TGW deployed for future scalability but current topology is simple
  point-to-point — VPC Peering would suffice.
- TGW data processing accumulates on high-volume same-region traffic that is
  free over VPC Peering within the same AZ.
- Attachment charges persist for attachments with no active routing need.

## Savings Calculation

Evidence order: explicit `cost_report.json` `pricing_note` (authoritative) →
TGW data processing bytes × $0.02/GB → TGW attachment count × $0.05/hr × 720
hr/mo (if removal confirmed safe) → rule fallback.

### TGW pricing (us-east-1)
- Attachment charge: $0.05/attachment-hour.
- Data processing: $0.02/GB.

### VPC Peering pricing (us-east-1)
- Same-AZ: free.
- Cross-AZ: $0.01/GB per direction ($0.02/GB round-trip).
- Cross-region: varies by region pair.

Do not count attachment savings unless removal is confirmed safe (no active
routes, no other TGW dependencies).

## Optimized Terraform Rules

- No placeholders; preserve real resource names.
- For T1/T2 (replace with VPC Peering): show desired end state with
  `aws_vpc_peering_connection` as primary path; TGW as REVIEW target. Include
  tags for the peering connection.
- For T3 (idle attachment): mark for review with a comment; do not remove
  without explicit confirmation.
- Comments explain topology assumptions, safety checks, rollback plan.
- TGW removal: provide an operational plan (multi-step, not one `terraform apply`)
  since route table changes must precede attachment deletion.

## Scoring Guardrails

- Treat existing `aws_vpc_peering_connection` resources as potential compliant
  / decoy. Preserve them unless inputs explicitly flag them as problematic.
- Do not delete TGW resources in one Terraform step. Show migration end state +
  operational cutover plan: create/validate peering routes, shift traffic,
  monitor, then detach TGW attachments.
- Use `cost_report.json` pricing_note as preferred savings source when it gives
  a scenario-specific TGW data processing figure. If monthly service spend
  appears lower than pricing_note, state the inconsistency and keep the
  pricing-note estimate as scenario-provided evidence.
- Include unit economics for L3 scenarios: cost per GB, cost per order, cost
  per 1k requests where business metrics are present.
- Always produce both `finops_report.md` and `main_optimized.tf`.

## Preventive Actions

1. Default to VPC Peering for <= 10 VPC pairs in a single account.
2. Require TGW justification (transitive routing, inspection, Direct Connect)
   for any new Transit Gateway deployment.
3. Alert on TGW data processing cost > $50/month without documented need.
