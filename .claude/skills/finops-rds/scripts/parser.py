#!/usr/bin/env python3
"""
parser.py — FinOps RDS Skill
Parses Terraform + metrics.json + cost_report.json and consolidates into parsed_input.json.
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
    Extracts aws_db_instance resource blocks from Terraform source.
    Returns: [{"resource_id": "db-prod", "instance_class": "db.r5.large",
               "multi_az": True, "environment": "dev", ...}, ...]
    """
    text = Path(tf_path).read_text(encoding="utf-8")
    resources = []

    pattern = re.compile(
        r'resource\s+"aws_db_instance"\s+"([^"]+)"\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        name = m.group(1)
        body = m.group(2)

        def extract(field: str, default="") -> str:
            hit = re.search(rf'{field}\s*=\s*"?([^"\n]+)"?', body)
            return hit.group(1).strip() if hit else default

        def extract_tag(tag: str, default="") -> str:
            # Match Name = "value" inside tags block
            tags_match = re.search(r'tags\s*=\s*\{([^}]+)\}', body, re.DOTALL)
            if not tags_match:
                return default
            hit = re.search(rf'{tag}\s*=\s*"([^"]+)"', tags_match.group(1))
            return hit.group(1).strip() if hit else default

        multi_az_raw = extract("multi_az", "false").lower()
        multi_az = multi_az_raw == "true"

        resources.append({
            "resource_id":              name,
            "identifier":               extract("identifier", name),
            "engine":                   extract("engine", "mysql"),
            "engine_version":           extract("engine_version", ""),
            "instance_class":           extract("instance_class", ""),
            "allocated_storage_gb":     extract("allocated_storage", "0"),
            "storage_type":             extract("storage_type", "gp2"),
            "multi_az":                 multi_az,
            "backup_retention_days":    extract("backup_retention_period", "0"),
            "environment":              extract_tag("Environment", "").lower(),
            "name_tag":                 extract_tag("Name", name),
        })

    if not resources:
        print(f"[parser] WARNING: No aws_db_instance resources found in {tf_path}", file=sys.stderr)

    return resources


# ── Region Extraction ──────────────────────────────────────────────

def extract_region(tf_text: str) -> str:
    m = re.search(r'provider\s+"aws"\s*\{[^}]*region\s*=\s*"([^"]+)"', tf_text, re.DOTALL)
    return m.group(1).strip() if m else "us-east-1"


# ── Metrics Parsing ────────────────────────────────────────────────

def parse_metrics(metrics_path: str) -> dict:
    """
    Reads metrics.json and returns aggregated statistics per resource.
    Supports the nested Format B used by RDS scenario files:
      {"resources": {"db-id": {"metrics": {"cpu_utilization": {"datapoints": [...]}}}}}
    """
    raw = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    aggregated: dict[str, dict] = {}

    if isinstance(raw, dict) and "resources" in raw:
        metadata = raw.get("metadata", {})
        period_days = metadata.get("period_days", 30)
        resolution  = metadata.get("resolution", "daily")
        points_per_day = 24 if resolution == "hourly" else 1

        for rid, rdata in raw["resources"].items():
            aggregated[rid] = {"resource_id": rid, "period_days": period_days}
            for metric_name, metric_data in rdata.get("metrics", {}).items():
                datapoints = metric_data.get("datapoints", [])
                if datapoints:
                    aggregated[rid][f"{metric_name}_avg"] = sum(datapoints) / len(datapoints)
                    aggregated[rid][f"{metric_name}_max"] = max(datapoints)
                    aggregated[rid][f"{metric_name}_min"] = min(datapoints)
                    daily = [
                        sum(datapoints[i : i + points_per_day])
                        for i in range(0, len(datapoints), points_per_day)
                    ]
                    aggregated[rid][f"{metric_name}_zero_days"] = sum(1 for d in daily if d == 0)
                else:
                    for suffix in ("_avg", "_max", "_min", "_zero_days"):
                        aggregated[rid][f"{metric_name}{suffix}"] = 0
        return aggregated

    # Format A: flat list
    items = raw if isinstance(raw, list) else raw.get("metrics", [])
    for item in items:
        rid    = item.get("resource_id") or item.get("name") or "unknown"
        metric = item.get("metric") or item.get("metric_name") or "unknown"
        values = item.get("values", [])
        if rid not in aggregated:
            aggregated[rid] = {"resource_id": rid, "period_days": item.get("period_days", 30)}
        if values:
            aggregated[rid][f"{metric}_avg"]       = sum(values) / len(values)
            aggregated[rid][f"{metric}_max"]       = max(values)
            aggregated[rid][f"{metric}_min"]       = min(values)
            aggregated[rid][f"{metric}_zero_days"] = sum(1 for v in values if v == 0)
        else:
            for suffix in ("_avg", "_max", "_min", "_zero_days"):
                aggregated[rid][f"{metric}{suffix}"] = 0

    return aggregated


# ── Cost Report Parsing ────────────────────────────────────────────

def parse_cost_report(cost_path: str) -> dict:
    raw    = json.loads(Path(cost_path).read_text(encoding="utf-8"))
    months = raw if isinstance(raw, list) else raw.get(
        "monthly", raw.get("months", raw.get("monthly_data", []))
    )

    if not months:
        return {"avg_rds_monthly": 0, "avg_total_monthly": 0, "months": [], "pricing_note": ""}

    rds_spends  = []
    total_spends = []
    for m in months:
        total_spends.append(m.get("total_spend_usd", m.get("total", 0)))
        for svc in m.get("services", []):
            if svc.get("service", "").upper() == "RDS":
                rds_spends.append(svc.get("spend_usd", 0))

    avg_rds   = sum(rds_spends)   / len(rds_spends)   if rds_spends   else 0
    avg_total = sum(total_spends) / len(total_spends)  if total_spends else 0

    return {
        "avg_rds_monthly":   round(avg_rds,   2),
        "avg_total_monthly": round(avg_total, 2),
        "months":            months,
        "pricing_note":      raw.get("summary", {}).get("pricing_note", ""),
    }


# ── Main ───────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="FinOps RDS Parser")
    ap.add_argument("--tf",      required=True, help="Path to main.tf")
    ap.add_argument("--metrics", required=True, help="Path to metrics.json")
    ap.add_argument("--cost",    required=True, help="Path to cost_report.json")
    ap.add_argument("--out",     default="parsed_input.json", help="Output file path")
    args = ap.parse_args()

    print(f"[parser] Terraform   → {args.tf}")
    tf_text      = Path(args.tf).read_text(encoding="utf-8")
    tf_resources = parse_terraform(args.tf)
    region       = extract_region(tf_text)
    print(f"[parser]   aws_db_instance resources found: {len(tf_resources)}, region: {region}")

    print(f"[parser] Metrics     → {args.metrics}")
    metrics = parse_metrics(args.metrics)
    print(f"[parser]   Metrics aggregated for: {len(metrics)} resources")

    print(f"[parser] Cost report → {args.cost}")
    cost = parse_cost_report(args.cost)
    print(f"[parser]   Avg Monthly RDS ${cost['avg_rds_monthly']} / Avg Total ${cost['avg_total_monthly']}")

    output = {
        "region":        region,
        "tf_resources":  tf_resources,
        "metrics":       metrics,
        "cost_summary":  cost,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parser] ✓ Output complete → {out_path}")


if __name__ == "__main__":
    main()
