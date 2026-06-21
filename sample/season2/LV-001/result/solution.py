"""
LV-001: Cost Spike Detection Pipeline
Mock/real AWS Cost Explorer dual-mode analysis.

Usage:
    python solution.py              # mock mode (reads mock_responses/)
    python solution.py --live       # real AWS API mode (requires boto3 + credentials)
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

import anthropic
from langgraph.graph import END, StateGraph


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_cost_and_usage(work_dir: str, use_mock: bool = True) -> list[dict]:
    """Glob mock_responses/get_cost_and_usage*.json and merge all ResultsByTime pages.
    When use_mock=False, call boto3 ce.get_cost_and_usage with HOURLY granularity."""
    if use_mock:
        pattern = os.path.join(work_dir, "mock_responses", "get_cost_and_usage*.json")
        files = sorted(glob.glob(pattern))
        if not files:
            raise FileNotFoundError(f"No GetCostAndUsage mock files found: {pattern}")
        merged: list[dict] = []
        page_count = 0
        for path in files:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            merged.extend(data.get("ResultsByTime", []))
            page_count += 1
            if "NextPageToken" in data.get("ResponseMetadata", {}):
                print(f"[load_cost_and_usage] Note: pagination token present in {os.path.basename(path)}")
        if page_count > 1:
            print(f"[load_cost_and_usage] Merged {page_count} page file(s), {len(merged)} datapoints total")
        return merged
    else:
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 not installed. Install with: pip install boto3")
        client = boto3.client("ce", region_name="us-east-1")
        results: list[dict] = []
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=2)
        kwargs: dict = {
            "TimePeriod": {"Start": str(start), "End": str(end)},
            "Granularity": "HOURLY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        }
        while True:
            resp = client.get_cost_and_usage(**kwargs)
            results.extend(resp.get("ResultsByTime", []))
            token = resp.get("NextPageToken")
            if not token:
                break
            kwargs["NextPageToken"] = token
        return results


def load_anomalies(work_dir: str, use_mock: bool = True) -> list[dict]:
    """Load mock_responses/get_anomalies.json → response["Anomalies"] list.
    When use_mock=False, call boto3 ce.get_anomalies and extract ["Anomalies"]."""
    if use_mock:
        path = os.path.join(work_dir, "mock_responses", "get_anomalies.json")
        if not os.path.exists(path):
            print("[load_anomalies] No get_anomalies.json found -- anomaly confirmation unavailable")
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        anomalies = data.get("Anomalies", [])
        print(f"[load_anomalies] Loaded {len(anomalies)} anomalies")
        return anomalies
    else:
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 not installed. Install with: pip install boto3")
        client = boto3.client("ce", region_name="us-east-1")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=2)
        resp = client.get_anomalies(
            DateInterval={"StartDate": str(start), "EndDate": str(end)},
            TotalImpact={"NumericOperator": "GREATER_THAN", "StartValue": 0},
        )
        return resp.get("Anomalies", [])


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def detect_spikes(cost_data: list[dict]) -> list[dict]:
    """Apply 6-point rolling-baseline statistical (>mean+2σ) and pct-change (>100%) flags.
    Return spike records: {timestamp, cost, baseline_mean, baseline_stddev, flags}."""
    series: list[tuple[str, float]] = sorted(
        [(e["TimePeriod"]["Start"], float(e["Total"]["UnblendedCost"]["Amount"]))
         for e in cost_data],
        key=lambda x: x[0],
    )

    spikes: list[dict] = []
    for i, (ts, cost) in enumerate(series):
        prior = series[max(0, i - 6):i]
        if not prior:
            continue

        values = [c for _, c in prior]
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        stddev = math.sqrt(variance)

        flags: list[str] = []
        if n >= 3 and stddev > 0 and cost > mean + 2 * stddev:
            flags.append(f"statistical (cost ${cost:.2f} > mean+2s ${mean + 2*stddev:.2f})")
        prev_cost = series[i - 1][1]
        pct_change = ((cost - prev_cost) / prev_cost * 100) if prev_cost > 0 else 0.0
        if pct_change > 100:
            flags.append(f"pct-change (+{pct_change:.1f}% > 100%)")

        if flags:
            spikes.append({
                "timestamp": ts,
                "cost": cost,
                "baseline_mean": round(mean, 4),
                "baseline_stddev": round(stddev, 4),
                "baseline_n": n,
                "prev_cost": round(prev_cost, 4),
                "pct_change": round(pct_change, 4),
                "flags": flags,
            })

    return spikes


def drilldown_services(
    cost_data: list[dict],
    anomalies: list[dict],
    spike_hours: list[str],
) -> list[dict]:
    """Rank services by delta = spike_cost − baseline_avg for each spike hour.
    Cross-reference anomaly RootCauses; include UsageType when available."""
    # CE Groups use short names; GetAnomalies uses long names — normalize
    SERVICE_ALIASES: dict[str, str] = {
        "Amazon S3": "Amazon Simple Storage Service",
        "Amazon EC2": "Amazon Elastic Compute Cloud",
        "Amazon ES": "Amazon OpenSearch Service",
    }

    series = sorted(cost_data, key=lambda e: e["TimePeriod"]["Start"])
    anomaly_index: dict[str, dict] = {a["DimensionValue"]: a for a in anomalies}

    results: list[dict] = []
    for spike_ts in spike_hours:
        spike_entry = next((e for e in series if e["TimePeriod"]["Start"] == spike_ts), None)
        if spike_entry is None:
            continue

        prior_entries = [e for e in series if e["TimePeriod"]["Start"] < spike_ts][-6:]
        spike_groups: dict[str, float] = {
            g["Keys"][0]: float(g["Metrics"]["UnblendedCost"]["Amount"])
            for g in spike_entry.get("Groups", [])
        }

        service_baselines: dict[str, list[float]] = {}
        for entry in prior_entries:
            for g in entry.get("Groups", []):
                svc = g["Keys"][0]
                service_baselines.setdefault(svc, []).append(
                    float(g["Metrics"]["UnblendedCost"]["Amount"])
                )

        rows: list[dict] = []
        total_delta = 0.0
        for svc, spike_cost in spike_groups.items():
            baseline_vals = service_baselines.get(svc, [0.0])
            baseline_avg = sum(baseline_vals) / len(baseline_vals)
            delta = spike_cost - baseline_avg
            total_delta += max(delta, 0)

            canonical = SERVICE_ALIASES.get(svc, svc)
            anomaly = anomaly_index.get(canonical) or anomaly_index.get(svc)
            usage_type = "Not in GetAnomalies - Suspected"
            anomaly_score = None
            total_impact = None
            if anomaly:
                root_causes = anomaly.get("RootCauses", [])
                if root_causes:
                    usage_type = root_causes[0].get("UsageType", "N/A")
                anomaly_score = anomaly.get("AnomalyScore", {}).get("CurrentScore")
                total_impact = anomaly.get("Impact", {}).get("TotalImpact")

            rows.append({
                "service": svc,
                "baseline_avg": round(baseline_avg, 4),
                "spike_cost": round(spike_cost, 4),
                "delta": round(delta, 4),
                "anomaly_score": anomaly_score,
                "total_impact": total_impact,
                "usage_type": usage_type,
            })

        rows.sort(key=lambda r: r["delta"], reverse=True)
        for row in rows:
            row["delta_share_pct"] = (
                round(max(row["delta"], 0) / total_delta * 100, 1) if total_delta else 0
            )

        results.append({"spike_timestamp": spike_ts, "services": rows})

    return results


def correlate_cloudtrail(
    work_dir: str,
    spike_start: str,
    top_service: str,
) -> list[dict]:
    """Search CloudTrail mocks for events in [spike_start−60 min, spike_start].
    Filter by top_service eventSource mapping (ec2/autoscaling/ecs/cloudformation/s3/rds).
    Return matched events; empty list if no CloudTrail data found."""
    SERVICE_SOURCES: dict[str, list[str]] = {
        "Amazon Elastic Compute Cloud": [
            "ec2.amazonaws.com",
            "autoscaling.amazonaws.com",
            "ecs.amazonaws.com",
            "cloudformation.amazonaws.com",
        ],
        "Amazon Simple Storage Service": ["s3.amazonaws.com"],
        "Amazon Relational Database Service": ["rds.amazonaws.com"],
    }
    HIGHLIGHT_EVENTS = {
        "RunInstances", "CreateAutoScalingGroup", "UpdateAutoScalingGroup",
        "UpdateService", "CreateStack", "UpdateStack",
        "CreateBucket", "PutBucketReplication", "PutBucketPolicy",
    }

    mock_dir = os.path.join(work_dir, "mock_responses")
    ct_files = (
        glob.glob(os.path.join(mock_dir, "cloudtrail*.json"))
        + glob.glob(os.path.join(work_dir, "cloudtrail.json"))
    )
    if not ct_files:
        return []

    spike_dt = datetime.fromisoformat(spike_start.replace("Z", "+00:00"))
    window_start = spike_dt - timedelta(minutes=60)
    allowed_sources = SERVICE_SOURCES.get(top_service, [])

    matched: list[dict] = []
    for path in ct_files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        events = data if isinstance(data, list) else data.get("Records", [])
        for event in events:
            try:
                event_dt = datetime.fromisoformat(
                    event.get("eventTime", "").replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if not (window_start <= event_dt <= spike_dt):
                continue
            if event.get("eventSource") not in allowed_sources:
                continue
            matched.append({
                "eventTime": event.get("eventTime"),
                "eventSource": event.get("eventSource"),
                "eventName": event.get("eventName"),
                "userAgent": event.get("userAgent"),
                "highlighted": event.get("eventName") in HIGHLIGHT_EVENTS,
                "requestParameters": str(event.get("requestParameters", ""))[:200],
            })

    return sorted(matched, key=lambda e: e["eventTime"])


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

_REMEDIATION_TIPS: dict[str, list[str]] = {
    "Amazon Elastic Compute Cloud": [
        "inspect instance launches, Auto Scaling changes, ECS service updates, and "
        "CloudFormation stack updates in the pre-spike window. If unintentional, revert "
        "capacity changes or terminate surplus instances.",
        "if the new compute level is legitimate and recurring, evaluate Savings Plans or "
        "rightsizing after confirming sustained utilization.",
    ],
    "Amazon Simple Storage Service": [
        "reduce Tier-1 request volume by removing redundant PUT/LIST loops, batching "
        "writes, caching manifests/indexes, and adding request metrics by bucket or prefix.",
    ],
    "Amazon Relational Database Service": [
        "review connection counts and query patterns during the spike window; consider "
        "read replicas or connection pooling if load was legitimate.",
    ],
}

_CE_SHORT_TO_LONG: dict[str, str] = {
    "Amazon S3": "Amazon Simple Storage Service",
    "Amazon EC2": "Amazon Elastic Compute Cloud",
    "Amazon RDS": "Amazon Relational Database Service",
}


def _build_remediation(drilldown: list[dict], anomaly_impact: dict[str, float]) -> list[str]:
    """Generate per-service remediation bullets with impact estimates from anomaly data."""
    items: list[str] = []
    seen: set[str] = set()
    services = drilldown[0]["services"] if drilldown else []
    for row in services:
        svc = row["service"]
        canonical = _CE_SHORT_TO_LONG.get(svc, svc)
        tips = _REMEDIATION_TIPS.get(canonical, [])
        if not tips or canonical in seen:
            continue
        seen.add(canonical)
        impact = anomaly_impact.get(canonical, 0)
        impact_str = (
            f" — Est. prevention: ${impact:.2f} if root cause confirmed."
            if impact else "."
        )
        short = canonical.replace("Amazon ", "")
        items.append(f"- [ ] {short}: {tips[0][:-1]}{impact_str}")
        for tip in tips[1:]:
            items.append(f"- [ ] {short}: {tip}")
    return items

def _build_confidence(
    spikes: list,
    drilldown: list,
    correlations: list,
) -> list[str]:
    """Derive the Confidence table rows from actual analysis results, not hardcoded text."""
    rows: list[tuple[str, str, str]] = []

    # Spike detection — based on which flags fired
    if not spikes:
        rows.append(("Spike detection", "N/A", "No spikes detected in time-series data"))
    else:
        flag_kinds = {f.split(" ")[0] for s in spikes for f in s.get("flags", [])}
        if {"statistical", "pct-change"} <= flag_kinds:
            rows.append(("Spike detection", "High", "Statistical and pct-change flags fired"))
        else:
            only = ", ".join(sorted(flag_kinds)) or "none"
            rows.append(("Spike detection", "Medium", f"Only {only} flag fired"))

    # Service attribution — based on which top drivers are confirmed in GetAnomalies
    top_services = drilldown[0]["services"] if drilldown else []
    drivers = [r for r in top_services if r.get("delta", 0) > 0]
    confirmed = [r["service"] for r in drivers if r.get("anomaly_score") is not None]
    suspected = [r["service"] for r in drivers if r.get("anomaly_score") is None]
    if not drivers:
        rows.append(("Service attribution", "N/A", "No positive-delta drivers to attribute"))
    elif confirmed and not suspected:
        names = ", ".join(s.replace("Amazon ", "") for s in confirmed)
        rows.append(("Service attribution", "High", f"GetAnomalies RootCauses confirm {names}"))
    elif confirmed:
        names = ", ".join(s.replace("Amazon ", "") for s in confirmed)
        rows.append((
            "Service attribution", "Medium",
            f"{names} confirmed; others suspected (not in GetAnomalies)",
        ))
    else:
        rows.append((
            "Service attribution", "Low",
            "Top drivers absent from GetAnomalies — attribution suspected",
        ))

    # Triggering event — based on CloudTrail correlation results
    if not correlations:
        rows.append(("Triggering event", "Low", "CloudTrail events not available in pre-spike window"))
    elif any(e.get("highlighted") for e in correlations):
        rows.append(("Triggering event", "High", "Highlighted CloudTrail event(s) in pre-spike window"))
    else:
        rows.append(("Triggering event", "Medium", "CloudTrail events present but none highlighted"))

    # Baseline reliability — based on prior-datapoint count used
    baseline_n = max((s.get("baseline_n", 0) for s in spikes), default=0)
    if baseline_n >= 6:
        rows.append(("Baseline reliability", "High", f"{baseline_n} prior datapoints in rolling window"))
    elif baseline_n >= 3:
        rows.append(("Baseline reliability", "Medium", f"Sparse window ({baseline_n} prior datapoints)"))
    else:
        rows.append(("Baseline reliability", "Low", f"Very sparse window ({baseline_n} prior datapoints)"))

    lines = ["| Layer | Confidence | Reason |", "|-------|------------|--------|"]
    lines += [f"| {layer} | {conf} | {reason} |" for layer, conf, reason in rows]
    return lines


def render_report(
    spikes: list,
    drilldown: list,
    correlations: list,
    anomalies: list,
    cost_data: list[dict],
    output_paths: list[str],
    work_dir: str,
    llm_sections: str = "",
) -> None:
    """Write the same submission report to every requested output path."""
    timestamps = sorted(e["TimePeriod"]["Start"] for e in cost_data)
    data_range = f"{timestamps[0]} - {timestamps[-1]}" if timestamps else "No cost data"
    scenario = Path(work_dir).name
    impact_total = sum(float(a.get("Impact", {}).get("TotalImpact", 0)) for a in anomalies)

    linked_accounts = sorted({
        cause.get("LinkedAccount", "")
        for a in anomalies
        for cause in a.get("RootCauses", [])
        if cause.get("LinkedAccount")
    })
    linked_accounts_str = ", ".join(linked_accounts) if linked_accounts else "N/A"

    anomaly_impact: dict[str, float] = {
        a.get("DimensionValue", ""): float(a.get("Impact", {}).get("TotalImpact", 0))
        for a in anomalies
        if a.get("Impact", {}).get("TotalImpact")
    }

    lines: list[str] = [
        "# FinOps Cost Anomaly Report",
        "",
        f"**Scenario**: {scenario}",
        f"**Analysis date**: {datetime.now().strftime('%Y-%m-%d')}",
        f"**Data range**: {data_range}",
        "",
        "---",
        "",
        "## 1. Spike Window",
        "",
    ]

    if not spikes:
        lines.append("No spikes detected from Cost Explorer time-series data.")
    for spike in spikes:
        delta = spike["cost"] - spike["baseline_mean"]
        lines += [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Spike start | {spike['timestamp']} |",
            f"| Baseline window | {spike['baseline_n']} prior datapoints |",
            f"| Baseline mean | ${spike['baseline_mean']:.2f}/hr |",
            f"| Baseline stddev | ${spike['baseline_stddev']:.2f}/hr |",
            f"| Previous datapoint cost | ${spike['prev_cost']:.2f}/hr |",
            f"| Spike cost | ${spike['cost']:.2f}/hr |",
            f"| Absolute delta vs baseline | +${delta:.2f}/hr |",
            f"| Pct change vs previous | +{spike['pct_change']:.1f}% |",
            f"| Flags fired | {'; '.join(spike['flags'])} |",
            f"| Affected account(s) | {linked_accounts_str} |",
            "",
            "> Sparse data note: this mock has only a few sampled hourly points, so the "
            "statistical baseline is directional. The anomaly API is used as confirmation.",
            "",
        ]

    lines += ["---", "", "## 2. Impact (from GetAnomalies)", ""]
    if anomalies:
        lines += [
            "| Service | AnomalyScore | TotalImpact | TotalActualSpend | TotalExpectedSpend |",
            "|---------|--------------|-------------|------------------|--------------------|",
        ]
        for anomaly in anomalies:
            score = anomaly.get("AnomalyScore", {}).get("CurrentScore", "N/A")
            impact = anomaly.get("Impact", {})
            lines.append(
                f"| {anomaly.get('DimensionValue', 'Unknown')} | {score} | "
                f"${float(impact.get('TotalImpact', 0)):.2f} | "
                f"${float(impact.get('TotalActualSpend', 0)):.2f} | "
                f"${float(impact.get('TotalExpectedSpend', 0)):.2f} |"
            )
        lines += ["", f"**Total anomaly impact: ${impact_total:.2f}**", ""]
    else:
        lines += ["GetAnomalies data unavailable; impact and RootCauses cannot be confirmed.", ""]

    lines += ["---", "", "## 3. Drilldown by Service", ""]
    for item in drilldown:
        lines.append(f"**Spike at {item['spike_timestamp']}**\n")
        lines += [
            "| Rank | Service | Baseline Avg/hr | Spike Cost/hr | Delta | Delta Share | UsageType |",
            "|------|---------|-----------------|---------------|-------|-------------|-----------|",
        ]
        for rank, row in enumerate(item["services"], 1):
            lines.append(
                f"| {rank} | {row['service']} | ${row['baseline_avg']:.2f} | "
                f"${row['spike_cost']:.2f} | +${row['delta']:.2f} | "
                f"{row['delta_share_pct']}% | {row['usage_type']} |"
            )
        lines.append("")

    lines += ["---", "", "## 4. Anomaly API Confirmation", ""]
    if anomalies:
        for anomaly in anomalies:
            lines.append(f"**{anomaly.get('DimensionValue', 'Unknown service')}**")
            for cause in anomaly.get("RootCauses", []):
                lines.append(
                    f"- Region: {cause.get('Region', 'N/A')} | "
                    f"LinkedAccount: {cause.get('LinkedAccount', 'N/A')} | "
                    f"UsageType: `{cause.get('UsageType', 'N/A')}`"
                )
            lines.append("")
    else:
        lines.append("No anomaly API confirmation available.\n")

    lines += ["---", "", "## 5. CloudTrail Correlation", ""]
    if not correlations:
        lines += [
            "CloudTrail mock not provided - instrumentation gap. Cannot confirm triggering event.",
            "",
            "Recommended collection window: spike start minus 60 minutes through spike start.",
            "Recommended EC2-related eventSources: `ec2.amazonaws.com`, "
            "`autoscaling.amazonaws.com`, `ecs.amazonaws.com`, `cloudformation.amazonaws.com`.",
            "",
        ]
    else:
        for event in correlations:
            marker = "[!] " if event.get("highlighted") else ""
            lines.append(
                f"{marker}{event['eventTime']} | {event['eventSource']} | "
                f"{event['eventName']} | agent={event.get('userAgent', 'N/A')}"
            )
        lines.append("")

    if llm_sections:
        lines += ["---", "", llm_sections.strip(), ""]
    else:
        top_rows = drilldown[0]["services"] if drilldown else []
        top = top_rows[0] if top_rows else None
        secondary = top_rows[1] if len(top_rows) > 1 else None
        lines += ["---", "", "## 6. Likely Root Cause", ""]
        if top:
            lines.append(
                f"Primary driver: {top['service']} increased from ${top['baseline_avg']:.2f}/hr "
                f"to ${top['spike_cost']:.2f}/hr, contributing {top['delta_share_pct']}% of the "
                f"total delta. UsageType attribution: `{top['usage_type']}`."
            )
        if secondary:
            lines.append(
                f"Secondary driver: {secondary['service']} increased from "
                f"${secondary['baseline_avg']:.2f}/hr to ${secondary['spike_cost']:.2f}/hr "
                f"({secondary['delta_share_pct']}% of delta), UsageType `{secondary['usage_type']}`."
            )
        lines.append(
            "Triggering event confidence remains low until CloudTrail events in the pre-spike "
            "window are available."
        )
        lines += [
            "",
            "---",
            "",
            "## 7. Remediation",
            "",
            *_build_remediation(drilldown, anomaly_impact),
            "- [ ] Instrumentation: keep CloudTrail management events and enable service-specific "
            "metrics needed to tie spend spikes to deploy or scaling events.",
            "",
        ]

    lines += [
        "---",
        "",
        "## 8. Confidence",
        "",
        *_build_confidence(spikes, drilldown, correlations),
        "",
        "---",
        "",
        "## 9. Deliverables Status",
        "",
        "| Deliverable | Status |",
        "|-------------|--------|",
        "| `result/finops_report.md` | Generated for `/finops` convention |",
        "| `result/solution.py` | Generated as scenario code artifact |",
        "| `result/main_optimized.tf` | Generated placeholder; no Terraform changes for anomaly mode |",
    ]

    content = "\n".join(lines) + "\n"
    for output_path in output_paths:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[render_report] Written -> {output_path}")


# ---------------------------------------------------------------------------
# LangGraph state + nodes
# ---------------------------------------------------------------------------

class AnalysisState(TypedDict):
    work_dir: str
    use_mock: bool
    cost_data: list
    anomalies: list
    spikes: list
    drilldown: list
    correlations: list
    output_paths: list


def _node_load(state: AnalysisState) -> dict:
    cost_data = load_cost_and_usage(state["work_dir"], state["use_mock"])
    print(f"[load] Loaded {len(cost_data)} hourly datapoints")
    anomalies = load_anomalies(state["work_dir"], state["use_mock"])
    return {"cost_data": cost_data, "anomalies": anomalies}


def _node_detect(state: AnalysisState) -> dict:
    spikes = detect_spikes(state["cost_data"])
    print(f"[detect] Spikes: {[s['timestamp'] for s in spikes]}")
    return {"spikes": spikes}


def _node_drilldown(state: AnalysisState) -> dict:
    spike_hours = [s["timestamp"] for s in state["spikes"]]
    return {"drilldown": drilldown_services(state["cost_data"], state["anomalies"], spike_hours)}


def _node_correlate(state: AnalysisState) -> dict:
    if not state["spikes"]:
        return {"correlations": []}
    top_service = "Amazon Elastic Compute Cloud"
    if state["drilldown"] and state["drilldown"][0]["services"]:
        top_service = state["drilldown"][0]["services"][0]["service"]
    correlations = correlate_cloudtrail(
        state["work_dir"], state["spikes"][0]["timestamp"], top_service
    )
    if not correlations:
        print("[correlate] No CloudTrail data - instrumentation gap noted in report")
    return {"correlations": correlations}


def _valid_llm_sections(text: str) -> bool:
    """Verify LLM output has exactly the expected section headers, in order, and nothing
    that would corrupt the report's numbering (no stray ## 8/## 9 or duplicate headers)."""
    if not text or not text.strip():
        return False
    h6 = text.find("## 6. Likely Root Cause")
    h7 = text.find("## 7. Remediation")
    if h6 == -1 or h7 == -1 or h6 > h7:
        return False
    # No duplicates of the two headers and no later sections that collide with 8/9.
    if text.count("## 6.") != 1 or text.count("## 7.") != 1:
        return False
    if "## 8." in text or "## 9." in text:
        return False
    return True


