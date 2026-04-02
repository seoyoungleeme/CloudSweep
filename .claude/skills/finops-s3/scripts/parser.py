#!/usr/bin/env python3
"""
parser.py — FinOps S3 Skill
Parses Terraform + metrics.json + cost_report.json into parsed_input.json.

Captures the relationship between:
  - aws_s3_bucket         (the bucket)
  - aws_s3_bucket_versioning (versioning configuration)
  - aws_s3_bucket_lifecycle_configuration (lifecycle rules, if any)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _extract_field(body: str, field: str, default: str = "") -> str:
    hit = re.search(rf'{field}\s*=\s*"([^"]+)"', body)
    return hit.group(1).strip() if hit else default


def _extract_tag(body: str, tag: str, default: str = "") -> str:
    tags_match = re.search(r'tags\s*=\s*\{([^}]+)\}', body, re.DOTALL)
    if not tags_match:
        return default
    hit = re.search(rf'{tag}\s*=\s*"([^"]+)"', tags_match.group(1))
    return hit.group(1).strip() if hit else default


def _resource_blocks(text: str, resource_type: str) -> list[tuple[str, str]]:
    """Returns list of (logical_name, body) tuples for a given resource type."""
    pattern = re.compile(
        rf'resource\s+"{re.escape(resource_type)}"\s+"([^"]+)"\s*\{{((?:[^{{}}]|\{{[^{{}}]*\}})*)\}}',
        re.DOTALL
    )
    return [(m.group(1), m.group(2)) for m in pattern.finditer(text)]


def parse_terraform(tf_path: str) -> list[dict]:
    """
    Parses all aws_s3_bucket resources and resolves:
      - versioning_status  (from aws_s3_bucket_versioning)
      - lifecycle_config_exists (from aws_s3_bucket_lifecycle_configuration)
      - lifecycle_has_noncurrent_expiry
    """
    text = Path(tf_path).read_text(encoding="utf-8")

    # --- aws_s3_bucket ---
    buckets: dict[str, dict] = {}
    for name, body in _resource_blocks(text, "aws_s3_bucket"):
        bucket_name = _extract_field(body, "bucket", name)
        buckets[name] = {
            "resource_id":          name,
            "bucket_name":          bucket_name,
            "environment":          _extract_tag(body, "Environment", "").lower()
                                    or _infer_env(bucket_name),
            "name_tag":             _extract_tag(body, "Name", bucket_name),
            "versioning_status":    "Disabled",    # resolved below
            "lifecycle_config_exists": False,      # resolved below
            "lifecycle_has_noncurrent_expiry": False,
        }

    if not buckets:
        print("[parser] WARNING: No aws_s3_bucket resources found", file=sys.stderr)
        return []

    # --- aws_s3_bucket_versioning ---
    for name, body in _resource_blocks(text, "aws_s3_bucket_versioning"):
        # Match by logical resource name prefix (convention: same suffix)
        target_bucket = _resolve_ref(body, "bucket", buckets)
        if target_bucket:
            status_match = re.search(r'status\s*=\s*"([^"]+)"', body)
            if status_match:
                buckets[target_bucket]["versioning_status"] = status_match.group(1)

    # --- aws_s3_bucket_lifecycle_configuration ---
    lifecycle_names = [name for name, _ in _resource_blocks(text, "aws_s3_bucket_lifecycle_configuration")]
    for name, body in _resource_blocks(text, "aws_s3_bucket_lifecycle_configuration"):
        target_bucket = _resolve_ref(body, "bucket", buckets)
        if target_bucket:
            buckets[target_bucket]["lifecycle_config_exists"] = True
            # Check for noncurrent_version_expiration rule
            has_ncv = bool(re.search(r'noncurrent_version_expiration', body))
            buckets[target_bucket]["lifecycle_has_noncurrent_expiry"] = has_ncv

    return list(buckets.values())


def _infer_env(bucket_name: str) -> str:
    """Infer environment from bucket name keywords."""
    name_lower = bucket_name.lower()
    for keyword in ("prod", "production"):
        if keyword in name_lower:
            return "prod"
    for keyword in ("staging", "stage", "stg"):
        if keyword in name_lower:
            return "staging"
    for keyword in ("dev", "development"):
        if keyword in name_lower:
            return "dev"
    for keyword in ("test", "testing", "qa"):
        if keyword in name_lower:
            return "test"
    return ""


def _resolve_ref(body: str, field: str, buckets: dict[str, dict]) -> str | None:
    """
    Resolve a Terraform reference like:
      bucket = aws_s3_bucket.my_bucket.id
      bucket = aws_s3_bucket.my_bucket.bucket
    to the logical bucket name (key in buckets dict).
    """
    # Reference pattern: aws_s3_bucket.<name>.<attr>
    ref_match = re.search(
        rf'{field}\s*=\s*aws_s3_bucket\.([a-zA-Z0-9_\-]+)\.',
        body
    )
    if ref_match:
        ref_name = ref_match.group(1)
        if ref_name in buckets:
            return ref_name
    # Fall back: same resource name suffix
    return None


def extract_region(tf_text: str) -> str:
    m = re.search(r'provider\s+"aws"\s*\{[^}]*region\s*=\s*"([^"]+)"', tf_text, re.DOTALL)
    return m.group(1).strip() if m else "us-east-1"


def parse_metrics(metrics_path: str) -> dict:
    """
    Aggregates storage_bytes and noncurrent_version_count per bucket.
    Also computes the slope (growth trend) of noncurrent_version_count.
    """
    raw = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    aggregated: dict[str, dict] = {}

    if isinstance(raw, dict) and "resources" in raw:
        metadata    = raw.get("metadata", {})
        period_days = metadata.get("period_days", 30)

        for rid, rdata in raw["resources"].items():
            aggregated[rid] = {"resource_id": rid, "period_days": period_days}
            for metric_name, metric_data in rdata.get("metrics", {}).items():
                dps = metric_data.get("datapoints", [])
                if not dps:
                    for sfx in ("_avg", "_max", "_min", "_slope"):
                        aggregated[rid][f"{metric_name}{sfx}"] = 0
                    continue

                aggregated[rid][f"{metric_name}_avg"] = sum(dps) / len(dps)
                aggregated[rid][f"{metric_name}_max"] = max(dps)
                aggregated[rid][f"{metric_name}_min"] = min(dps)

                # Linear slope: (last - first) / num_points — positive = growing
                slope = (dps[-1] - dps[0]) / len(dps) if len(dps) > 1 else 0
                aggregated[rid][f"{metric_name}_slope"]         = round(slope, 6)
                aggregated[rid][f"{metric_name}_first"]         = dps[0]
                aggregated[rid][f"{metric_name}_last"]          = dps[-1]
                aggregated[rid][f"{metric_name}_total_growth"]  = round(dps[-1] - dps[0], 4)

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
            aggregated[rid][f"{metric}_avg"]   = sum(values) / len(values)
            aggregated[rid][f"{metric}_max"]   = max(values)
            aggregated[rid][f"{metric}_min"]   = min(values)
            slope = (values[-1] - values[0]) / len(values) if len(values) > 1 else 0
            aggregated[rid][f"{metric}_slope"] = round(slope, 6)
            aggregated[rid][f"{metric}_last"]  = values[-1]
            aggregated[rid][f"{metric}_first"] = values[0]

    return aggregated


def parse_cost_report(cost_path: str) -> dict:
    raw    = json.loads(Path(cost_path).read_text(encoding="utf-8"))
    months = raw if isinstance(raw, list) else raw.get(
        "monthly", raw.get("months", raw.get("monthly_data", []))
    )

    if not months:
        return {"avg_s3_monthly": 0, "avg_total_monthly": 0, "months": [], "pricing_note": ""}

    s3_spends    = []
    total_spends = []
    for m in months:
        total_spends.append(m.get("total_spend_usd", m.get("total", 0)))
        for svc in m.get("services", []):
            if svc.get("service", "").upper() == "S3":
                s3_spends.append(svc.get("spend_usd", 0))

    avg_s3    = sum(s3_spends)   / len(s3_spends)   if s3_spends   else 0
    avg_total = sum(total_spends) / len(total_spends) if total_spends else 0

    # Try to extract noncurrent storage GB and cost from pricing_note.
    # Handles formats like:
    #   "10 TB noncurrent × $0.023/GB = 10,240 GB × $0.023 ≈ $235 → ~$230/mo"
    #   "5,120 GB × $0.023 ≈ $117/mo"
    pricing_note = raw.get("summary", {}).get("pricing_note", "")
    noncurrent_gb   = None
    noncurrent_cost = None

    # GB: prefer explicit GB figure; fall back to TB × 1024
    m_gb = re.search(r'([\d,]+)\s*GB', pricing_note)
    m_tb = re.search(r'([\d.]+)\s*TB', pricing_note)
    if m_gb:
        noncurrent_gb = float(m_gb.group(1).replace(",", ""))
    elif m_tb:
        noncurrent_gb = round(float(m_tb.group(1)) * 1024, 2)

    # Cost: handles ~$230/mo, ≈$235/mo, → ~$230/mo, $230/mo
    m_cost = re.search(r'[~≈→\s]*\$\s*([\d.]+)\s*/?\s*mo', pricing_note)
    if m_cost:
        noncurrent_cost = float(m_cost.group(1))

    return {
        "avg_s3_monthly":        round(avg_s3,    2),
        "avg_total_monthly":     round(avg_total, 2),
        "months":                months,
        "pricing_note":          pricing_note,
        "noncurrent_storage_gb": noncurrent_gb,
        "noncurrent_cost_usd":   noncurrent_cost,
    }


def main():
    ap = argparse.ArgumentParser(description="FinOps S3 Parser")
    ap.add_argument("--tf",      required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--cost",    required=True)
    ap.add_argument("--out",     default="parsed_input.json")
    args = ap.parse_args()

    print(f"[parser] Terraform   → {args.tf}")
    tf_text      = Path(args.tf).read_text(encoding="utf-8")
    tf_resources = parse_terraform(args.tf)
    region       = extract_region(tf_text)
    print(f"[parser]   aws_s3_bucket resources: {len(tf_resources)}, region: {region}")
    for b in tf_resources:
        print(f"[parser]   {b['resource_id']:30s}  versioning={b['versioning_status']:10s}  "
              f"lifecycle={b['lifecycle_config_exists']}")

    print(f"[parser] Metrics     → {args.metrics}")
    metrics = parse_metrics(args.metrics)
    print(f"[parser]   Metrics aggregated for: {len(metrics)} resources")

    print(f"[parser] Cost report → {args.cost}")
    cost = parse_cost_report(args.cost)
    print(f"[parser]   Avg Monthly S3 ${cost['avg_s3_monthly']} / "
          f"Noncurrent storage: {cost.get('noncurrent_storage_gb')} GB "
          f"(~${cost.get('noncurrent_cost_usd')}/mo)")

    output = {
        "region":       region,
        "tf_resources": tf_resources,
        "metrics":      metrics,
        "cost_summary": cost,
    }

    out_path = Path(args.out)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[parser] ✓ Output complete → {out_path}")


if __name__ == "__main__":
    main()
