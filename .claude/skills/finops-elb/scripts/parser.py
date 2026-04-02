#!/usr/bin/env python3
"""
parser.py — FinOps ELB Skill
Parses Terraform + metrics.json + cost_report.json and consolidates them into parsed_input.json.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── Terraform Parsing ──────────────────────────────────────────────

def parse_terraform(tf_path: str) -> list[dict]:
    """
    Extracts aws_lb resource blocks from terraform source.
    Returns: [{"resource_id": "lb-4dzo8v", "type": "application", "internal": False, ...}, ...]
    """
    text = Path(tf_path).read_text(encoding="utf-8")
    resources = []

    # Match resource "aws_lb" "<name>" { ... } blocks
    pattern = re.compile(
        r'resource\s+"aws_(?:lb|alb)"\s+"([^"]+)"\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        name = m.group(1)
        body = m.group(2)

        def extract(field: str, default=""):
            hit = re.search(rf'{field}\s*=\s*"?([^"\n]+)"?', body)
            return hit.group(1).strip() if hit else default

        resources.append({
            "resource_id": name,
            "lb_type": extract("load_balancer_type", "application"),
            "internal": extract("internal", "false").lower() == "true",
            "name_tag": extract('Name', name),
        })

    if not resources:
        print(f"[parser] WARNING: No aws_lb/aws_alb resources found in — {tf_path}", file=sys.stderr)

    return resources


# ── Region Extraction ──────────────────────────────────────────────

def extract_region(tf_text: str) -> str:
    """Extracts AWS region from provider block. Defaults to us-east-1."""
    m = re.search(r'provider\s+"aws"\s*\{[^}]*region\s*=\s*"([^"]+)"', tf_text, re.DOTALL)
    return m.group(1).strip() if m else "us-east-1"


# ── Metrics Parsing ────────────────────────────────────────────────

def parse_metrics(metrics_path: str) -> dict:
    """
    Reads metrics.json and returns aggregated statistics per resource.

    Supported formats:

    Format A — list or {"metrics": [...]}:
      [{"resource_id": "lb-4dzo8v", "metric": "request_count",
        "values": [0, 0, ...], "period_days": 30}, ...]

    Format B — nested resources dict (hourly or daily datapoints):
      {"metadata": {"period_days": 30, "resolution": "hourly"},
       "resources": {
         "lb-4dzo8v": {
           "metrics": {
             "request_count": {"datapoints": [0.0, ...]},
             ...
           }
         }
       }}
    """
    raw = json.loads(Path(metrics_path).read_text(encoding="utf-8"))

    aggregated: dict[str, dict] = {}

    # Format B: {"resources": {"lb-id": {"metrics": {"name": {"datapoints": [...]}}}}}
    if isinstance(raw, dict) and "resources" in raw and isinstance(raw["resources"], dict):
        metadata = raw.get("metadata", {})
        period_days = metadata.get("period_days", 30)
        resolution = metadata.get("resolution", "daily")
        points_per_day = 24 if resolution == "hourly" else 1

        for rid, rdata in raw["resources"].items():
            aggregated[rid] = {"resource_id": rid, "period_days": period_days}
            for metric_name, metric_data in rdata.get("metrics", {}).items():
                datapoints = metric_data.get("datapoints", [])
                if datapoints:
                    aggregated[rid][f"{metric_name}_avg"] = sum(datapoints) / len(datapoints)
                    aggregated[rid][f"{metric_name}_max"] = max(datapoints)
                    aggregated[rid][f"{metric_name}_min"] = min(datapoints)
                    daily = [sum(datapoints[i:i + points_per_day])
                             for i in range(0, len(datapoints), points_per_day)]
                    aggregated[rid][f"{metric_name}_zero_days"] = sum(1 for d in daily if d == 0)
                else:
                    aggregated[rid][f"{metric_name}_avg"] = 0
                    aggregated[rid][f"{metric_name}_max"] = 0
                    aggregated[rid][f"{metric_name}_min"] = 0
                    aggregated[rid][f"{metric_name}_zero_days"] = 0
        return aggregated

    # Format A: list or {"metrics": [...]}
    items = raw if isinstance(raw, list) else raw.get("metrics", [])
    for item in items:
        rid = item.get("resource_id") or item.get("name") or "unknown"
        metric = item.get("metric") or item.get("metric_name") or "unknown"
        values = item.get("values", [])

        if rid not in aggregated:
            aggregated[rid] = {"resource_id": rid, "period_days": item.get("period_days", 30)}

        if values:
            aggregated[rid][f"{metric}_avg"] = sum(values) / len(values)
            aggregated[rid][f"{metric}_max"] = max(values)
            aggregated[rid][f"{metric}_min"] = min(values)
            aggregated[rid][f"{metric}_zero_days"] = sum(1 for v in values if v == 0)
            aggregated[rid][f"{metric}_values"] = values
        else:
            aggregated[rid][f"{metric}_avg"] = 0
            aggregated[rid][f"{metric}_max"] = 0
            aggregated[rid][f"{metric}_min"] = 0
            aggregated[rid][f"{metric}_zero_days"] = 0

    return aggregated


# ── Cost Report Parsing ────────────────────────────────────────────

def parse_cost_report(cost_path: str) -> dict:
    """
    Reads cost_report.json and computes summary statistics.
    Expected structure:
      { "monthly": [ {"month": "M-5", "total": 214.44, "waste": 32.73}, ... ] }
    """
    raw = json.loads(Path(cost_path).read_text(encoding="utf-8"))
    months = raw if isinstance(raw, list) else raw.get("monthly", raw.get("months", raw.get("monthly_data", [])))

    if not months:
        return {"avg_total": 0, "avg_waste": 0, "avg_waste_pct": 0, "months": []}

    totals = [m.get("total", m.get("total_cost", m.get("total_spend_usd", 0))) for m in months]
    wastes = [m.get("waste", m.get("waste_cost", m.get("waste_usd", 0))) for m in months]

    avg_total = sum(totals) / len(totals)
    avg_waste = sum(wastes) / len(wastes)
    avg_waste_pct = (avg_waste / avg_total * 100) if avg_total else 0

    return {
        "avg_total": round(avg_total, 2),
        "avg_waste": round(avg_waste, 2),
        "avg_waste_pct": round(avg_waste_pct, 1),
        "months": months,
    }


# ── Main ───────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="FinOps ELB Parser")
    ap.add_argument("--tf",      required=True, help="Path to main.tf")
    ap.add_argument("--metrics", required=True, help="Path to metrics.json")
    ap.add_argument("--cost",    required=True, help="Path to cost_report.json")
    ap.add_argument("--out",     default="parsed_input.json", help="Output file path")
    args = ap.parse_args()

    print(f"[parser] Terraform  → {args.tf}")
    tf_text = Path(args.tf).read_text(encoding="utf-8")
    tf_resources = parse_terraform(args.tf)
    region = extract_region(tf_text)
    print(f"[parser]   aws_lb/aws_alb resources found: {len(tf_resources)}, region: {region}")

    print(f"[parser] Metrics    → {args.metrics}")
    metrics = parse_metrics(args.metrics)
    print(f"[parser]   Metrics aggregated for: {len(metrics)} resources")

    print(f"[parser] Cost report→ {args.cost}")
    cost = parse_cost_report(args.cost)
    print(f"[parser]   Avg Monthly Cost ${cost['avg_total']} / Avg Monthly Waste ${cost['avg_waste']}")

    output = {
        "region": region,
        "tf_resources": tf_resources,
        "metrics": metrics,
        "cost_summary": cost,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parser] ✓ Output complete → {out_path}")


if __name__ == "__main__":
    main()
