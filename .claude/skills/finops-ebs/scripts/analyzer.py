#!/usr/bin/env python3
"""
analyzer.py — FinOps EBS Skill
Applies orphaned snapshot rules to parsed_input.json → findings.json.

Rule S1: aws_ebs_snapshot with SourceVolumeStatus=deleted → orphaned → DELETE
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# EBS snapshot storage pricing (USD per GB-month)
SNAPSHOT_PRICING: dict[str, float] = {
    "us-east-1":      0.05,
    "us-east-2":      0.05,
    "us-west-1":      0.05,
    "us-west-2":      0.05,
    "ca-central-1":   0.05,
    "ap-northeast-1": 0.05,
    "ap-northeast-2": 0.05,
    "ap-southeast-1": 0.05,
    "ap-southeast-2": 0.055,
    "ap-south-1":     0.05,
    "eu-west-1":      0.05,
    "eu-west-2":      0.05,
    "eu-central-1":   0.05,
    "sa-east-1":      0.05,
}
DEFAULT_REGION = "us-east-1"


def get_price_per_gb(region: str) -> float:
    return SNAPSHOT_PRICING.get(region, SNAPSHOT_PRICING[DEFAULT_REGION])


def load_rules(rules_path: str) -> dict:
    return json.loads(Path(rules_path).read_text(encoding="utf-8"))


def analyze_resource(resource: dict, metrics: dict, rules: dict, price_per_gb: float) -> dict | None:
    """Returns a finding if the snapshot is orphaned, else None."""
    rid                  = resource["resource_id"]
    source_vol_status    = resource.get("source_volume_status", "").lower()

    thresholds           = rules.get("thresholds", {})
    orphan_tag_key       = thresholds.get("orphaned_tag_key", "SourceVolumeStatus")
    orphan_tag_value     = thresholds.get("orphaned_tag_value", "deleted").lower()

    # Rule S1: source volume deleted → orphaned snapshot
    if source_vol_status != orphan_tag_value:
        return None

    m           = metrics.get(rid, {})
    storage_gb  = m.get("storage_gb_avg", 0.0)
    period_days = m.get("period_days", 30)

    monthly_cost = round(storage_gb * price_per_gb, 4)
    annual_cost  = round(monthly_cost * 12, 4)

    return {
        "rule_id":       "S1",
        "resource_id":   rid,
        "resource_type": "aws_ebs_snapshot",
        "verdict":       f"Orphaned snapshot — source volume is deleted, storing {storage_gb:.1f} GB with no active purpose",
        "severity":      "HIGH",
        "action":        "DELETE",
        "saving_type":   "confirmed",
        "confidence":    "HIGH",
        "metrics_summary": {
            "storage_gb":   round(storage_gb, 2),
            "period_days":  period_days,
        },
        "root_cause": (
            f"`{rid}` has `SourceVolumeStatus = deleted`. "
            "The EBS volume this snapshot was created from has been terminated, "
            "but the snapshot was never cleaned up. "
            f"It is storing {storage_gb:.1f} GB of data for a non-existent volume, "
            f"costing ${monthly_cost:.4f}/month with zero operational value."
        ),
        "remediation": (
            f"1. Verify no AMI references this snapshot:\n"
            f"   aws ec2 describe-images --filters Name=block-device-mapping.snapshot-id,Values=<snapshot-id>\n"
            f"2. Delete via AWS CLI:\n"
            f"   aws ec2 delete-snapshot --snapshot-id <snapshot-id>\n"
            f"3. Or remove from Terraform state and run terraform apply:\n"
            f"   terraform state rm aws_ebs_snapshot.{rid}\n"
            f"4. Automate: enable AWS Data Lifecycle Manager or use a Lambda to clean up\n"
            f"   snapshots whose source volumes no longer exist."
        ),
        "source_volume_id":              resource.get("volume_id", "unknown"),
        "estimated_monthly_saving_usd":  monthly_cost,
        "estimated_annual_saving_usd":   annual_cost,
    }


def main():
    ap = argparse.ArgumentParser(description="FinOps EBS Analyzer")
    ap.add_argument("--input",  default="parsed_input.json")
    ap.add_argument("--rules",  default="rules/orphaned_snapshot.json")
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
    print(f"[analyzer] Region: {region} / Snapshot price: ${price_per_gb}/GB-month")
    print(f"[analyzer] Resources to analyze: {len(tf_resources)}")

    findings: list[dict] = []
    ok_count = 0
    for resource in tf_resources:
        result = analyze_resource(resource, metrics, rules, price_per_gb)
        if result:
            findings.append(result)
        else:
            ok_count += 1

    total_monthly_raw = round(sum(f["estimated_monthly_saving_usd"] for f in findings), 2)
    total_storage     = round(sum(f["metrics_summary"]["storage_gb"] for f in findings), 2)

    # Cap savings at actual avg EBS spend from cost report.
    # Per-snapshot GB estimates can be synthetic/inflated; the real bill is the ceiling.
    avg_ebs_monthly = cost_summary.get("avg_ebs_monthly", None)
    if avg_ebs_monthly and total_monthly_raw > avg_ebs_monthly:
        cap_ratio = avg_ebs_monthly / total_monthly_raw
        for f in findings:
            f["estimated_monthly_saving_usd"] = round(f["estimated_monthly_saving_usd"] * cap_ratio, 4)
            f["estimated_annual_saving_usd"]  = round(f["estimated_monthly_saving_usd"] * 12, 4)
        total_monthly = round(avg_ebs_monthly, 2)
        savings_capped = True
    else:
        total_monthly = total_monthly_raw
        savings_capped = False
    total_annual = round(total_monthly * 12, 2)

    print(f"[analyzer]   Orphaned: {len(findings)} / OK: {ok_count}")
    print(f"[analyzer]   Total orphaned storage: {total_storage} GB")
    if savings_capped:
        print(f"[analyzer]   GB-based estimate: ${total_monthly_raw} → capped at avg_ebs_monthly: ${total_monthly}")
    print(f"[analyzer]   Total confirmed monthly savings: ${total_monthly}")

    output = {
        "analyzed_at":                        datetime.utcnow().isoformat() + "Z",
        "region":                             region,
        "snapshot_price_per_gb_usd":          price_per_gb,
        "total_resources_checked":            len(tf_resources),
        "findings_count":                     len(findings),
        "total_orphaned_storage_gb":          total_storage,
        "total_estimated_monthly_saving_usd": total_monthly,
        "total_estimated_annual_saving_usd":  total_annual,
        "savings_capped_at_ebs_spend":        savings_capped,
        "cost_summary":                       cost_summary,
        "findings":                           findings,
    }

    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyzer] Done → {args.out}")


if __name__ == "__main__":
    main()
