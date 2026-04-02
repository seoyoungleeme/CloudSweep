#!/usr/bin/env python3
"""
formatter.py — FinOps ELB Skill
Reads findings.json and formats it into a Markdown report saved to finops_report.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SEVERITY_ICON      = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
ACTION_LABEL       = {"DELETE": "Immediate Deletion", "MONITOR": "Keep Monitoring", "OPTIMIZE": "Requires Optimization"}
ALB_HOURS_PER_MONTH = 730


def render_report(data: dict) -> str:
    findings         = data["findings"]
    cost_summary     = data.get("cost_summary", {})
    total_save       = data["total_estimated_monthly_saving_usd"]
    annual_save      = data["total_estimated_annual_saving_usd"]
    total_potential  = data.get("total_potential_monthly_saving_usd", 0.0)
    analyzed_at      = data.get("analyzed_at", "N/A")
    region           = data.get("region", "us-east-1")
    alb_monthly_cost = data.get("alb_monthly_cost_usd", round(0.0225 * 730, 4))

    lines = []

    # ── Header ──────────────────────────────────────────────────
    lines += [
        "# FinOps ELB Analysis Report",
        "",
        f"- **Analysis Date/Time**: {analyzed_at}",
        f"- **Resources Checked**: {data['total_resources_checked']}",
        f"- **Issues Found**: {data['findings_count']}",
        "",
    ]

    # ── Executive Summary ─────────────────────────────────────
    avg_elb_monthly = cost_summary.get("avg_elb_monthly", "N/A")
    pricing_note    = cost_summary.get("pricing_note", "")
    lines += [
        "## Executive Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Region | {region} |",
        f"| Issues Found | {data['findings_count']} items |",
        f"| Confirmed Monthly Savings (DELETE) | **${total_save:.2f}** |",
        f"| Potential Monthly Savings (MONITOR) | ${total_potential:.2f} |",
        f"| Confirmed Annual Savings | **${annual_save:.2f}** |",
        f"| Average Monthly ELB Spend | ${avg_elb_monthly} |",
        f"| Average Monthly Cloud Cost | ${cost_summary.get('avg_total', 'N/A')} |",
        f"| Average Monthly Wasted Cost | ${cost_summary.get('avg_waste', 'N/A')} ({cost_summary.get('avg_waste_pct', 'N/A')}%) |",
        "",
    ]
    if pricing_note:
        lines += [f"> **Cost Evidence**: {pricing_note}", ""]

    if not findings:
        lines += ["> ✅ No FinOps cost issues were found.", ""]
        return "\n".join(lines)

    # ── Discovered Cost Issues ──────────────────────────────────────
    lines += ["## Discovered Cost Issues", ""]
    for i, f in enumerate(findings, 1):
        icon = SEVERITY_ICON.get(f["severity"], "⚪")
        action = ACTION_LABEL.get(f["action"], f["action"])
        lines += [
            f"### {i}. {icon} `{f['resource_id']}` — {f['severity']}",
            "",
            f"**Verdict**: {f['verdict']}  ",
            f"**Recommended Action**: {action}  ",
            f"**Confidence**: {f['confidence']}",
            "",
            "**Metrics Summary (30 Days)**",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
        ]
        ms           = f["metrics_summary"]
        conn_display = "N/A (data missing)" if ms.get("active_connection_data_missing") else ms["active_connection_count_avg"]
        lines += [
            f"| request_count Avg | {ms['request_count_avg']} |",
            f"| active_connection_count Avg | {conn_display} |",
            f"| Days with request_count = 0 | {ms['request_count_zero_days']} days / {ms['period_days']} days |",
            "",
        ]

    # ── Deep Root Cause Analysis ────────────────────────────────────────
    lines += ["## Deep Root Cause Analysis", ""]
    for f in findings:
        lines += [
            f"### `{f['resource_id']}`",
            "",
            f.get("root_cause", "No information available"),
            "",
        ]

    # ── Remediation Strategy ─────────────────────────────────────────────
    lines += ["## Remediation Strategy", ""]
    for f in findings:
        lines += [
            f"### `{f['resource_id']}`",
            "",
            f.get("remediation", "No information available"),
            "",
        ]

    # ── Estimated Savings ───────────────────────────────────────────
    alb_hourly = alb_monthly_cost / ALB_HOURS_PER_MONTH
    lines += [
        "## Estimated Savings",
        "",
        f"| Resource | Severity | Action | Type | Monthly | Annual |",
        f"|----------|----------|--------|------|---------|--------|",
    ]
    for f in findings:
        action     = ACTION_LABEL.get(f["action"], f["action"])
        type_label = "Confirmed" if f.get("saving_type") == "confirmed" else "Potential"
        lines.append(
            f"| `{f['resource_id']}` | {f['severity']} | {action} | {type_label} "
            f"| ${f['estimated_monthly_saving_usd']:.2f} "
            f"| ${f['estimated_annual_saving_usd']:.2f} |"
        )
    lines += [
        f"| **TOTAL (confirmed)** | | | | **${total_save:.2f}** | **${annual_save:.2f}** |",
        "",
        f"> **Cost Basis**: AWS ALB Fixed Cost ${alb_hourly:.4f}/hr × {ALB_HOURS_PER_MONTH}hr = ${alb_monthly_cost:.2f}/month ({region})",
        f"> LCU cost = $0 (no traffic on idle resources).",
        f"> MONITOR findings show potential savings — excluded from confirmed totals, pending investigation.",
        "",
    ]

    # ── Footer ──────────────────────────────────────────────────
    lines += [
        "---",
        "",
        "*Generated by: FinOps ELB Skill (finops-elb) — Claude Agent Skills*",
    ]

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="FinOps ELB Report Formatter")
    ap.add_argument("--findings", default="findings.json", help="Analyzer output file")
    ap.add_argument("--out",      default="finops_report.md", help="Markdown output file")
    args = ap.parse_args()

    data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
    report = render_report(data)

    print(report)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"\n[formatter] ✓ Report saved → {args.out}")


if __name__ == "__main__":
    main()