def _generate_interpretive_sections(state: AnalysisState) -> str:
    """Call Claude to generate Section 6 (Root Cause) and Section 7 (Remediation)."""
    drilldown_rows = state["drilldown"][0]["services"][:3] if state["drilldown"] else []
    cloudtrail_info = (
        json.dumps(state["correlations"], indent=2)
        if state["correlations"]
        else "Not provided — instrumentation gap."
    )
    prompt = f"""You are a FinOps analyst writing an AWS cost spike incident report.

Based ONLY on the structured data below, write two sections.

Evidence-first rule:
- Do not assert a root cause the data cannot confirm.
- If CloudTrail is absent, state triggering event confidence is Low.
- Mark services absent from GetAnomalies as "Suspected".

=== SPIKE ===
{json.dumps(state["spikes"][0] if state["spikes"] else {}, indent=2)}

=== DRILLDOWN (top 3 services) ===
{json.dumps(drilldown_rows, indent=2)}

=== ANOMALIES ===
{json.dumps(state["anomalies"], indent=2)}

=== CLOUDTRAIL ===
{cloudtrail_info}

Respond in this exact format (no extra text before or after):

## 6. Likely Root Cause

<2-4 sentences citing specific services, UsageTypes, and confidence level>

---

## 7. Remediation

<markdown checklist; include "Est. prevention: $X if root cause confirmed" where TotalImpact is available>
"""
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        if not _valid_llm_sections(text):
            print("[report] LLM output missing required headers -- falling back to template")
            return ""
        print("[report] LLM sections generated")
        return text
    except Exception as e:
        print(f"[report] LLM unavailable ({e.__class__.__name__}) -- falling back to template")
        return ""


