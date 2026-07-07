"""Cost anomaly parsing and spike detection for CloudSweep."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .rule_engine import stable_id


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _load_cost_and_usage(files: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in files:
        data = _load_json(Path(file_name))
        rows.extend(data.get("ResultsByTime", []))
    return sorted(rows, key=lambda row: row.get("TimePeriod", {}).get("Start", ""))


def _cost_amount(row: dict[str, Any]) -> float:
    return float(row.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0.0))


def _group_amounts(row: dict[str, Any]) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for group in row.get("Groups", []):
        key = " / ".join(group.get("Keys", []))
        amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0.0))
        amounts[key] = amount
    return amounts


def _detect_spikes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spikes: list[dict[str, Any]] = []
    costs = [_cost_amount(row) for row in rows]
    for idx, row in enumerate(rows):
        prior = costs[max(0, idx - 6):idx]
        if not prior:
            continue
        baseline_mean = statistics.mean(prior)
        baseline_stddev = statistics.pstdev(prior) if len(prior) > 1 else 0.0
        current = costs[idx]
        prev = costs[idx - 1]
        flags = []
        if current > baseline_mean + 2 * baseline_stddev:
            flags.append("statistical")
        if prev and ((current - prev) / prev) > 1.0:
            flags.append("pct_change")
        if flags:
            spikes.append(
                {
                    "timestamp": row.get("TimePeriod", {}).get("Start"),
                    "cost": round(current, 2),
                    "baseline_mean": round(baseline_mean, 2),
                    "baseline_stddev": round(baseline_stddev, 2),
                    "flags": flags,
                }
            )
    return spikes


def _drilldown(rows: list[dict[str, Any]], spikes: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ts = {row.get("TimePeriod", {}).get("Start"): row for row in rows}
    anomaly_usage = {
        item.get("DimensionValue"): [
            cause.get("UsageType")
            for cause in item.get("RootCauses", [])
            if cause.get("UsageType")
        ]
        for item in anomalies
    }
    result: list[dict[str, Any]] = []
    for spike in spikes:
        row = by_ts.get(spike["timestamp"])
        if not row:
            continue
        current = _group_amounts(row)
        ranked = sorted(current.items(), key=lambda item: item[1], reverse=True)
        result.append(
            {
                "timestamp": spike["timestamp"],
                "services": [
                    {
                        "service": service,
                        "spike_cost": round(amount, 2),
                        "usage_types": anomaly_usage.get(service, []),
                    }
                    for service, amount in ranked[:5]
                ],
            }
        )
    return result


def analyze_cost_anomaly(evidence: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    rows = _load_cost_and_usage(evidence.get("cost_explorer", []))
    anomalies = []
    if evidence.get("anomalies"):
        anomalies = _load_json(Path(evidence["anomalies"])).get("Anomalies", [])

    spikes = _detect_spikes(rows) if rows else []
    return {
        "datapoints": len(rows),
        "spikes": spikes,
        "drilldown": _drilldown(rows, spikes, anomalies),
        "anomalies": anomalies,
        "cloudtrail_available": bool(evidence.get("cloudtrail")),
        "confidence": {
            "spike_detection": "HIGH" if spikes else "NOT_APPLICABLE",
            "service_attribution": "HIGH" if anomalies else ("MEDIUM" if spikes else "NOT_APPLICABLE"),
            "triggering_event": "MEDIUM" if evidence.get("cloudtrail") else "LOW",
        },
        "fact_ids": [stable_id(run_id, "anomaly", spike.get("timestamp"), spike.get("cost")) for spike in spikes],
    }

