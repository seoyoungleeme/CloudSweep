---
name: finops-anomaly
description: >
  FinOps Cost Anomaly Analysis Skill — Detects real-time cost spikes from AWS Cost
  Explorer API responses (GetCostAndUsage HOURLY, GetAnomalies). Use when inputs are
  CE mock/API responses, not Terraform infrastructure. Keywords: "cost spike",
  "anomaly", "GetCostAndUsage", "GetAnomalies", "hourly billing", "비용 스파이크".
user_invocable: false
---

# FinOps Cost Anomaly Analysis Skill

## Purpose

> **Review-only authority:** LangGraph owns spike detection, service attribution, and confidence facts. Claude explains likely root cause, reviews gaps, and cites fact IDs; it must not invent or recalculate the machine result.

Detect and attribute a real-time cost spike using Cost Explorer hourly data and
anomaly detection results. Produces a structured incident report.

This skill operates in **standalone mode** only (routed from `finops` orchestrator).
Do not dispatch subagents.

---

## Inputs

| File (glob) | Required | Purpose |
|-------------|----------|---------|
| `mock_responses/get_cost_and_usage*.json` | Yes (full mode) / No (degraded) | CE `GetCostAndUsage` HOURLY response — primary spike detection source |
| `mock_responses/get_anomalies.json` | No | CE `GetAnomalies` response — anomaly confirmation and RootCauses drilldown |
| `mock_responses/cloudtrail*.json` or `cloudtrail.json` | No | CloudTrail events for root-cause correlation |

**Degraded mode**: if `get_cost_and_usage*.json` is absent but `get_anomalies.json` is present,
skip Steps 1–2 (detect, drilldown) and produce anomaly summary only. Note in the report:
"Spike detection unavailable — cost time-series data absent."

If neither CE file is present, report what is unavailable and stop.

## Output Directory

Write all artifacts under `<WORK_DIR>/result/` (create if missing), matching the
standard `/finops` sample layout.

| File | Notes |
|------|-------|
| `result/finops_report.md` | Primary report — matches standard finops output convention |
| `result/main_optimized.tf` | Standard artifact; placeholder when anomaly mode has no Terraform input |
| `result/solution.py` | Scenario-specific code artifact, when README requires `solution.py` |

---

## Workflow

### Step 1 — detect()

**0. Merge pages first.**
`GetCostAndUsage` returns at most 1 day of HOURLY data per request. Multi-day analysis
windows require pagination via `NextPageToken`.

- Collect **all** files matching `mock_responses/get_cost_and_usage*.json`, sorted by filename.
- Merge every `ResultsByTime[]` array across files into one list before any analysis.
- If any response contains `NextPageToken` in its metadata, note in the report:
  "data required pagination — merged N page(s)".
- For `get_anomalies.json`: in real usage the `DateInterval` filter should span the full
  analysis window; if the mock lacks this filter, note its scope in the report.

Parse the merged CE data:

1. Build a time-ordered list of `{ timestamp, total_cost, groups[] }` from
   `ResultsByTime[].TimePeriod.Start` and `Total.UnblendedCost.Amount`.
2. For each datapoint, compute a **rolling baseline**:
   - Preferred window: last 6 datapoints before the current hour.
   - If fewer than 3 prior datapoints exist, use all available prior datapoints.
   - If only 1 prior point exists, use pct-change as the sole signal.
3. Compute `baseline_mean` and `baseline_stddev` from the window.
4. **Statistical flag**: mark as spike if `cost > baseline_mean + 2 * baseline_stddev`.
5. **Pct-change flag**: mark as spike if cost increased > 100 % from the previous datapoint.
6. A datapoint is a confirmed spike if either flag fires.

Report:
- Spike timestamp(s)
- Baseline mean ± stddev
- Spike cost and absolute/pct delta
- Which flags fired

> Note: sparse data (< 6 hourly datapoints) reduces stddev reliability. State the
> window size actually used.

### Step 2 — drilldown()

For each confirmed spike hour, using `Groups[]` from the CE response:

