# finops-organizations — Detailed Rules

## Required Safety Checks

Before recommending billing consolidation or sharing changes:
- Accounts belong to the same legal/commercial billing scope.
- RI/SP sharing preferences at the management account and account level.
- Billing Conductor, billing transfer, or custom chargeback isn't intentionally
  isolating charges.
- Commitment type, region, instance family, tenancy, OS, engine eligibility.
- Shared discounts won't break team chargeback/showback agreements.

## Deep Architectural Analysis

### Infrastructure and Account Evidence
- Organization, OU, account, payer, management account evidence.
- Consolidated billing status and discount sharing preferences.
- Account ownership, cost center, environment, workload mapping.

### RI/SP Coverage Evidence
- On-demand %, RI/SP coverage, utilization, effective savings rate, unused
  commitments, stranded discounts.
- Distinguish coverage opportunity from utilization waste.

### Cost
- Monthly spend trend by account or payer.
- Service mix and commitment-eligible spend.
- Pricing notes / recommendation scenarios.

### Root Cause (governance frame)
- Accounts fragmented across billing families.
- Discount sharing preferences block otherwise eligible RI/SP coverage.
- Commitments purchased locally without centralized planning.
- Cost allocation insufficient for central commitment planning.

## Savings Calculation

Evidence order: explicit savings in `cost_report.json` / `ri_sp_coverage.json` →
eligible on-demand spend × documented modeled savings % → treat static / TF
percentages as potential.

Do not count new RI/SP purchase savings unless utilization, term, payment
option, service eligibility, and risk tolerance are modeled.

If RI/SP eligibility for a specific service/engine/region is unclear, call
`aws-docs` to verify before including in savings estimate.

## Optimized Terraform / Operational Plan Rules

- No placeholders; preserve real resources and account names.
- Do not move accounts, change sharing preferences, or create commitments in
  Terraform unless inputs include enough evidence.
- Prefer an operational plan: validate accounts → update sharing preferences →
  run commitment analysis → implement.
- Comments explain assumptions and verification steps.

## Preventive Actions

1. Centralize commitment planning.
2. Enforce account cost ownership and allocation tags.
3. Review coverage and utilization monthly.
