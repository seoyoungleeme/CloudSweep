"""Cross-domain review facts and notes for CloudSweep reports."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .domain_detection import _domain_from_service, _resource_blocks
from .rule_engine import stable_id


def _series(values: Any) -> list[float]:
    if isinstance(values, dict):
        values = values.get("datapoints", [])
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for item in values:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _as_percent(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 1:
        return number * 100
    return number


def _resource_name(address: str) -> str:
    """Extract the name component from a 'type.name' Terraform address."""
    parts = address.split(".")
    return parts[-1] if len(parts) > 1 else address


def _index_findings_by_resource(
    findings: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    idx: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        resource = str(finding.get("resource", ""))
        if resource:
            idx.setdefault(resource, []).append(finding)
    return idx


def _index_metric_facts(
    dependency_facts: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    metric_kinds = {"request_invocation_ratio", "retry_amplification_ratio", "cache_hit_rate_pct"}
    idx: dict[str, dict[str, float]] = {}
    for fact in dependency_facts:
        if fact.get("kind") in metric_kinds:
            resource = str(fact.get("resource", ""))
            if resource:
                idx.setdefault(resource, {})[str(fact["kind"])] = float(fact["value"])
    return idx


def _record_config(record: dict[str, Any]) -> dict[str, Any]:
    configuration = record.get("configuration", {})
    return configuration if isinstance(configuration, dict) else {}


def _record_resource_type(record: dict[str, Any]) -> str:
    return str(record.get("resource_type") or record.get("type") or "")


def _record_log_group_name(record: dict[str, Any]) -> str | None:
    configuration = _record_config(record)
    for value in (
        configuration.get("name"),
        record.get("log_group_name"),
        record.get("name"),
        record.get("resource_id"),
    ):
        if isinstance(value, str) and value.startswith("/"):
            return value
    return None


def _append_cross_domain_ref(finding: dict[str, Any], ref: dict[str, Any]) -> None:
    refs = finding.setdefault("cross_domain_refs", [])
    if ref not in refs:
        refs.append(ref)


def _cross_domain_analysis(
    domains: set[str],
    findings: list[dict[str, Any]],
    anomaly: dict[str, Any],
    dependency_facts: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate cross-domain notes and annotate findings with cross-domain refs.

    Returns (notes, annotated_findings). Findings are shallow-copied and
    mutated in place; the originals are not modified.
    """
    notes: list[str] = []
    annotated = [dict(f) for f in findings]
    hypotheses: list[dict[str, Any]] = []
    by_resource = _index_findings_by_resource(annotated)
    metric_facts = _index_metric_facts(dependency_facts)

    def lookup(address: str) -> list[dict[str, Any]]:
        # Try full address first, then name-only fallback.
        return by_resource.get(address) or by_resource.get(_resource_name(address), [])

    # 1. Terraform reference edges where both endpoints have findings.
    #    Annotate the source finding with the upstream dependency and emit
    #    a remediation-ordering note.
    seen_pairs: set[tuple[str, str]] = set()
    for fact in dependency_facts:
        if fact.get("kind") != "terraform_reference":
            continue
        source_addr = str(fact.get("source", ""))
        target_addr = str(fact.get("target", ""))
        pair = (source_addr, target_addr)
        if pair in seen_pairs:
            continue
        source_findings = lookup(source_addr)
        target_findings = lookup(target_addr)
        if not source_findings or not target_findings:
            continue
        seen_pairs.add(pair)
        target_ids = [f["finding_id"] for f in target_findings if "finding_id" in f]
        for sf in source_findings:
            sf.setdefault("cross_domain_refs", []).append({
                "kind": "upstream_dependency",
                "upstream_resource": target_addr,
                "upstream_finding_ids": target_ids,
            })
        notes.append(
            f"{_resource_name(source_addr)} depends on {_resource_name(target_addr)};"
            f" both have findings -- remediate {_resource_name(target_addr)} first"
            f" to realize {_resource_name(source_addr)} savings."
        )

    # 2. Retry amplification: upstream errors inflate cost; rightsizing alone won't help.
    for resource, metrics in metric_facts.items():
        ratio = metrics.get("retry_amplification_ratio")
        if ratio is None or ratio <= 1.5:
            continue
        resource_findings = lookup(resource)
        if not resource_findings:
            continue
        for rf in resource_findings:
            rf.setdefault("cross_domain_refs", []).append({
                "kind": "retry_amplification",
                "retry_amplification_ratio": ratio,
            })
        notes.append(
            f"{resource}: retry_amplification_ratio={ratio} --"
            " upstream errors may inflate cost; resolve root cause before rightsizing."
        )

    # 3. Request amplification: downstream fan-out inflates storage/cache spend.
    for resource, metrics in metric_facts.items():
        ratio = metrics.get("request_invocation_ratio")
        if ratio is None or ratio <= 2.0:
            continue
        resource_findings = lookup(resource)
        if not resource_findings:
            continue
        for rf in resource_findings:
            rf.setdefault("cross_domain_refs", []).append({
                "kind": "request_amplification",
                "request_invocation_ratio": ratio,
            })
        notes.append(
            f"{resource}: request_invocation_ratio={ratio} --"
            " downstream amplification detected; storage or cache lifecycle changes alone will not reduce cost."
        )

    # 4. Multi-platform LLM TCO conflict: Bedrock + hosted accelerator.
    if "bedrock" in domains and ({"sagemaker", "ec2"} & domains):
        bedrock_findings = [f for f in annotated if f.get("domain") == "bedrock"]
        hosted_findings = [f for f in annotated if f.get("domain") in {"sagemaker", "ec2"}]
        bedrock_savings = sum(
            float(f.get("estimated_monthly_saving_usd") or 0)
            for f in bedrock_findings
        )
        hosted_savings = sum(
            float(f.get("estimated_monthly_saving_usd") or 0)
            for f in hosted_findings
        )
        if bedrock_findings and hosted_findings:
            notes.append(
                f"Bedrock (${bedrock_savings:.0f}/mo potential) and hosted accelerator"
                f" (${hosted_savings:.0f}/mo potential) both have findings --"
                " TCO comparison required before platform-level remediation."
            )

    # 5. Cost spike correlated with structural waste findings.
    #    Service names live in drilldown[].services[], not in spikes[].
    spikes = anomaly.get("spikes", [])
    if spikes:
        drilldown_services: set[str] = set()
        for entry in anomaly.get("drilldown", []):
            for svc in entry.get("services", []):
                raw = str(svc.get("service", "")).lower()
                domain = _domain_from_service(raw)
                if domain:
                    drilldown_services.add(domain)
        high_conf_in_spike_domains = [
            f for f in findings
            if f.get("confidence") == "HIGH" and str(f.get("domain", "")) in drilldown_services
        ]
        if high_conf_in_spike_domains:
            affected = ", ".join(sorted({str(f.get("domain")) for f in high_conf_in_spike_domains}))
            notes.append(
                f"Cost spike and HIGH-confidence findings overlap in {affected} --"
                " spike may be partially attributable to structural waste found."
            )
        elif drilldown_services:
            notes.append(
                f"Cost spike attributed to {', '.join(sorted(drilldown_services))} but no HIGH-confidence"
                " waste findings in those domains -- spike is likely transient or driven by workload growth."
            )
        else:
            notes.append(
                "Cost spike detected but service attribution is unavailable --"
                " reconcile with Cost Explorer before applying remediation."
            )

    # 6. ElastiCache low hit rate + RDS findings: cache is not absorbing reads,
    #    rightsizing RDS will not reduce cost until cache effectiveness is restored.
    if {"elasticache", "rds"} <= domains:
        low_hit_rate = False
        for fact in dependency_facts:
            if fact.get("kind") != "cache_hit_rate_pct":
                continue
            hit_rate_pct = _as_percent(fact.get("value"))
            if hit_rate_pct is not None and hit_rate_pct < 80:
                low_hit_rate = True
                break
        rds_findings = [f for f in annotated if f.get("domain") == "rds"]
        if low_hit_rate and rds_findings:
            for rf in rds_findings:
                rf.setdefault("cross_domain_refs", []).append({
                    "kind": "cache_miss_amplification",
                    "note": "ElastiCache hit rate < 80%; RDS load is cache-miss-driven.",
                })
            notes.append(
                "ElastiCache hit rate < 80% and RDS has findings --"
                " restore cache effectiveness before rightsizing RDS or savings will not materialize."
            )

    # 7. CloudWatch log group associations. These are strong only when a
    #    concrete log group and its associated compute/RDS resource both have findings.
    seen_log_pairs: set[tuple[str, str]] = set()
    for fact in dependency_facts:
        if fact.get("kind") != "log_group_association":
            continue
        log_group_resource = str(fact.get("source", ""))
        target_resource = str(fact.get("target", ""))
        pair = (log_group_resource, target_resource)
        if pair in seen_log_pairs:
            continue
        log_group_findings = lookup(log_group_resource)
        target_findings = lookup(target_resource)
        if not log_group_findings or not target_findings:
            continue
        seen_log_pairs.add(pair)
        log_group_finding_ids = [
            f["finding_id"] for f in log_group_findings if "finding_id" in f
        ]
        target_finding_ids = [
            f["finding_id"] for f in target_findings if "finding_id" in f
        ]
        log_group_name = str(fact.get("log_group_name", ""))
        target_service = str(fact.get("service", "compute")).lower()
        target_label = "Lambda" if target_service == "lambda" else "RDS" if target_service == "rds" else target_service
        for cf in log_group_findings:
            _append_cross_domain_ref(cf, {
                "kind": "log_group_association",
                "associated_resource": target_resource,
                "associated_finding_ids": target_finding_ids,
                "log_group_name": log_group_name,
            })
        for tf in target_findings:
            _append_cross_domain_ref(tf, {
                "kind": "log_group_association",
                "log_group_resource": log_group_resource,
                "log_group_finding_ids": log_group_finding_ids,
                "log_group_name": log_group_name,
            })
        notes.append(
            f"CloudWatch log group {_resource_name(log_group_resource)} is associated with "
            f"{target_label} {_resource_name(target_resource)}; review retention and emitted log volume together."
        )

    # 8. NAT Gateway + Lambda or ECS: outbound traffic through NAT inflates data-processing cost.
    if "nat" in domains and ({"lambda", "ecs"} & domains):
        compute_domains = sorted({"lambda", "ecs"} & domains)
        nat_findings = [f for f in findings if f.get("domain") == "nat"]
        if nat_findings:
            notes.append(
                f"NAT Gateway and {'/'.join(compute_domains)} are both present --"
                " outbound traffic from compute through NAT drives data-processing cost;"
                " validate VPC endpoints and traffic volume before acting on NAT findings alone."
            )

    associated_log_groups = {
        str(fact.get("source", ""))
        for fact in dependency_facts
        if fact.get("kind") == "log_group_association"
    }
    if "cloudwatch" in domains:
        for finding in annotated:
            if finding.get("domain") != "cloudwatch":
                continue
            resource = str(finding.get("resource", ""))
            if resource in associated_log_groups:
                continue
            log_group_name = str(finding.get("display_name") or resource)
            hypotheses.append({
                "kind": "cloudwatch_retention_review",
                "status": "hypothesis",
                "resource": resource,
                "finding_ids": [finding["finding_id"]] if "finding_id" in finding else [],
                "fact_ids": [],
                "statement": (
                    f"CloudWatch log group {log_group_name} has a retention finding but no observed "
                    "compute/RDS association in the evidence; review emitted volume and owner before "
                    "treating it as a cross-domain cost driver."
                ),
            })

    if not notes:
        notes.append("No cross-domain risk pattern detected from available evidence.")

    return notes, annotated, hypotheses


