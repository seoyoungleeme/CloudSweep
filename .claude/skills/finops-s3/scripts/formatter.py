#!/usr/bin/env python3
"""
formatter.py — FinOps S3 Skill
Reads findings.json → finops_report.md + main_optimized.tf.

Unlike ELB/RDS/EBS skills, the fix here is ADDING a resource (lifecycle policy),
not deleting or modifying one. main_optimized.tf = original + new lifecycle blocks.
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEVERITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
ACTION_LABEL  = {"ADD_LIFECYCLE_POLICY": "Add S3 Lifecycle Policy"}


def lifecycle_tf_block(finding: dict) -> str:
    """Generates a ready-to-apply aws_s3_bucket_lifecycle_configuration block."""
    rid         = finding["resource_id"]
    bucket_name = finding["bucket_name"]
    cfg         = finding["lifecycle_recommendation"]
    ndays       = cfg["noncurrent_days"]
    nversions   = cfg["newer_versions"]
    mpart_days  = cfg["multipart_days"]
    env         = finding.get("environment", "default")

    lines = [
        f'# Lifecycle policy for {bucket_name} ({env})',
        f'# Expires noncurrent versions after {ndays} days, keeps {nversions} newest',
        f'resource "aws_s3_bucket_lifecycle_configuration" "{rid}" {{',
        f'  bucket = aws_s3_bucket.{rid}.id',
        f'',
        f'  rule {{',
        f'    id     = "expire-noncurrent-versions"',
        f'    status = "Enabled"',
        f'',
        f'    noncurrent_version_expiration {{',
        f'      noncurrent_days           = {ndays}',
        f'      newer_noncurrent_versions = {nversions}',
        f'    }}',
        f'',
        f'    abort_incomplete_multipart_upload {{',
        f'      days_after_initiation = {mpart_days}',
        f'    }}',
        f'  }}',
        f'}}',
    ]
    return "\n".join(lines)


def render_report(data: dict) -> str:
    findings      = data["findings"]
    cost_summary  = data.get("cost_summary", {})
    total_save    = data["total_estimated_monthly_saving_usd"]
    annual_save   = data["total_estimated_annual_saving_usd"]
    analyzed_at   = data.get("analyzed_at", "N/A")
    region        = data.get("region", "us-east-1")
    price_per_gb  = data.get("s3_price_per_gb_usd", 0.023)
    pricing_note  = cost_summary.get("pricing_note", "")

    lines = []

    # ── Header ──────────────────────────────────────────────────────
    lines += [
        "# FinOps S3 Analysis Report",
        "",
        f"- **Analysis Date/Time**: {analyzed_at}",
        f"- **Region**: {region}",
        f"- **Buckets Checked**: {data['total_resources_checked']}",
        f"- **Issues Found**: {data['findings_count']}",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Region | {region} |",
        f"| Buckets Checked | {data['total_resources_checked']} |",
        f"| Issues Found | {data['findings_count']} |",
        f"| Root Cause | Versioning enabled, no noncurrent version lifecycle policy |",
        f"| Confirmed Monthly Savings | **${total_save:.2f}** |",
        f"| Confirmed Annual Savings | **${annual_save:.2f}** |",
        f"| Avg Monthly S3 Spend | ${cost_summary.get('avg_s3_monthly', 'N/A')} |",
        "",
    ]
    if pricing_note:
        lines += [f"> **Cost Evidence**: {pricing_note}", ""]

    if not findings:
        lines += ["> ✅ No S3 lifecycle policy issues found.", ""]
        return "\n".join(lines)

    # ── Discovered Cost Issues ───────────────────────────────────────
    lines += ["## Discovered Cost Issues", ""]
    for i, f in enumerate(findings, 1):
        icon      = SEVERITY_ICON.get(f["severity"], "⚪")
        action    = ACTION_LABEL.get(f["action"], f["action"])
        cfg       = f["lifecycle_recommendation"]
        ms        = f["metrics_summary"]

        lines += [
            f"### {i}. {icon} `{f['bucket_name']}` (`{f['resource_id']}`) — {f['severity']}",
            "",
            f"**Verdict**: {f['verdict']}  ",
            f"**Recommended Action**: {action}  ",
            f"**Confidence**: {f['confidence']}  ",
            f"**Environment**: `{f.get('environment', 'unknown')}`",
            "",
            "**Noncurrent Version Growth (30 Days)**",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Noncurrent Count (start) | {ms['noncurrent_version_count_first']:.0f} |",
            f"| Noncurrent Count (end) | {ms['noncurrent_version_count_last']:.0f} |",
            f"| Growth Rate | {ms['noncurrent_version_count_slope']:.2f} versions/hr |",
            f"| Trend | **{ms['trend'].upper()}** |",
            f"| Evaluation Period | {ms['period_days']} days |",
            "",
            "**Recommended Lifecycle Policy**",
            "",
            "| Setting | Value |",
            "|---------|-------|",
            f"| Noncurrent version expiration | {cfg['noncurrent_days']} days |",
            f"| Newer noncurrent versions to keep | {cfg['newer_versions']} |",
            f"| Abort incomplete multipart uploads | {cfg['multipart_days']} days |",
            "",
            f"**Estimated Monthly Savings**: **${f['estimated_monthly_saving_usd']:.2f}**  ",
            f"**Estimated Annual Savings**: **${f['estimated_annual_saving_usd']:.2f}**",
            "",
        ]

    # ── Root Cause ───────────────────────────────────────────────────
    lines += ["## Root Cause Analysis", ""]
    for f in findings:
        lines += [
            f"### `{f['bucket_name']}`",
            "",
            f.get("root_cause", "No information available."),
            "",
            "**Why this goes unnoticed**: S3 storage charges appear as a single line in the "
            "AWS bill. Without separating noncurrent version storage from current storage, "
            "the cost appears as normal S3 usage growth rather than an uncontrolled accumulation.",
            "",
        ]

    # ── Remediation ──────────────────────────────────────────────────
    lines += ["## Remediation Strategy", ""]
    for f in findings:
        lines += [
            f"### `{f['bucket_name']}`",
            "",
            f.get("remediation", "No information available."),
            "",
        ]

    lines += [
        "### Preventive Actions (Apply to All Future Buckets)",
        "",
        "1. **Org-wide policy**: Use AWS Organizations SCP or a Terraform module wrapper to "
        "enforce that any `aws_s3_bucket` with versioning enabled must also have a "
        "`aws_s3_bucket_lifecycle_configuration`.",
        "2. **AWS Config rule**: Enable `S3_LIFECYCLE_POLICY_CHECK` to flag buckets "
        "without lifecycle policies.",
        "3. **Cost allocation**: Tag noncurrent storage with `StorageClass=Noncurrent` "
        "and set a budget alert.",
        "",
    ]

    # ── Savings Summary ──────────────────────────────────────────────
    lines += [
        "## Estimated Savings Summary",
        "",
        "| Bucket | Rule | Severity | Action | Monthly | Annual |",
        "|--------|------|----------|--------|---------|--------|",
    ]
    for f in findings:
        action = ACTION_LABEL.get(f["action"], f["action"])
        lines.append(
            f"| `{f['bucket_name']}` | {f['rule_id']} | {f['severity']} | {action} "
            f"| ${f['estimated_monthly_saving_usd']:.2f} | ${f['estimated_annual_saving_usd']:.2f} |"
        )
    lines += [
        f"| **TOTAL** | | | | **${total_save:.2f}** | **${annual_save:.2f}** |",
        "",
        f"> **Pricing basis**: S3 Standard ${price_per_gb}/GB-month ({region}).  ",
        f"> Savings represent noncurrent version storage cost stopped at lifecycle expiry threshold.",
        "",
    ]

    # ── Optimized Terraform ──────────────────────────────────────────
    lines += [
        "## Optimized Terraform",
        "",
        "Add the following lifecycle configuration blocks to your Terraform. "
        "Existing `aws_s3_bucket` and `aws_s3_bucket_versioning` resources are unchanged.",
        "",
        "```hcl",
    ]
    for f in findings:
        lines += [lifecycle_tf_block(f), ""]
    lines += ["```", ""]

    lines += [
        "---",
        "",
        "*Generated by: FinOps S3 Skill (finops-s3) — Claude Agent Skills*",
    ]

    return "\n".join(lines)


def render_optimized_tf(original_tf_path: str | None, findings: list[dict]) -> str:
    """
    Builds main_optimized.tf = original main.tf content + new lifecycle blocks appended.
    """
    lines = []

    if original_tf_path and Path(original_tf_path).exists():
        original = Path(original_tf_path).read_text(encoding="utf-8").rstrip()
        lines += [
            "# main_optimized.tf — generated by finops-s3 skill",
            "# Changes: aws_s3_bucket_lifecycle_configuration blocks added for each",
            "# versioning-enabled bucket that was missing a noncurrent expiry policy.",
            "# Existing resources are unchanged.",
            "",
            original,
            "",
        ]
    else:
        lines += [
            "# main_optimized.tf — generated by finops-s3 skill",
            "# (Original main.tf not provided — lifecycle blocks only)",
            "",
        ]

    lines += [
        "# ══════════════════════════════════════════════════════════",
        "# ADDED BY FINOPS-S3: Lifecycle policies to expire noncurrent versions",
        "# ══════════════════════════════════════════════════════════",
        "",
    ]
    for f in findings:
        lines += [lifecycle_tf_block(f), ""]

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="FinOps S3 Report Formatter")
    ap.add_argument("--findings",    default="findings.json")
    ap.add_argument("--out",         default="finops_report.md")
    ap.add_argument("--original-tf", default=None,
                    help="Path to original main.tf to include in main_optimized.tf")
    args = ap.parse_args()

    data   = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    report = render_report(data)

    print(report)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"\n[formatter] ✓ Report saved → {args.out}")

    # Write main_optimized.tf next to the report
    out_dir = Path(args.out).parent
    opt_tf_path = out_dir / "main_optimized.tf"
    opt_tf = render_optimized_tf(args.original_tf, data["findings"])
    opt_tf_path.write_text(opt_tf, encoding="utf-8")
    print(f"[formatter] ✓ Optimized Terraform saved → {opt_tf_path}")


if __name__ == "__main__":
    main()
