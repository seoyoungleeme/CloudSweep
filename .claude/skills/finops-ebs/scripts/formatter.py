#!/usr/bin/env python3
"""
formatter.py — FinOps EBS Skill
Reads findings.json → finops_report.md.

When all (or most) resources are flagged for deletion, produces a compact report
with a bulk CLI deletion script instead of listing every resource individually.
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# When findings exceed this count, switch to compact review-candidate mode.
BULK_THRESHOLD = 10


def render_report(data: dict) -> str:
    findings      = data["findings"]
    cost_summary  = data.get("cost_summary", {})
    total_save    = data["total_estimated_monthly_saving_usd"]
    annual_save   = data["total_estimated_annual_saving_usd"]
    analyzed_at   = data.get("analyzed_at", "N/A")
    region        = data.get("region", "us-east-1")
    total_checked = data["total_resources_checked"]
    total_storage = data.get("total_orphaned_storage_gb", 0)
    price_per_gb  = data.get("snapshot_price_per_gb_usd", 0.05)

    is_bulk = len(findings) >= BULK_THRESHOLD

    lines = []

    # ── Header ──────────────────────────────────────────────────────
    lines += [
        "# FinOps EBS Snapshot Analysis Report",
        "",
        f"- **Analysis Date/Time**: {analyzed_at}",
        f"- **Region**: {region}",
        f"- **Snapshots Checked**: {total_checked}",
        f"- **Orphaned Snapshots Found**: {data['findings_count']}",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────
    avg_ebs_monthly = cost_summary.get("avg_ebs_monthly", "N/A")
    pricing_note    = cost_summary.get("pricing_note", "")
    lines += [
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Region | {region} |",
        f"| Total Snapshots | {total_checked} |",
        f"| Cleanup Candidates | **{data['findings_count']}** |",
        f"| Total Orphaned Storage | {total_storage:.1f} GB |",
        f"| Potential Monthly Savings | **${total_save:.2f}** |",
        f"| Potential Annual Savings | **${annual_save:.2f}** |",
        f"| Avg Monthly EBS Spend | ${avg_ebs_monthly} |",
        f"| Snapshot Price | ${price_per_gb}/GB-month ({region}) |",
        "",
    ]
    if pricing_note:
        lines += [f"> **Note**: {pricing_note}", ""]

    if not findings:
        lines += ["> ✅ No orphaned EBS snapshots found.", ""]
        return "\n".join(lines)

    # ── Problem Identification ───────────────────────────────────────
    lines += [
        "## Problem Identification",
        "",
        "| Category | Details |",
        "|----------|---------|",
        f"| Waste Type | Potential orphaned EBS snapshots (source volume deleted) |",
        f"| Affected Resources | {data['findings_count']} of {total_checked} `aws_ebs_snapshot` |",
        f"| Detection Signal | `SourceVolumeStatus = \"deleted\"` tag |",
        f"| Monthly Waste | **${total_save:.2f} potential** |",
        f"| Annual Waste | **${annual_save:.2f} potential** |",
        f"| Confidence | MEDIUM until dependency and retention checks pass |",
        "",
    ]

    # ── Snapshot List ────────────────────────────────────────────────
    if is_bulk:
        # Compact mode: summary table + first 5 examples
        lines += [
            "## Orphaned Snapshot List",
            "",
            f"> **{data['findings_count']} snapshots** are cleanup candidates. "
            f"Showing first 5 as examples — see `findings.json` for the full list.",
            "",
            "| # | Snapshot ID | Storage (GB) |",
            "|---|-------------|--------------|",
        ]
        for i, f in enumerate(findings[:5], 1):
            gb = f["metrics_summary"]["storage_gb"]
            lines.append(f"| {i} | `{f['resource_id']}` | {gb:.1f} |")
        lines += [
            f"| ... | *({data['findings_count'] - 5} more)* | ... |",
            f"| **TOTAL** | | **{total_storage:.1f} GB** |",
            "",
        ]
    else:
        lines += [
            "## Orphaned Snapshot List",
            "",
            "| # | Snapshot ID | Storage (GB) |",
            "|---|-------------|--------------|",
        ]
        for i, f in enumerate(findings, 1):
            gb = f["metrics_summary"]["storage_gb"]
            lines.append(f"| {i} | `{f['resource_id']}` | {gb:.1f} |")
        lines += [
            f"| **TOTAL** | | **{total_storage:.1f} GB** |",
            "",
        ]

    # ── Root Cause ───────────────────────────────────────────────────
    lines += [
        "## Root Cause",
        "",
        "### Evidence from Infrastructure (Terraform)",
        "",
        f"All {data['findings_count']} `aws_ebs_snapshot` resources carry the tag "
        "`SourceVolumeStatus = \"deleted\"`, confirming their source EBS volumes have been "
        "terminated. This is a strong cleanup signal, but deleting an EC2 instance or EBS "
        "volume does **not** prove the snapshot has no remaining AMI, launch template, "
        "AWS Backup, DLM, legal hold, compliance, or DR dependency.",
        "",
        "### Root Cause",
        "",
        "Snapshot lifecycle governance is incomplete. Source volumes were deleted, but the "
        "provided evidence does not fully prove whether each snapshot is still required for "
        "images, backup retention, DR, or compliance. Over time, unreviewed snapshots can "
        "become a significant hidden cost.",
        "",
    ]

    # ── Remediation ──────────────────────────────────────────────────
    snapshot_ids = " ".join(f["resource_id"] for f in findings)
    lines += [
        "## Remediation Strategy",
        "",
        "### Immediate Actions (Week 1) — Verify, Then Delete or Retain",
        "",
        "**Step 1**: Verify no AMI depends on each snapshot:",
        "```bash",
        "# Run for each snapshot before deleting",
        "aws ec2 describe-images \\",
        "  --filters Name=block-device-mapping.snapshot-id,Values=<snapshot-id> \\",
        "  --query 'Images[*].{ID:ImageId,Name:Name}'",
        "```",
        "",
        "**Step 2**: Verify launch templates, AWS Backup/DLM ownership, legal hold, compliance tags, and owner approval.",
        "",
        "**Step 3**: Delete only snapshots that pass all dependency checks:",
        "```bash",
        "# Review candidates first; delete only approved snapshot IDs",
        "aws ec2 describe-snapshots --owner-ids self \\",
        "  --filters Name=tag:SourceVolumeStatus,Values=deleted \\",
        "  --query 'Snapshots[*].SnapshotId' --output text",
        "# aws ec2 delete-snapshot --snapshot-id <approved-snapshot-id>",
        "```",
        "",
        "**Step 4**: Remove Terraform-managed deleted snapshots from state only after deletion:",
        "```bash",
        "# Remove all orphaned snapshots from Terraform state in bulk",
        "terraform state list | grep aws_ebs_snapshot | \\",
        "  xargs -I{} terraform state rm {}",
        "```",
        "",
        "### Preventive Actions (Week 2-4)",
        "",
        "1. **AWS Data Lifecycle Manager**: Create a DLM policy to automatically expire snapshots "
        "after a retention period (e.g. 30 days for dev, 90 days for prod).",
        "2. **Lambda cleanup review**: Schedule a Lambda function to scan for snapshots with deleted "
        "source volumes and open review tickets before deletion.",
        "3. **Tagging policy**: Enforce `SourceVolumeStatus` tag updates via EventBridge rule "
        "on `DeleteVolume` API call.",
        "",
        "```hcl",
        "# Optional: AWS DLM lifecycle policy to auto-expire snapshots",
        'resource "aws_dlm_lifecycle_policy" "ebs_cleanup" {',
        '  description        = "Auto-delete EBS snapshots after retention period"',
        '  execution_role_arn = aws_iam_role.dlm_lifecycle_role.arn',
        '  state              = "ENABLED"',
        "",
        "  policy_details {",
        '    resource_types = ["VOLUME"]',
        "",
        "    schedule {",
        '      name = "Daily snapshots — 30 day retention"',
        "",
        "      create_rule {",
        "        interval      = 24",
        '        interval_unit = "HOURS"',
        '        times         = ["23:45"]',
        "      }",
        "",
        "      retain_rule {",
        "        count = 30",
        "      }",
        "",
        "      copy_tags = true",
        "    }",
        "",
        "    target_tags = {",
        '      ManagedBy = "dlm"',
        "    }",
        "  }",
        "}",
        "```",
        "",
    ]

    # ── Estimated Savings ────────────────────────────────────────────
    lines += [
        "## Estimated Savings",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Cleanup Candidate Snapshots | {data['findings_count']} |",
        f"| Potential Storage to Reclaim | {total_storage:.1f} GB |",
        f"| Price per GB | ${price_per_gb}/GB-month |",
        f"| **Potential Monthly Savings** | **${total_save:.2f}** |",
        f"| **Potential Annual Savings** | **${annual_save:.2f}** |",
        "",
    ]

    # ── Footer ──────────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "*Generated by: FinOps EBS Skill (finops-ebs) — Claude Agent Skills*",
    ]

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="FinOps EBS Report Formatter")
    ap.add_argument("--findings", default="findings.json")
    ap.add_argument("--out",      default="finops_report.md")
    args = ap.parse_args()

    data   = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    report = render_report(data)

    print(report)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"\n[formatter] ✓ Report saved → {args.out}")


if __name__ == "__main__":
    main()