def _build_log_group_association_facts(
    *,
    run_id: str | None,
    resources: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    lambda_by_function_name: dict[str, str] = {}
    rds_by_identifier: dict[str, str] = {}

    for resource_name, record in sorted(resources.items()):
        resource_type = _record_resource_type(record)
        configuration = _record_config(record)
        service = _domain_from_service(record.get("service"))
        if service == "lambda" or resource_type == "aws_lambda_function":
            function_name = (
                configuration.get("function_name")
                or record.get("function_name")
                or str(record.get("resource_id", "")).rsplit(":", 1)[-1]
            )
            if isinstance(function_name, str) and function_name:
                lambda_by_function_name[function_name] = resource_name
        elif service == "rds" or resource_type == "aws_db_instance":
            identifier = configuration.get("identifier") or record.get("identifier") or record.get("resource_id")
            if isinstance(identifier, str) and identifier:
                rds_by_identifier[identifier] = resource_name

    log_group_records: dict[str, tuple[str, dict[str, Any]]] = {}
    for resource_name, record in sorted(resources.items()):
        resource_type = _record_resource_type(record)
        service = _domain_from_service(record.get("service"))
        if service != "cloudwatch" and resource_type != "aws_cloudwatch_log_group":
            continue
        log_group_name = _record_log_group_name(record)
        if not log_group_name:
            continue
        existing = log_group_records.get(log_group_name)
        if existing is None or existing[0].startswith("arn:"):
            log_group_records[log_group_name] = (resource_name, record)

    facts: list[dict[str, Any]] = []
    for log_group_name, (resource_name, _record) in sorted(log_group_records.items()):
        target_resource = None
        target_type = None
        target_service = None
        if log_group_name.startswith("/aws/lambda/"):
            function_name = log_group_name.removeprefix("/aws/lambda/")
            target_resource = lambda_by_function_name.get(function_name)
            target_type = "aws_lambda_function"
            target_service = "lambda"
        elif log_group_name.startswith("/aws/rds/"):
            identifier = log_group_name.removeprefix("/aws/rds/")
            target_resource = rds_by_identifier.get(identifier)
            target_type = "aws_db_instance"
            target_service = "rds"

        if not target_resource or not target_type or not target_service:
            continue
        facts.append({
            "fact_id": stable_id(run_id, "log_group_association", resource_name, target_resource),
            "kind": "log_group_association",
            "source": resource_name,
            "source_type": "aws_cloudwatch_log_group",
            "target": target_resource,
            "target_type": target_type,
            "service": target_service,
            "log_group_name": log_group_name,
            "status": "observed",
        })
    return facts


def _build_dependency_facts(
    *,
    run_id: str | None,
    terraform_path: str | None,
    resources: dict[str, dict[str, Any]],
    read_text: Callable[[Path], str],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if terraform_path:
        blocks = _resource_blocks(read_text(Path(terraform_path)))
        by_address = {(block["type"], block["name"]): block for block in blocks}
        for source in blocks:
            refs = re.findall(r"(aws_[A-Za-z0-9_]+)\.([A-Za-z0-9_-]+)\.", source["text"])
            for target_type, target_name in sorted(set(refs)):
                target = by_address.get((target_type, target_name))
                if not target or (target_type, target_name) == (source["type"], source["name"]):
                    continue
                source_address = f"{source['type']}.{source['name']}"
                target_address = f"{target_type}.{target_name}"
                fact_id = stable_id(run_id, "dependency", source_address, target_address)
                facts.append({
                    "fact_id": fact_id,
                    "kind": "terraform_reference",
                    "source": source_address,
                    "source_type": source["type"],
                    "target": target_address,
                    "target_type": target["type"],
                    "status": "observed",
                })

    facts.extend(_build_log_group_association_facts(run_id=run_id, resources=resources))

    for resource_name, record in sorted(resources.items()):
        metrics = record.get("metrics", {})
        if not isinstance(metrics, dict):
            continue

        def metric_average(*names: str) -> float | None:
            for name in names:
                value = _avg(_series(metrics.get(name)))
                if value is not None:
                    return value
            return None

        invocations = metric_average("invocations", "invocation_count")
        requests = metric_average("downstream_requests", "request_count", "requests")
        retries = metric_average("retries", "retry_count")
        cache_hit_rate = metric_average("cache_hit_rate_pct", "cache_hit_rate")

        derived: list[tuple[str, float, dict[str, Any]]] = []
        if invocations is not None and invocations > 0 and requests is not None:
            derived.append((
                "request_invocation_ratio",
                round(requests / invocations, 4),
                {"requests_avg": requests, "invocations_avg": invocations},
            ))
        if invocations is not None and invocations > 0 and retries is not None:
            derived.append((
                "retry_amplification_ratio",
                round(retries / invocations, 4),
                {"retries_avg": retries, "invocations_avg": invocations},
            ))
        cache_hit_rate_pct = _as_percent(cache_hit_rate)
        if cache_hit_rate_pct is not None:
            derived.append(("cache_hit_rate_pct", round(cache_hit_rate_pct, 4), {}))

        for kind, value, inputs in derived:
            facts.append({
                "fact_id": stable_id(run_id, "dependency_metric", resource_name, kind),
                "kind": kind,
                "resource": resource_name,
                "value": value,
                "inputs": inputs,
                "status": "observed",
            })
    return sorted(
        facts,
        key=lambda fact: (
            str(fact.get("source", fact.get("resource", ""))),
            str(fact.get("target", fact.get("kind", ""))),
            fact["fact_id"],
        ),
    )


def build_cross_domain_review(
    *,
    run_id: str | None,
    domains: list[str],
    findings: list[dict[str, Any]],
    anomaly: dict[str, Any],
    terraform_path: str | None,
    resources: dict[str, dict[str, Any]],
    read_text: Callable[[Path], str],
) -> dict[str, Any]:
    dependency_facts = _build_dependency_facts(
        run_id=run_id,
        terraform_path=terraform_path,
        resources=resources,
        read_text=read_text,
    )
    notes, annotated_findings, hypotheses = _cross_domain_analysis(
        set(domains), findings, anomaly, dependency_facts
    )
    return {
        "notes": notes,
        "hypotheses": hypotheses,
        "dependency_facts": dependency_facts,
        "findings": annotated_findings,
    }
