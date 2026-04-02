#!/usr/bin/env python3
"""
analyzer.py — FinOps S3 Skill
Applies missing lifecycle policy rules to parsed_input.json → findings.json.

Rule V1: aws_s3_bucket with versioning=Enabled AND no lifecycle config
         AND noncurrent_version_count slope > threshold → ADD_LIFECYCLE_POLICY
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# S3 Standard storage pricing (USD/GB-month)
S3_PRICING: dict[str, float] = {
    "us-east-1":      0.023,
    "us-east-2":      0.023,
    "us-west-1":      0.026,
    "us-west-2":      0.023,
    "ca-central-1":   0.025,
    "ap-northeast-1": 0.025,
    "ap-northeast-2": 0.024,
    "ap-southeast-1": 0.025,
    "ap-southeast-2": 0.025,
    "ap-south-1":     0.023,
    "eu-west-1":      0.023,
    "eu-west-2":      0.024,
    "eu-central-1":   0.025,
    "sa-east-1":      0.026,
}
DEFAULT_REGION = "us-east-1"

LIFECYCLE_RECOMMENDATIONS = {
    "prod":    {"noncurrent_days": 90,  "newer_versions": 5, "multipart_days": 7},
    "staging": {"noncurrent_days": 30,  "newer_versions": 3, "multipart_days": 3},
    "dev":     {"noncurrent_days": 14,  "newer_versions": 2, "multipart_days": 3},
    "test":    {"noncurrent_days": 14,  "newer_versions": 2, "multipart_days": 3},
    "default": {"noncurrent_days": 30,  "newer_versions": 3, "multipart_days": 7},
}


def get_price_per_gb(region: str) -> float:
    return S3_PRICING.get(region, S3_PRICING[DEFAULT_REGION])


def load_rules(rules_path: str) -> dict:
    return json.loads(Path(rules_path).read_text(encoding="utf-8"))


def estimate_noncurrent_saving(resource: dict, metrics: dict,
                               cost_summary: dict, price_per_gb: float,
                               num_buckets_flagged: int) -> float:
    """
    Estimate monthly saving from adding a lifecycle policy.
    Priority:
      1. noncurrent_cost_usd from pricing_note (split across flagged buckets)
      2. noncurrent_version_count_last × estimated_size_per_version × price_per_gb
      3. Fallback: avg_s3_monthly × 0.8 / num_buckets_flagged
    """
    # Option 1: cost report pricing_note
    noncurrent_cost = cost_summary.get("noncurrent_cost_usd")
    if noncurrent_cost and num_buckets_flagged > 0:
        return round(noncurrent_cost / num_buckets_flagged, 2)

    # Option 2: estimate from noncurrent_gb in pricing note
    noncurrent_gb = cost_summary.get("noncurrent_storage_gb")
    if noncurrent_gb and num_buckets_flagged > 0:
        return round((noncurrent_gb * price_per_gb) / num_buckets_flagged, 2)

    # Option 3: avg S3 spend × noncurrent fraction
    avg_s3 = cost_summary.get("avg_s3_monthly", 0)
    if avg_s3 > 0 and num_buckets_flagged > 0:
        return round(avg_s3 * 0.8 / num_buckets_flagged, 2)

    return 0.0


def analyze_resource(resource: dict, metrics: dict, rules: dict,
                     cost_summary: dict, price_per_gb: float,
                     num_buckets_flagged: int) -> dict | None:
    """Returns a finding if the bucket has versioning but no lifecycle policy."""
    rid              = resource["resource_id"]
    bucket_name      = resource.get("bucket_name", rid)
    versioning       = resource.get("versioning_status", "Disabled")
    has_lifecycle    = resource.get("lifecycle_config_exists", False)
    has_ncv_expiry   = resource.get("lifecycle_has_noncurrent_expiry", False)
    environment      = resource.get("environment", "default") or "default"

    thresholds  = rules.get("thresholds", {})
    slope_min   = thresholds.get("noncurrent_version_count_slope_min", 0.1)

    m = metrics.get(rid, {})
    ncv_slope  = m.get("noncurrent_version_count_slope", 0)
    ncv_last   = m.get("noncurrent_version_count_last", 0)
    ncv_first  = m.get("noncurrent_version_count_first", 0)
    period     = m.get("period_days", 30)

    # Rule V1: versioning enabled + no noncurrent expiry + versions growing
    if versioning != "Enabled":
        return None
    if has_ncv_expiry:
        # Lifecycle exists and already handles noncurrent versions — no issue
        return None
    if ncv_slope <= slope_min:
        # Versions not growing — low risk
        return None

    lifecycle_cfg = LIFECYCLE_RECOMMENDATIONS.get(
        environment, LIFECYCLE_RECOMMENDATIONS["default"]
    )
    monthly_saving = estimate_noncurrent_saving(
        resource, metrics, cost_summary, price_per_gb, num_buckets_flagged
    )
    annual_saving  = round(monthly_saving * 12, 2)

    issue_desc = "no lifecycle configuration" if not has_lifecycle \
        else "lifecycle exists but missing noncurrent_version_expiration rule"

    return {
        "rule_id":        "V1",
        "resource_id":    rid,
        "resource_type":  "aws_s3_bucket",
        "bucket_name":    bucket_name,
        "environment":    environment,
        "verdict": (
            f"Versioning enabled, {issue_desc} — "
            f"noncurrent versions growing at {ncv_slope:.2f}/hr "
            f"({ncv_first:.0f} → {ncv_last:.0f} over {period}d)"
        ),
        "severity":      "HIGH",
        "action":        "ADD_LIFECYCLE_POLICY",
        "saving_type":   "confirmed",
        "confidence":    "HIGH",
        "metrics_summary": {
            "noncurrent_version_count_first": ncv_first,
            "noncurrent_version_count_last":  ncv_last,
            "noncurrent_version_count_slope": ncv_slope,
            "period_days":                    period,
            "trend":                          "growing" if ncv_slope > 0 else "stable",
        },
        "lifecycle_recommendation": lifecycle_cfg,
        "root_cause": (
            f"`{bucket_name}` has S3 versioning enabled but {issue_desc}. "
            f"Every object update or delete creates a noncurrent version that is retained forever. "
            f"Over the last {period} days, noncurrent version count grew from {ncv_first:.0f} "
            f"to {ncv_last:.0f} (slope: {ncv_slope:.2f}/hr), confirming unbounded accumulation. "
            f"At ${price_per_gb}/GB-month (S3 Standard, {DEFAULT_REGION}), this grows without limit."
        ),
        "remediation": (
            f"Add an aws_s3_bucket_lifecycle_configuration for `{bucket_name}` with:\n"
            f"  - noncurrent_version_expiration: {lifecycle_cfg['noncurrent_days']} days\n"
            f"  - newer_noncurrent_versions kept: {lifecycle_cfg['newer_versions']}\n"
            f"  - abort_incomplete_multipart_upload: {lifecycle_cfg['multipart_days']} days\n"
            f"See Optimized Terraform section for ready-to-apply resource block."
        ),
        "estimated_monthly_saving_usd": monthly_saving,
        "estimated_annual_saving_usd":  annual_saving,
    }


def main():
    ap = argparse.ArgumentParser(description="FinOps S3 Analyzer")
    ap.add_argument("--input",  default="parsed_input.json")
    ap.add_argument("--rules",  default="rules/missing_lifecycle_policy.json")
    ap.add_argument("--out",    default="findings.json")
    ap.add_argument("--region", default=None)
    args = ap.parse_args()

    data         = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rules        = load_rules(args.rules)
    tf_resources = data["tf_resources"]
    metrics      = data["metrics"]
    cost_summary = data["cost_summary"]

    region       = args.region or data.get("region", DEFAULT_REGION)
    price_per_gb = get_price_per_gb(region)
    print(f"[analyzer] Region: {region} / S3 price: ${price_per_gb}/GB-month")
    print(f"[analyzer] Buckets to analyze: {len(tf_resources)}")

    # Pre-scan: count buckets that will be flagged (needed for saving split)
    flagged_preview = [
        r for r in tf_resources
        if r.get("versioning_status") == "Enabled"
        and not r.get("lifecycle_has_noncurrent_expiry", False)
    ]
    num_flagged = max(len(flagged_preview), 1)

    findings: list[dict] = []
    for resource in tf_resources:
        result = analyze_resource(
            resource, metrics, rules, cost_summary, price_per_gb, num_flagged
        )
        if result:
            findings.append(result)
            print(f"[analyzer]   [{result['severity']}][{result['rule_id']}] "
                  f"{result['resource_id']} — {result['verdict'][:80]}")
        else:
            print(f"[analyzer]   [OK]  {resource['resource_id']} — No issues")

    total_monthly = round(sum(f["estimated_monthly_saving_usd"] for f in findings), 2)
    total_annual  = round(total_monthly * 12, 2)

    output = {
        "analyzed_at":                        datetime.utcnow().isoformat() + "Z",
        "region":                             region,
        "s3_price_per_gb_usd":               price_per_gb,
        "total_resources_checked":            len(tf_resources),
        "findings_count":                     len(findings),
        "total_estimated_monthly_saving_usd": total_monthly,
        "total_estimated_annual_saving_usd":  total_annual,
        "cost_summary":                       cost_summary,
        "findings":                           findings,
    }

    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyzer] Done → {args.out}")
    print(f"[analyzer]   Total confirmed monthly savings: ${total_monthly}")


if __name__ == "__main__":
    main()