1. Compute each service's **baseline avg cost** from the same rolling window used in detect().
2. Rank services by `delta = spike_cost − baseline_avg`, descending.
3. Compute each service's **delta share** = `delta / total_delta * 100`.
4. Cross-reference with `get_anomalies.json`:
   - Match `DimensionValue` to spike service.
   - Extract `RootCauses[].{Service, Region, LinkedAccount, UsageType}`.
   - Record `AnomalyScore.CurrentScore` and `Impact.{TotalImpact, TotalActualSpend, TotalExpectedSpend}`.
5. **USAGE_TYPE second-pass drilldown** (GroupBy USAGE_TYPE within top service):
   - If a mock file matching `mock_responses/get_cost_and_usage*usagetype*.json` exists,
     parse it: rank UsageType entries by cost for the top service at the spike hour.
   - Otherwise: use `GetAnomalies.RootCauses[].UsageType` for services that triggered an
     anomaly — this is the attribution source.
   - If neither source provides UsageType, mark as `"UsageType: not available in mock data"`.
   - **Real implementation note**: requires a second `GetCostAndUsage` call with
     `GroupBy=[{Type: DIMENSION, Key: USAGE_TYPE}]` and a `Filter` scoped to the top service.
6. Produce ranked drilldown table: `Service | Baseline Avg | Spike Cost | Delta | Delta Share% | UsageType`.

### Step 3 — correlate()

Inspect CloudTrail data only if present:

1. Search WORK_DIR for `mock_responses/cloudtrail*.json` or `cloudtrail.json`.
2. If found:
   - Filter events where `eventTime` is within `[spike_start − 60 min, spike_start]`.
   - Filter by `eventSource` matching the top anomalous service:
     - EC2 → `ec2.amazonaws.com`, `autoscaling.amazonaws.com`, `ecs.amazonaws.com`, `cloudformation.amazonaws.com`
     - S3 → `s3.amazonaws.com`
     - RDS → `rds.amazonaws.com`
   - Highlight events: `RunInstances`, `CreateAutoScalingGroup`, `UpdateAutoScalingGroup`,
     `UpdateService`, `CreateStack`, `UpdateStack`,
     `CreateBucket`, `PutBucketReplication`, `PutBucketPolicy`.
   - Report event name, time, userAgent, requestParameters summary.
3. If CloudTrail data is **absent**:
   - State: "CloudTrail mock not provided — cannot confirm triggering event."
   - Do **not** invent events or infer from service name alone.
   - Note as instrumentation gap (evidence-first rule).

### Step 4 — report()

Write `<WORK_DIR>/result/finops_report.md` with the sections below.

---

## Report Template

```markdown
# FinOps Cost Anomaly Report

**Scenario**: <WORK_DIR basename>
**Analysis date**: <today>
**Data range**: <earliest timestamp> – <latest timestamp in CE data>

---

## 1. Spike Window

| Metric | Value |
|--------|-------|
| Spike start | <timestamp> |
| Baseline window | <N datapoints, e.g. "3 hourly datapoints (2026-05-26T00–12Z)"> |
| Baseline mean | $X.XX/hr |
| Baseline stddev | $X.XX/hr |
| Spike cost | $X.XX/hr |
| Absolute delta | +$X.XX/hr |
| Pct change | +X% |
| Flags fired | Statistical (>mean+2σ) / Pct-change (>100%) |

---

## 2. Impact (from GetAnomalies)

| Service | AnomalyScore | TotalImpact | TotalActualSpend | TotalExpectedSpend |
|---------|-------------|-------------|-----------------|-------------------|
| ...     | ...         | $...        | $...            | $...              |

Total anomaly impact: $<sum of TotalImpact across anomalies>

---

## 3. Drilldown by Service

| Rank | Service | Baseline Avg/hr | Spike Cost/hr | Delta | Delta Share | UsageType |
|------|---------|----------------|---------------|-------|-------------|-----------|
| 1    | ...     | ...            | ...           | ...   | ...%        | ...       |

---

## 4. Anomaly API Confirmation

<Summarize RootCauses[] from GetAnomalies: Service, Region, LinkedAccount, UsageType>

---

## 5. CloudTrail Correlation

<If CloudTrail data present: list triggering events in [spike_start−60m, spike_start].>
<If absent: "CloudTrail mock not provided — instrumentation gap. Cannot confirm triggering event.">

---

## 6. Likely Root Cause

<Evidence-based summary. If CloudTrail absent, qualify confidence.>

---

## 7. Remediation

<Per-service recommendations with doc URLs from mcp__aws-docs__search_documentation.>

- [ ] <Service>: <action>
  - Doc: <URL>
  - Est. monthly impact prevention: $<TotalImpact> if root cause confirmed

---

## 8. Confidence

| Layer | Confidence | Reason |
|-------|-----------|--------|
| Spike detection | High | Statistical + pct-change both fired |
| Service attribution | High | GetAnomalies RootCauses confirm UsageType |
| Root cause (triggering event) | Medium / Low | CloudTrail absent — triggering event unknown |

---

## 9. Deliverables Status

| Deliverable | Status |
|-------------|--------|
| `result/finops_report.md` | Generated |
| `result/main_optimized.tf` | Generated placeholder — no Terraform in anomaly mode |
| `result/solution.py` | Generated |
```

