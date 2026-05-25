# Scoring & Aggregation Guardrails

## Per-finding rules

1. Every detected domain appears as finding, no-finding, or skipped — never
   silently omitted.
2. Every finding cites Terraform, metrics, and cost evidence (or states what
   is unavailable).
3. Normal/healthy resources are unchanged in `result/main_optimized.tf`.
4. Savings use `avg_monthly_spend_usd` and are within reasonable range of cost
   evidence.
5. Report uses 4-section unified layout — no per-domain or per-agent subsections.
6. Every cascade pattern appears in Root Cause with a full attribution chain.
7. Scenario IDs, `_fusion_components`, filenames, and hint text are never
   finding evidence. They may define the recall denominator or inspection
   target only.

## Coverage rules

- Multi-domain mode: subagents use inline slices only; standalone mode reads full files.
- Use `avg_monthly_spend_usd` for monthly figures. Label period totals as `<N>-month total`.
- Mark missing facts as `Not available in the provided data; verify in the real environment`.
- Preserve decoy/healthy resources in `result/main_optimized.tf`.
- Attribute cost to workload behavior. When NAT/transfer/orchestration cost is
  high, trace to the originating caller before recommending a fix.
- For compute → storage/API workloads, check request amplification and cache
  evidence before accepting service-local fixes such as memory rightsizing or
  lifecycle transitions.
- Prefer configuration fixes over deletion for lifecycle, retention, polling,
  rightsizing, or routing waste.
- For NAT waste: Gateway Endpoint (free) → Interface Endpoint → right-sizing.

## Recall denominator

`_fusion_components` count from `cost_report.json`, or total expected patterns
from scenario metadata. Write `Not measured` for unobservable metrics.

## Aggregation steps

1. Ensure `<WORK_DIR>/result` exists.
2. Merge domain findings into `result/finops_report.md` per `report-template.md`.
3. Merge optimized TF fragments into `result/main_optimized.tf` (preserve all
   unchanged resources from every domain).
4. Retry MCP pricing for any domain that skipped it; record discrepancy if MCP
   price differs from scenario `pricing_note`.
