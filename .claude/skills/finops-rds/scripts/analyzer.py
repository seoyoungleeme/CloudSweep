#!/usr/bin/env python3
"""
analyzer.py — FinOps RDS Skill
Reads parsed_input.json + rules/overprovisioned_rds.json and generates findings.json.

Detects two categories of waste:
  R1 — Multi-AZ enabled on non-production environment (HIGH)
  R2 — CPU chronically under-utilized relative to instance class (MEDIUM)
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HOURS_PER_MONTH = 730   # AWS standard average month

# Region-aware RDS pricing: db.r5.large single-AZ hourly (USD)
RDS_PRICING: dict[str, dict[str, float]] = {
    "us-east-1": {
        "db.t3.micro":   0.017,  "db.t3.small":  0.034,  "db.t3.medium": 0.068,
        "db.t3.large":   0.136,  "db.t4g.micro": 0.016,  "db.t4g.small": 0.032,
        "db.t4g.medium": 0.065,  "db.m5.large":  0.171,  "db.m5.xlarge": 0.342,
        "db.m6g.large":  0.153,  "db.r5.large":  0.240,  "db.r5.xlarge": 0.480,
        "db.r6g.large":  0.192,
    },
    "ap-northeast-2": {
        "db.t3.micro":   0.020,  "db.t3.small":  0.040,  "db.t3.medium": 0.080,
        "db.t3.large":   0.160,  "db.m5.large":  0.200,  "db.r5.large":  0.280,
    },
}
DEFAULT_REGION = "us-east-1"

DOWNSIZE_MAP: dict[str, str] = {
    "db.r5.large":  "db.t3.large",
    "db.r5.xlarge": "db.r5.large",
    "db.m5.large":  "db.t3.large",
    "db.m5.xlarge": "db.m5.large",
    "db.r6g.large": "db.t4g.large",
    "db.m6g.large": "db.t4g.large",
}


def get_hourly(region: str, instance_class: str) -> float:
    region_prices = RDS_PRICING.get(region, RDS_PRICING[DEFAULT_REGION])
    return region_prices.get(instance_class, 0.0)


def load_rules(rules_path: str) -> dict:
    return json.loads(Path(rules_path).read_text(encoding="utf-8"))


def analyze_resource(resource: dict, metrics: dict, rules: dict, region: str) -> list[dict]:
    """Returns zero, one, or two findings for a single RDS instance."""
    findings = []
    rid          = resource["resource_id"]
    instance_cls = resource.get("instance_class", "")
    multi_az     = resource.get("multi_az", False)
    environment  = resource.get("environment", "").lower()

    m            = metrics.get(rid, {})
    cpu_avg      = m.get("cpu_utilization_avg", None)
    conn_avg     = m.get("database_connections_avg", None)
    period_days  = m.get("period_days", 30)

    thresholds     = rules.get("thresholds", {})
    non_prod_envs  = [e.lower() for e in thresholds.get("non_prod_env_tags", ["dev", "test", "staging"])]
    cpu_threshold  = thresholds.get("cpu_utilization_avg_max_pct", 20.0)
    conn_min       = thresholds.get("database_connections_avg_min", 1.0)

    hourly_single  = get_hourly(region, instance_cls)
    monthly_single = round(hourly_single * HOURS_PER_MONTH, 2)
    monthly_multi  = round(monthly_single * 2, 2)

    # ── Rule R1: Multi-AZ on non-production ───────────────────────────
    if multi_az and environment in non_prod_envs:
        saving_monthly = monthly_single   # disabling Multi-AZ saves exactly one AZ's worth
        saving_annual  = round(saving_monthly * 12, 2)
        findings.append({
            "rule_id":       "R1",
            "resource_id":   rid,
            "resource_type": "aws_db_instance",
            "instance_class": instance_cls,
            "environment":   environment,
            "verdict":       f"Multi-AZ enabled on '{environment}' environment — redundancy unnecessary outside production",
            "severity":      "HIGH",
            "action":        "DISABLE_MULTI_AZ",
            "saving_type":   "confirmed",
            "confidence":    "HIGH",
            "metrics_summary": {
                "cpu_utilization_avg":       round(cpu_avg, 2) if cpu_avg is not None else None,
                "database_connections_avg":  round(conn_avg, 2) if conn_avg is not None else None,
                "period_days":               period_days,
            },
            "root_cause": (
                f"`{rid}` is tagged Environment='{environment}' but has `multi_az = true`. "
                f"Multi-AZ doubles the instance cost (${monthly_single:.2f}/mo single-AZ → ${monthly_multi:.2f}/mo multi-AZ). "
                "Development and test environments do not require cross-AZ failover; "
                "enabling it here is a configuration oversight that silently doubles RDS spend."
            ),
            "remediation": (
                f"1. Set `multi_az = false` in Terraform for `aws_db_instance.{rid}`\n"
                f"2. Apply during a maintenance window: `terraform apply -target=aws_db_instance.{rid}`\n"
                "3. AWS performs a brief failover (< 60s) when switching from Multi-AZ to Single-AZ.\n"
                "4. Add a governance check (e.g. AWS Config rule) to block multi_az=true on non-prod instances."
            ),
            "current_monthly_cost_usd":    monthly_multi,
            "optimized_monthly_cost_usd":  monthly_single,
            "estimated_monthly_saving_usd": saving_monthly,
            "estimated_annual_saving_usd":  saving_annual,
        })

    # ── Rule R2: CPU underutilization ─────────────────────────────────
    # Check if R1 was already emitted for this instance (Multi-AZ will be disabled).
    r1_emitted = any(f["rule_id"] == "R1" and f["resource_id"] == rid for f in findings)

    if cpu_avg is not None and cpu_avg < cpu_threshold:
        # Only flag if the DB is actually in use (has some connections)
        db_in_use = conn_avg is None or conn_avg >= conn_min
        if db_in_use:
            recommended_cls = DOWNSIZE_MAP.get(instance_cls)
            if recommended_cls:
                hourly_recommended  = get_hourly(region, recommended_cls)
                monthly_recommended = round(hourly_recommended * HOURS_PER_MONTH, 2)
                # If R1 disables Multi-AZ, R2 savings should assume single-AZ
                # to avoid double-counting the AZ cost already saved by R1.
                az_mult = 1 if r1_emitted else (2 if multi_az else 1)
                saving_monthly = round((monthly_single - monthly_recommended) * az_mult, 2)
                saving_annual  = round(saving_monthly * 12, 2)

                if saving_monthly > 0:
                    findings.append({
                        "rule_id":       "R2",
                        "resource_id":   rid,
                        "resource_type": "aws_db_instance",
                        "instance_class": instance_cls,
                        "environment":   environment,
                        "verdict": (
                            f"CPU avg {cpu_avg:.1f}% over {period_days}d — "
                            f"'{instance_cls}' is overprovisioned; downsize to '{recommended_cls}'"
                        ),
                        "severity":    "MEDIUM",
                        "action":      "DOWNSIZE",
                        "saving_type": "confirmed",
                        "confidence":  "MEDIUM",
                        "metrics_summary": {
                            "cpu_utilization_avg":      round(cpu_avg, 2),
                            "database_connections_avg": round(conn_avg, 2) if conn_avg is not None else None,
                            "period_days":              period_days,
                        },
                        "root_cause": (
                            f"`{rid}` uses `{instance_cls}` (memory-optimized, ${monthly_single:.2f}/mo) "
                            f"but 30-day average CPU is only {cpu_avg:.1f}%. "
                            "Memory-optimized R-family instances are intended for workloads requiring >60% memory pressure; "
                            "at these utilization levels a general-purpose T or M class instance is sufficient. "
                            f"Recommended replacement: `{recommended_cls}` (${monthly_recommended:.2f}/mo)."
                        ),
                        "remediation": (
                            f"1. Create a snapshot before resizing: `aws rds create-db-snapshot`\n"
                            f"2. Modify instance class in Terraform: `instance_class = \"{recommended_cls}\"`\n"
                            f"3. Apply during maintenance window: `terraform apply -target=aws_db_instance.{rid}`\n"
                            "4. Monitor CPU and connection metrics for 7 days after resize to confirm headroom."
                        ),
                        "current_instance_class":      instance_cls,
                        "recommended_instance_class":  recommended_cls,
                        "r2_assumes_single_az":        r1_emitted,
                        "current_monthly_cost_usd":    round(monthly_single * az_mult, 2),
                        "optimized_monthly_cost_usd":  round(monthly_recommended * az_mult, 2),
                        "estimated_monthly_saving_usd": saving_monthly,
                        "estimated_annual_saving_usd":  saving_annual,
                    })

    return findings


def main():
    ap = argparse.ArgumentParser(description="FinOps RDS Analyzer")
    ap.add_argument("--input",  default="parsed_input.json", help="Parser output file")
    ap.add_argument("--rules",  default="rules/overprovisioned_rds.json", help="Rules config")
    ap.add_argument("--out",    default="findings.json", help="Findings output file")
    ap.add_argument("--region", default=None, help="Override AWS region for pricing")
    args = ap.parse_args()

    data         = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rules        = load_rules(args.rules)
    tf_resources = data["tf_resources"]
    metrics      = data["metrics"]
    cost_summary = data["cost_summary"]

    region = args.region or data.get("region", DEFAULT_REGION)
    print(f"[analyzer] Region: {region}")
    print(f"[analyzer] Resources to analyze: {len(tf_resources)}")

    all_findings: list[dict] = []
    for resource in tf_resources:
        results = analyze_resource(resource, metrics, rules, region)
        if results:
            for r in results:
                all_findings.append(r)
                print(f"[analyzer]   [{r['severity']}][{r['rule_id']}] {r['resource_id']} — {r['verdict'][:70]}")
        else:
            print(f"[analyzer]   [OK]  {resource['resource_id']} — No issues found")

    confirmed = [f for f in all_findings if f["saving_type"] == "confirmed"]
    total_monthly = round(sum(f["estimated_monthly_saving_usd"] for f in confirmed), 2)
    total_annual  = round(total_monthly * 12, 2)

    output = {
        "analyzed_at":                        datetime.utcnow().isoformat() + "Z",
        "region":                             region,
        "total_resources_checked":            len(tf_resources),
        "findings_count":                     len(all_findings),
        "total_estimated_monthly_saving_usd": total_monthly,
        "total_estimated_annual_saving_usd":  total_annual,
        "cost_summary":                       cost_summary,
        "findings":                           all_findings,
    }

    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyzer] Done — {args.out}")
    print(f"[analyzer]   Total confirmed monthly savings: ${total_monthly}")


if __name__ == "__main__":
    main()