def _node_report(state: AnalysisState) -> dict:
    llm_sections = _generate_interpretive_sections(state)
    render_report(
        state["spikes"],
        state["drilldown"],
        state["correlations"],
        state["anomalies"],
        state["cost_data"],
        state["output_paths"],
        state["work_dir"],
        llm_sections=llm_sections,
    )
    return {}


def build_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("load", _node_load)
    graph.add_node("detect", _node_detect)
    graph.add_node("drilldown", _node_drilldown)
    graph.add_node("correlate", _node_correlate)
    graph.add_node("report", _node_report)

    graph.set_entry_point("load")
    graph.add_edge("load", "detect")
    graph.add_edge("detect", "drilldown")
    graph.add_edge("drilldown", "correlate")
    graph.add_edge("correlate", "report")
    graph.add_edge("report", END)

    # No checkpointer: this is a sub-second linear pipeline, so checkpoint/resume
    # adds no value. When the slow --live paginated path or conditional branching
    # is added, wire a *durable* checkpointer (e.g. SqliteSaver) with a per-run
    # thread_id — an in-process MemorySaver would not survive process exit anyway.
    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    use_mock = "--live" not in sys.argv
    work_dir = os.path.dirname(os.path.abspath(__file__))
    # Support legacy execution if this file is copied under result/.
    if os.path.basename(work_dir) == "result":
        work_dir = os.path.dirname(work_dir)
    result_dir = os.path.join(work_dir, "result")
    output_paths = [
        os.path.join(result_dir, "finops_report.md"),
    ]

    print(f"[main] WORK_DIR : {work_dir}")
    print(f"[main] mode     : {'mock' if use_mock else 'live AWS'}")

    app = build_graph()
    app.invoke({
        "work_dir": work_dir,
        "use_mock": use_mock,
        "cost_data": [],
        "anomalies": [],
        "spikes": [],
        "drilldown": [],
        "correlations": [],
        "output_paths": output_paths,
    })
    print("[main] Done.")


if __name__ == "__main__":
    main()
