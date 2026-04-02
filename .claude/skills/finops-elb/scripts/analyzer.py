#!/usr/bin/env python3
"""
analyzer.py — FinOps ELB Skill
Reads parsed_input.json and rules/unused_elb.json to generate findings.json.
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Region-aware ALB pricing table (hourly, USD) — AWS public pricing
ALB_HOURLY_PRICING = {
    "us-east-1":      0.0225,
    "us-east-2":      0.0225,
    "us-west-1":      0.0250,
    "us-west-2":      0.0225,
    "ca-central-1":   0.0225,
    "ap-northeast-1": 0.0270,
    "ap-northeast-2": 0.0252,
    "ap-southeast-1": 0.0270,
    "ap-southeast-2": 0.0270,
    "ap-south-1":     0.0225,
    "eu-west-1":      0.0270,
    "eu-west-2":      0.0261,
    "eu-central-1":   0.0270,
    "sa-east-1":      0.0405,
}
ALB_HOURS_PER_MONTH = 730   # AWS standard: 730hr average month
DEFAULT_REGION      = "us-east-1"


def get_alb_monthly_cost(region: str) -> float:
    """Returns ALB fixed monthly cost (USD) for the given region."""
    hourly = ALB_HOURLY_PRICING.get(region, ALB_HOURLY_PRICING[DEFAULT_REGION])
    return round(hourly * ALB_HOURS_PER_MONTH, 4)


def load_rules(rules_path: str) -> dict:
    return json.loads(Path(rules_path).read_text(encoding="utf-8"))


def severity_label(score: int) -> str:
    if score >= 90:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    return "LOW"


def analyze_resource(resource: dict, metrics: dict, rules: dict, alb_monthly_cost: float) -> dict | None:
    """
    Evaluates rules for a single resource and returns a finding dict.
    Returns None if the resource is healthy (no waste detected).
    """
    rid = resource["resource_id"]
    m = metrics.get(rid, {})
    period = m.get("period_days", 30)

    req_avg  = m.get("request_count_avg", None)
    conn_avg = m.get("active_connection_count_avg", None)
    req_zeros = m.get("request_count_zero_days", 0)

    thresholds     = rules.get("thresholds", {})
    req_threshold  = thresholds.get("request_count_avg_max", 0)
    conn_threshold = thresholds.get("active_connection_count_avg_max", 0)
    min_zero_days  = thresholds.get("min_zero_days", 28)

    # Skip if ALL metric data is missing — cannot make a determination
    if req_avg is None and conn_avg is None:
        return None

    # Track whether active_connection data was actually measured; missing != zero
    conn_data_missing = conn_avg is None

    req_avg  = req_avg  if req_avg  is not None else 0.0
    conn_avg = conn_avg if conn_avg is not None else 0.0

    is_req_zero        = req_avg  <= req_threshold
    is_conn_zero       = conn_avg <= conn_threshold
    is_persistent_zero = req_zeros >= min_zero_days

    # ── Rule A: both zero, persistent → DELETE ─────────────────────
    if is_req_zero and is_conn_zero and is_persistent_zero:
        severity_score = 95
        action         = "DELETE"
        saving_type    = "confirmed"
        verdict        = "Unused ALB — Immediate deletion recommended"
        # Downgrade confidence when connection data is absent (can't fully confirm)
        if conn_data_missing:
            confidence = "MEDIUM"
            verdict    = "Unused ALB — Deletion recommended (verify: active_connection data unavailable)"
        else:
            confidence = "HIGH"   # may be re-validated in main() via cost alignment
        root_cause = (
            f"30-day request_count average {req_avg:.1f}, "
            f"active_connection_count average {'N/A (data missing)' if conn_data_missing else f'{conn_avg:.1f}'}. "
            "Traffic is exactly zero, incurring only ALB fixed costs. "
            "Suspected incomplete cleanup of test/old environments or unremoved resources after service termination."
        )
        remediation = (
            "1. Check Route 53 / CNAME references before deletion\n"
            f"2. Terraform: Run `terraform destroy -target=aws_lb.{rid}`\n"
            "3. Or AWS CLI: `aws elbv2 delete-load-balancer --load-balancer-arn <ARN>`"
        )

    # ── Rule B: requests zero but connections non-zero → MONITOR ───
    elif is_req_zero and not is_conn_zero:
        severity_score = 65
        action         = "MONITOR"
        saving_type    = "potential"   # not confirmed — requires investigation first
        confidence     = "MEDIUM"
        verdict        = "No Requests — Intermittent connections detected, 14-day monitoring required"
        root_cause     = (
            f"request_count average is {req_avg:.1f} (effectively 0) but "
            f"active_connection_count average is {conn_avg:.1f}, indicating intermittent connections. "
            "Possibility of health checks or internal service connections."
        )
        remediation = (
            "1. Identify actual connection source (IP) in CloudWatch Logs\n"
            "2. Re-evaluate after 14 days of additional monitoring\n"
            "3. Proceed with deletion if connections are exclusively health checks"
        )

    else:
        # Rule C: normal usage — no finding
        return None

    monthly_saving = round(alb_monthly_cost, 2)
    annual_saving  = round(monthly_saving * 12, 2)

    return {
        "resource_id":   rid,
        "resource_type": "aws_lb",
        "lb_type":       resource.get("lb_type", "application"),
        "verdict":       verdict,
        "severity":      severity_label(severity_score),
        "action":        action,
        "saving_type":   saving_type,
        "confidence":    confidence,
        "metrics_summary": {
            "request_count_avg":              round(req_avg, 2),
            "active_connection_count_avg":    None if conn_data_missing else round(conn_avg, 2),
            "active_connection_data_missing": conn_data_missing,
            "request_count_zero_days":        req_zeros,
            "period_days":                    period,
        },
        "root_cause":  root_cause,
        "remediation": remediation,
        "estimated_monthly_saving_usd": monthly_saving,
        "estimated_annual_saving_usd":  annual_saving,
    }


def main():
    ap = argparse.ArgumentParser(description="FinOps ELB Analyzer")
    ap.add_argument("--input",  default="parsed_input.json", help="Parser output file")
    ap.add_argument("--rules",  default="rules/unused_elb.json", help="Rules configuration file")
    ap.add_argument("--out",    default="findings.json", help="Findings output file")
    ap.add_argument("--region", default=None,
                    help="Override AWS region for pricing (e.g. ap-northeast-2). "
                         "Defaults to region in parsed_input.json, then us-east-1.")
    args = ap.parse_args()

    data         = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rules        = load_rules(args.rules)
    tf_resources = data["tf_resources"]
    metrics      = data["metrics"]
    cost_summary = data["cost_summary"]

    # Region priority: CLI flag > parsed_input.json > DEFAULT_REGION
    region           = args.region or data.get("region", DEFAULT_REGION)
    alb_monthly_cost = get_alb_monthly_cost(region)

    print(f"[analyzer] Region: {region} / ALB monthly cost: ${alb_monthly_cost:.4f}")
    print(f"[analyzer] Resources to analyze: {len(tf_resources)}")

    findings = []
    for resource in tf_resources:
        result = analyze_resource(resource, metrics, rules, alb_monthly_cost)
        if result:
            findings.append(result)
            print(f"[analyzer]   [{result['severity']}] {result['resource_id']} - {result['verdict'][:60]}")
        else:
            print(f"[analyzer]   [OK]  {resource['resource_id']} - Normal")

    # ── Post-process: re-validate confidence using actual HIGH DELETE count ─
    # Compares reported avg waste to expected cost of all HIGH DELETE findings.
    # Only upgrades findings where active_connection data was actually measured.
    high_delete_count = sum(
        1 for f in findings
        if f["severity"] == "HIGH" and f["action"] == "DELETE"
    )
    avg_waste = cost_summary.get("avg_waste", 0)
    if high_delete_count > 0 and abs(avg_waste - alb_monthly_cost * high_delete_count) < 5.0:
        for f in findings:
            if (f["severity"] == "HIGH"
                    and f["action"] == "DELETE"
                    and not f["metrics_summary"].get("active_connection_data_missing")):
                f["confidence"] = "HIGH"

    # ── Totals: confirmed (DELETE) vs potential (MONITOR) ───────────
    confirmed = [f for f in findings if f["saving_type"] == "confirmed"]
    potential = [f for f in findings if f["saving_type"] == "potential"]

    total_confirmed_monthly = round(sum(f["estimated_monthly_saving_usd"] for f in confirmed), 2)
    total_potential_monthly = round(sum(f["estimated_monthly_saving_usd"] for f in potential), 2)
    total_confirmed_annual  = round(total_confirmed_monthly * 12, 2)

    # ── Cap savings at actual ELB service spend from cost report ────
    # Cannot save more than what is actually billed for ELB.
    savings_capped = False
    avg_elb_monthly = cost_summary.get("avg_elb_monthly", 0)
    if avg_elb_monthly > 0 and total_confirmed_monthly > avg_elb_monthly:
        cap_ratio = avg_elb_monthly / total_confirmed_monthly
        for f in confirmed:
            f["estimated_monthly_saving_usd"] = round(f["estimated_monthly_saving_usd"] * cap_ratio, 2)
            f["estimated_annual_saving_usd"]  = round(f["estimated_monthly_saving_usd"] * 12, 2)
        total_confirmed_monthly = round(avg_elb_monthly, 2)
        total_confirmed_annual  = round(total_confirmed_monthly * 12, 2)
        savings_capped = True
        print(f"[analyzer]   Savings capped at avg_elb_monthly: ${avg_elb_monthly}")

    output = {
        "analyzed_at":                         datetime.utcnow().isoformat() + "Z",
        "region":                              region,
        "alb_monthly_cost_usd":               alb_monthly_cost,
        "total_resources_checked":            len(tf_resources),
        "findings_count":                     len(findings),
        "total_estimated_monthly_saving_usd": total_confirmed_monthly,
        "total_potential_monthly_saving_usd": total_potential_monthly,
        "total_estimated_annual_saving_usd":  total_confirmed_annual,
        "savings_capped_at_elb_spend":        savings_capped,
        "cost_summary":                        cost_summary,
        "findings":                            findings,
    }

    Path(args.out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyzer] Done - {args.out}")
    print(f"[analyzer]   Confirmed monthly savings: ${total_confirmed_monthly} | Potential: ${total_potential_monthly}")


if __name__ == "__main__":
    main()
