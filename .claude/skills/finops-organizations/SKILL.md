---
name: finops-organizations
description: >
  FinOps Organizations Analysis Skill. Detects missed consolidated billing,
  Reserved Instance and Savings Plans sharing, account fragmentation, and
  commitment planning opportunities using Terraform, account inventory, RI/SP
  coverage data, and AWS cost reports.
user_invocable: false
---

# FinOps Organizations Analysis Skill

## Scope

Analyze AWS Organizations and billing architecture from a FinOps perspective.
The goal is to improve discount sharing, volume discount aggregation, commitment
planning, cost visibility, and governance without crossing legal, security,
commercial, or chargeback boundaries.

Important safety rule:

Do not recommend consolidating accounts or enabling RI/SP sharing solely from
spend data. Confirm organization membership, payer/management account design,
sharing preferences, Billing Conductor or billing transfer use, legal entity
constraints, chargeback requirements, and account ownership first.

## Step 1 - Locate Input Files

Recursively scan `WORK_DIR` and list every available file before analysis.

| File | Description | If Missing |
|------|-------------|------------|
| `main.tf` | Terraform `aws_organizations_organization`, accounts, OUs, billing/sharing metadata when present | Cannot analyze; ask user for path |
| `metrics.json` | Account spend, RI/SP coverage, utilization, sharing preferences, discount leakage, and account mapping | Mark metrics section as unavailable |
| `cost_report.json` | Monthly cost history, pricing notes, commitment coverage, and payer/account-level data | Mark cost section as unavailable |
| `ri_sp_coverage.json` | Optional RI/SP coverage, utilization, recommendations, and commitment scenarios | Mark RI/SP detail as unavailable |

Base every conclusion on provided files. If a fact is not present, write:
`Not available in the provided data; verify in the real environment.`

## Step 2 - Analyze Evidence

Read the input files and apply detection rules from
`rules/consolidated_billing.json`.

### Detection Rules

| Rule | Condition | Severity | Action |
|------|-----------|----------|--------|
| O1 | Accounts are outside consolidated billing or sharing family and discount leakage is evidenced | HIGH | REVIEW_CONSOLIDATED_BILLING |
| O2 | RI/SP sharing disabled or scoped in a way that causes unused commitments and on-demand leakage | HIGH | REVIEW_DISCOUNT_SHARING |
| O3 | Coverage is low but utilization and workload stability support a commitment plan | MEDIUM | MODEL_RI_SP_PURCHASE |
| O4 | Utilization is low or commitments are stranded | MEDIUM | REALIGN_COMMITMENTS |
| O5 | Cost allocation, tags, OU/account mapping, or chargeback data is insufficient | MEDIUM | IMPROVE_COST_GOVERNANCE |

### Required Safety Checks

Before recommending billing consolidation or sharing changes:

- Confirm the accounts belong to the same legal/commercial billing scope.
- Confirm RI/SP sharing preferences at the management account and account level.
- Confirm Billing Conductor, billing transfer, or custom chargeback does not
  intentionally isolate charges.
- Confirm commitment type, region, instance family, tenancy, OS, and engine
  eligibility where applicable.
- Confirm shared discounts will not break team chargeback/showback agreements.

## Step 3 - Deep Architectural Analysis

Cover these sections in the final report:

### 3.1 Infrastructure and Account Evidence

- Organization, OU, account, payer, and management account evidence.
- Consolidated billing status and discount sharing preferences when present.
- Account ownership, cost center, environment, and workload mapping.

### 3.2 RI/SP Coverage Evidence

- On-demand percentage, RI/SP coverage, utilization, effective savings rate,
  unused commitments, and stranded discounts.
- Distinguish coverage opportunity from utilization waste.

### 3.3 Cost Evidence

- Monthly spend trend by account or payer when available.
- Service mix and commitment-eligible spend.
- Any pricing notes or recommendation scenarios.

### 3.4 Root Cause

Frame root cause as governance or purchasing architecture:

- Accounts are fragmented across billing families.
- Discount sharing preferences block otherwise eligible RI/SP coverage.
- Commitments are purchased locally without centralized planning.
- Cost allocation data is insufficient for central commitment planning.

## Savings Calculation

Prefer this order of evidence:

1. Use explicit savings estimates in `cost_report.json` or `ri_sp_coverage.json`.
2. Use eligible on-demand spend times a documented modeled savings percentage.
3. Treat any static or Terraform-provided savings percentage as potential until
   commitment eligibility and sharing preferences are verified.

Do not count savings from new RI/SP purchases unless utilization, term, payment
option, service eligibility, and risk tolerance are modeled.

If RI/SP eligibility for a specific service, engine, or region is unclear from
the provided data, call `aws-docs` to verify before including it in the savings
estimate. Do not call aws-docs when eligibility is already confirmed by
cost_report or ri_sp_coverage data.

## Step 4 - Optimized Terraform or Operational Plan

Create `WORK_DIR/main_optimized.tf` or an operational plan when appropriate.

Rules:

- Do not use placeholders such as `<resource-name>`.
- Preserve real resources and account names.
- Do not move accounts, change sharing preferences, or create commitments in
  Terraform unless the provided files include enough evidence.
- Prefer an operational plan for billing architecture changes: validate
  accounts, update sharing preferences, run commitment analysis, then implement.
- Add comments explaining assumptions and verification steps.

## Step 5 - Write Final Report

Save `WORK_DIR/finops_report.md` and include the report in the response.

Report format:

```markdown
# FinOps Organizations Analysis Skill Report - <Scenario ID>

## Problem Identification
| Category | Details |
|----------|---------|
| Waste Type | Missed consolidated billing, RI/SP sharing, or commitment planning savings |
| Affected Accounts | X of Y |
| Monthly Waste | $XX potential/confirmed |
| Confidence | High/Medium/Low with reason |

## Evidence

### Infrastructure and Accounts
<organization, account, payer, sharing, and governance evidence>

### RI/SP Coverage
<coverage, utilization, on-demand leakage, stranded commitment evidence>

### Cost Report
<monthly spend and savings assumptions>

## Root Cause
<billing governance cause>

## Proposed Solution

### Immediate Actions
1. Validate account scope and sharing preferences.
2. Model RI/SP sharing and commitment scenarios before changes.

### Preventive Actions
1. Centralize commitment planning.
2. Enforce account cost ownership and allocation tags.
3. Review coverage and utilization monthly.

## Estimated Monthly Savings
$XX.XX with assumptions and confidence.

## Optimized Terraform / Operational Plan
<real resource-based plan>
```

Generated by: finops-organizations skill
