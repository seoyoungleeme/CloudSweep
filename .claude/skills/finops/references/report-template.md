# FinOps Report Template

Use this template when writing `result/finops_report.md`.
Do **not** create per-domain or per-agent subsections — merge all findings into
each section. Use 4-backtick outer fence when embedding this template in a code block.

---

# FinOps Analysis Report
- **Scenario**: <scenario ID and name>
- **Domains analyzed**: <comma-separated list>
- **Run date**: <YYYY-MM-DD>

## Analysis Metrics
| Metric | Value |
|--------|-------|
| Recall | X / Y patterns found |
| Domains analyzed | N |
| Agent count | 1 orchestrator + N domain experts |
| Pricing source | <primary source used> |
| Doc references | <MCP status> |
| Total tokens | Not measured |
| Wall-clock time | Not measured |
| Analysis cost | Not measured |

---

## 1. Problem Identification

| Resource | Service | Waste Type | Coupling | Severity | Monthly Waste |
|----------|---------|------------|----------|----------|---------------|
| ...      | Lambda  | Memory over-allocation | — | HIGH | ~$X/mo |
| ...      | DynamoDB | Capacity over-provisioned | ← Lambda retry loop | HIGH | ~$X/mo |
| ...      | NAT     | AWS-service traffic via NAT | ← ECS private subnet | HIGH | ~$X/mo |

**Coupling column**: `—` for isolated findings. For cascades write the upstream
caller (e.g., `← Lambda retry loop`) or downstream impact (`→ NAT GB charge`).
For cascade findings add a sub-row:
> Workload cost breakdown: compute $X + requests $X + storage/DB $X + network $X + logs $X + orchestration $X = **$X/workload-unit**

For each flagged resource include:
- **Allocated vs observed** — metrics evidence (p99, avg, utilization %)
- **Infrastructure state** — what the Terraform currently says
- **Cost evidence** — cost_report figure or pricing_note (use `avg_monthly_spend_usd`)
- **For request-amplification cascades** — downstream requests per invocation,
  cache evidence, request-cost share, or a clear instrumentation gap.

Mark compliant resources inline (e.g., "✅ No waste detected").

---

## 2. Root Cause

Summarize root causes in a single narrative or bullet list. Group by systemic
pattern (e.g., "initial over-provisioning never revisited" across Lambda + DynamoDB).

For each cross-service cascade, show the attribution chain:
```
surface line item → originating caller behavior → affected downstream services
```

Include:
- Per-workload cost breakdown: `compute + requests + storage_or_db + network + logs + orchestration`
- Spike classification (when anomaly is present): normal growth | release-driven | misconfiguration | retry loop | security incident
- Whether root cause is in the same domain as the billed line item or upstream

---

## 3. Proposed Solution

### Immediate Actions
Numbered list ordered by lowest rollback risk first. Each item:
- Resource name, what changes (before → after)
- Evidence basis (metric or cost_report reference)
- Prerequisites or validation steps before production rollout

### Preventive Actions
Governance, alerting, and policy controls that prevent recurrence across all domains.

### Cross-Service Remediations
For detected cascades, include the appropriate fix from `references/cross-service-playbooks.md`:
- **VPC Gateway Endpoint** — when private subnet traffic to S3/DynamoDB routes through NAT
- **Request reduction / cache** — when compute repeatedly calls storage/API and
  downstream requests per invocation are high
- **Callback over polling** — replace SFN Wait-state loop with `.waitForTaskToken`
- **CloudFront cache tuning** — TTL, cache key, compression to reach > 80% CacheHitRate
- **Cost Anomaly Detection** — monitor + alert for detected spike type
- **VPC Flow Logs + Athena** — when network cost attribution needs traffic analysis

---

## 4. Estimated Monthly Savings

| Domain | Resources Changed | Monthly Savings | Annual Savings |
|--------|------------------|----------------|----------------|
| Lambda | X of Y functions | $X | $X |
| S3     | X of Y buckets   | $X | $X |
| DynamoDB | X of Y tables  | $X | $X |
| **TOTAL** | **N resources** | **$X/mo** | **$X/yr** |

Current avg monthly spend: $X → waste ratio: X%
Pricing source: <source>

---

## Agent Performance Measurement

Single vs. multi-agent comparison for this run. Derive each value from what
actually happened — do not fabricate. Write `Not measured` for anything
unobservable.

- **`recall`** — patterns found ÷ total expected (use `_fusion_components` count
  from `cost_report.json` as denominator; if absent, use Problem Identification
  row count for multi-agent and estimate single-agent recall from context constraints).
- **`input_tokens`** — single-agent: estimate from full unsliced file sizes.
  Multi-agent: sum of all domain slices passed to subagents.
- **`output_tokens`** — single-agent: estimate for one monolithic analysis.
  Multi-agent: sum of subagent outputs + aggregation step.
- **`wall_clock_sec`** — multi-agent: longest parallel chain, not total sequential time.
  Single-agent: estimate from comparable single-pass analysis.
- **`agent_count`** — actual domain subagents spawned (0 for single-domain routing).
- **`framework`** — `"claude-subagent"` if Agent tool was used; `"single-pass"` otherwise.
- **`notes`** — emergent cross-domain findings that a single-agent would have missed.
  If none: `"No cross-domain emergent findings."`.

```json
{
  "single_agent": {
    "recall": <float 0-1>,
    "input_tokens": <int>,
    "output_tokens": <int>,
    "wall_clock_sec": <int>
  },
  "multi_agent": {
    "recall": <float 0-1>,
    "input_tokens": <int>,
    "output_tokens": <int>,
    "wall_clock_sec": <int>,
    "agent_count": <int>
  },
  "framework": "<claude-subagent | single-pass>",
  "notes": "<emergent findings or No cross-domain emergent findings.>"
}
```

---

## Scenario Coverage

Every detected domain must appear as one of:

| Outcome | When to use |
|---------|-------------|
| **Finding** | Waste pattern detected with supporting evidence |
| **No finding with evidence** | Domain analyzed, no waste found — state what was checked |
| **Skipped — missing evidence** | Required input file(s) absent — state which files |

Never omit a detected domain silently.
