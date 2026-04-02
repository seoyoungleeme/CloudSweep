#!/usr/bin/env python3
"""
formatter.py — FinOps RDS Skill
Reads findings.json and formats it into a Markdown report.
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEVERITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
ACTION_LABEL  = {
    "DISABLE_MULTI_AZ": "Disable Multi-AZ",
    "DOWNSIZE":         "Downsize Instance Class",
    "MONITOR":          "Monitor",
}
RULE_NAMES = {
    "R1": "Multi-AZ on Non-Production",
    "R2": "CPU Underutilization (Overprovisioned)",
}


def render_report(data: dict) -> str:
    findings      = data["findings"]
    cost_summary  = data.get("cost_summary", {})
    total_save    = data["total_estimated_monthly_saving_usd"]
    annual_save   = data["total_estimated_annual_saving_usd"]
    analyzed_at   = data.get("analyzed_at", "N/A")
    region        = data.get("region", "us-east-1")

    lines = []

    # ── Header ──────────────────────────────────────────────────────
    lines += [
        "# FinOps RDS Analysis Report",
        "",
        f"- **Analysis Date/Time**: {analyzed_at}",
        f"- **Region**: {region}",
        f"- **Resources Checked**: {data['total_resources_checked']}",
        f"- **Issues Found**: {data['findings_count']}",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────
    avg_rds_monthly = cost_summary.get("avg_rds_monthly", "N/A")
    pricing_note    = cost_summary.get("pricing_note", "")
    lines += [
        "## Executive Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Region | {region} |",
        f"| Issues Found | {data['findings_count']} items |",
        f"| Confirmed Monthly Savings | **${total_save:.2f}** |",
        f"| Confirmed Annual Savings | **${annual_save:.2f}** |",
        f"| Avg Monthly RDS Spend | ${avg_rds_monthly} |",
        "",
    ]
    if pricing_note:
        lines += [f"> **Note**: {pricing_note}", ""]

    if not findings:
        lines += ["> ✅ No FinOps cost issues were found.", ""]
        return "\n".join(lines)

    # ── Discovered Cost Issues ───────────────────────────────────────
    lines += ["## Discovered Cost Issues", ""]
    for i, f in enumerate(findings, 1):
        icon        = SEVERITY_ICON.get(f["severity"], "⚪")
        action_lbl  = ACTION_LABEL.get(f["action"], f["action"])
        rule_name   = RULE_NAMES.get(f["rule_id"], f["rule_id"])
        lines += [
            f"### {i}. {icon} `{f['resource_id']}` — {f['severity']} [{rule_name}]",
            "",
            f"**Verdict**: {f['verdict']}  ",
            f"**Recommended Action**: {action_lbl}  ",
            f"**Confidence**: {f['confidence']}  ",
            f"**Environment**: `{f.get('environment', 'unknown')}`  ",
            f"**Instance Class**: `{f.get('instance_class', 'unknown')}`",
            "",
            "**Metrics Summary (30 Days)**",
            "",
            "| Metric | Value |",
            "|--------|-------|",
        ]
        ms = f["metrics_summary"]
        cpu_disp  = f"{ms['cpu_utilization_avg']:.1f}%" if ms.get("cpu_utilization_avg") is not None else "N/A"
        conn_disp = f"{ms['database_connections_avg']:.1f}" if ms.get("database_connections_avg") is not None else "N/A"
        lines += [
            f"| CPU Utilization Avg | {cpu_disp} |",
            f"| Database Connections Avg | {conn_disp} |",
            f"| Evaluation Period | {ms['period_days']} days |",
            "",
        ]

        if f["rule_id"] == "R1":
            lines += [
                "**Cost Impact (Multi-AZ vs Single-AZ)**",
                "",
                "| | Cost/Month |",
                "|-|-----------|",
                f"| Current (Multi-AZ) | ${f['current_monthly_cost_usd']:.2f} |",
                f"| After fix (Single-AZ) | ${f['optimized_monthly_cost_usd']:.2f} |",
                f"| **Savings** | **${f['estimated_monthly_saving_usd']:.2f}** |",
                "",
            ]
        elif f["rule_id"] == "R2":
            lines += [
                "**Cost Impact (Instance Downsize)**",
                "",
                "| | Instance | Cost/Month |",
                "|-|----------|-----------|",
                f"| Current | `{f['current_instance_class']}` | ${f['current_monthly_cost_usd']:.2f} |",
                f"| Recommended | `{f['recommended_instance_class']}` | ${f['optimized_monthly_cost_usd']:.2f} |",
                f"| **Savings** | | **${f['estimated_monthly_saving_usd']:.2f}** |",
                "",
            ]

    # ── Deep Root Cause Analysis ─────────────────────────────────────
    lines += ["## Deep Root Cause Analysis", ""]
    for f in findings:
        rule_name = RULE_NAMES.get(f["rule_id"], f["rule_id"])
        lines += [
            f"### `{f['resource_id']}` — {rule_name}",
            "",
            f.get("root_cause", "No information available."),
            "",
        ]

    # ── Remediation Strategy ─────────────────────────────────────────
    lines += ["## Remediation Strategy", ""]
    for f in findings:
        rule_name = RULE_NAMES.get(f["rule_id"], f["rule_id"])
        lines += [
            f"### `{f['resource_id']}` — {rule_name}",
            "",
            f.get("remediation", "No information available."),
            "",
        ]

    # ── Estimated Savings Summary ────────────────────────────────────
    lines += [
        "## Estimated Savings Summary",
        "",
        "| Resource | Rule | Severity | Action | Monthly | Annual |",
        "|----------|------|----------|--------|---------|--------|",
    ]
    for f in findings:
        action_lbl = ACTION_LABEL.get(f["action"], f["action"])
        rule_name  = RULE_NAMES.get(f["rule_id"], f["rule_id"])
        lines.append(
            f"| `{f['resource_id']}` | {rule_name} | {f['severity']} | {action_lbl} "
            f"| ${f['estimated_monthly_saving_usd']:.2f} | ${f['estimated_annual_saving_usd']:.2f} |"
        )
    lines += [
        f"| **TOTAL** | | | | **${total_save:.2f}** | **${annual_save:.2f}** |",
        "",
    ]

    # ── Optimized Terraform ──────────────────────────────────────────
    lines += [
        "## Optimized Terraform",
        "",
        "Apply the changes below. Always run `terraform plan` first and snapshot your DB before resizing.",
        "",
        "```hcl",
    ]

    # Group findings by resource_id to produce one block per resource
    by_resource: dict[str, list[dict]] = {}
    for f in findings:
        by_resource.setdefault(f["resource_id"], []).append(f)

    for rid, rfindings in by_resource.items():
        r1 = next((f for f in rfindings if f["rule_id"] == "R1"), None)
        r2 = next((f for f in rfindings if f["rule_id"] == "R2"), None)

        new_multi_az  = "false" if r1 else ("true" if rfindings[0].get("environment", "prod") == "prod" else "false")
        new_cls       = r2["recommended_instance_class"] if r2 else rfindings[0].get("instance_class", "")

        changes = []
        if r1:
            changes.append(f"multi_az = false  # was true — dev env needs no cross-AZ failover; saves ${r1['estimated_monthly_saving_usd']:.2f}/mo")
        if r2:
            changes.append(f"instance_class = \"{new_cls}\"  # was {r2['current_instance_class']}; CPU avg {r2['metrics_summary']['cpu_utilization_avg']:.1f}% → saves ${r2['estimated_monthly_saving_usd']:.2f}/mo")

        lines += [
            f"# ── {rid} ──────────────────────────────────────────────",
        ]
        for c in changes:
            lines.append(f"# CHANGE: {c}")
        lines += [""]

    lines.append("```")
    lines += [""]

    # ── Governance Recommendations ───────────────────────────────────
    lines += [
        "## Governance Recommendations",
        "",
        "### Prevent Recurrence",
        "",
        "1. **Tagging policy**: Enforce `Environment` tag on all `aws_db_instance` resources via AWS Config.",
        "2. **Multi-AZ guard**: Add a CI/CD check that fails if `multi_az = true` and `Environment` tag is `dev`/`test`/`staging`.",
        "3. **Cost Anomaly Detection**: Enable AWS Cost Anomaly Detection on the RDS service to alert on unexpected spend increases.",
        "",
        "```hcl",
        "# Optional: AWS Config rule to detect Multi-AZ on non-prod RDS",
        "resource \"aws_config_config_rule\" \"rds_non_prod_single_az\" {",
        "  name = \"rds-non-prod-no-multi-az\"",
        "  source {",
        "    owner             = \"CUSTOM_LAMBDA\"",
        "    source_identifier = aws_lambda_function.rds_multi_az_check.arn",
        "  }",
        "}",
        "```",
        "",
        "---",
        "",
        "*Generated by: FinOps RDS Skill (finops-rds) — Claude Agent Skills*",
    ]

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="FinOps RDS Report Formatter")
    ap.add_argument("--findings", default="findings.json", help="Analyzer output file")
    ap.add_argument("--out",      default="finops_report.md", help="Markdown output file")
    args = ap.parse_args()

    data   = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    report = render_report(data)

    print(report)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"\n[formatter] ✓ Report saved → {args.out}")


if __name__ == "__main__":
    main()