---

## Step 5 — solution.py

Generate `<WORK_DIR>/result/solution.py` as a mock/real API dual-mode analysis pipeline.
Use only the Python standard library. Include an `if __name__ == "__main__":` guard.

Define these six functions in order:

```python
def load_cost_and_usage(work_dir: str, use_mock: bool = True) -> list[dict]:
    """Glob mock_responses/get_cost_and_usage*.json and merge all ResultsByTime pages.
    When use_mock=False, call boto3 ce.get_cost_and_usage with HOURLY granularity."""

def load_anomalies(work_dir: str, use_mock: bool = True) -> list[dict]:
    """Load mock_responses/get_anomalies.json → response["Anomalies"] list.
    When use_mock=False, call boto3 ce.get_anomalies and extract ["Anomalies"]."""

def detect_spikes(cost_data: list[dict]) -> list[dict]:
    """Apply 6-point rolling-baseline statistical (>mean+2σ) and pct-change (>100%) flags.
    Return spike records: {timestamp, cost, baseline_mean, baseline_stddev, flags}."""

def drilldown_services(cost_data: list[dict], anomalies: list[dict],
                       spike_hours: list[str]) -> list[dict]:
    """Rank services by delta = spike_cost − baseline_avg for each spike hour.
    Cross-reference anomaly RootCauses; include UsageType when available."""

def correlate_cloudtrail(work_dir: str, spike_start: str, top_service: str) -> list[dict]:
    """Search CloudTrail mocks for events in [spike_start−60 min, spike_start].
    Filter by top_service eventSource mapping (ec2/autoscaling/ecs/cloudformation/s3/rds).
    Return matched events; empty list if no CloudTrail data found."""

def render_report(spikes: list, drilldown: list, correlations: list,
                  anomalies: list, cost_data: list[dict],
                  output_paths: list[str], work_dir: str) -> None:
    """Write the report to result/finops_report.md."""
```

`main()` must call them in order and write the report to
`<WORK_DIR>/result/finops_report.md`.

---

## Pricing / Docs MCP

- Do **not** call `mcp__aws-pricing__get_pricing` — CE data already reflects actual spend.
- **Do** call `mcp__aws-docs__search_documentation` for each remediation item to get a doc URL.
  If MCP is unavailable, note "doc URL unavailable" and continue.

---

## Evidence-First Rule

Do not assert a root cause that the available data cannot confirm. Specifically:
- If CloudTrail is absent, confidence for the triggering event is Medium at most.
- If a service appears in spike data but not in `get_anomalies.json`, mark attribution as Suspected.
- Never fill unknowns with scenario filename, hint text, or README content as evidence.

Generated by: finops-anomaly skill — Claude Code
