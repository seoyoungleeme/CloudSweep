"""LangGraph orchestration runtime for CloudSweep FinOps analysis.

The Claude skill files remain the source of analyst instructions. This module
turns the same workflow into an executable graph so scenarios can be analyzed
repeatably from the command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import operator
import re
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from .enrichment import EnrichmentProvider, FallbackEnrichmentProvider
from .rule_engine import AnalyzerRegistration, AnalyzerRegistry, RuleValidationError, stable_id


DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bedrock": ("aws_bedrock*", "aws_bedrockagent*"),
    "sagemaker": ("aws_sagemaker*",),
    "ec2": ("aws_instance", "aws_launch_template", "aws_autoscaling_group", "aws_spot_instance_request"),
    "lambda": ("aws_lambda_function",),
    "s3": ("aws_s3_bucket", "aws_s3_bucket_lifecycle_configuration"),
    "dynamodb": ("aws_dynamodb_table", "aws_appautoscaling_target", "aws_appautoscaling_policy"),
    "rds": ("aws_db_instance",),
    "elb": ("aws_lb", "aws_elb", "aws_alb"),
    "ebs": ("aws_ebs_snapshot",),
    "ecs": ("aws_ecs_service", "aws_ecs_task_definition"),
    "elasticache": ("aws_elasticache_replication_group",),
    "sqs": ("aws_sqs_queue",),
    "kinesis": ("aws_kinesis_stream",),
    "nat": ("aws_nat_gateway", "aws_vpc_endpoint"),
    "tgw": ("aws_ec2_transit_gateway",),
    "cloudwatch": ("aws_cloudwatch_log_group",),
    "cloudwatch-alarm": ("aws_cloudwatch_metric_alarm",),
    "organizations": ("aws_account", "aws_organization"),
}

SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "bedrock": ("bedrock", "amazon bedrock"),
    "sagemaker": ("sagemaker", "amazon sagemaker", "amazon sagemaker ai"),
    "lambda": ("lambda", "aws lambda"),
    "s3": ("s3", "amazon s3", "amazon simple storage service"),
    "dynamodb": ("dynamodb", "amazon dynamodb"),
    "rds": ("rds", "amazon rds", "amazon relational database service"),
    "elb": ("elb", "alb", "elastic load balancing"),
    "ebs": ("ebs", "amazon ebs", "amazon elastic block store"),
    "ec2": ("ec2", "amazon ec2", "amazon elastic compute cloud"),
    "cloudwatch": ("cloudwatch", "amazon cloudwatch"),
    "cloudwatch-alarm": ("cloudwatch", "amazon cloudwatch"),
    "ecs": ("ecs", "amazon ecs", "fargate"),
    "elasticache": ("elasticache", "amazon elasticache"),
    "sqs": ("sqs", "amazon sqs", "amazon simple queue service"),
    "kinesis": ("kinesis", "amazon kinesis"),
    "nat": ("nat gateway", "amazon ec2"),
    "tgw": ("transit gateway", "amazon ec2"),
    "organizations": ("organizations", "aws organizations"),
}


class CloudSweepState(TypedDict, total=False):
    schema_version: str
    run_id: str
    work_dir: str
    result_dir: str
    write: bool
    standard_output: bool
    evidence: dict[str, Any]
    intent: str
    execution_plan: list[str]
    domains: list[str]
    domain_resources: dict[str, list[str]]
    cost_summary: dict[str, Any]
    anomaly: dict[str, Any]
    findings: list[dict[str, Any]]
    cross_domain_notes: list[str]
    optimized_tf: str
    report_markdown: str
    output_paths: dict[str, str]
    warnings: list[str]
    trace: list[str]
    analysis_domain: str
    domain_results: Annotated[list[dict[str, Any]], operator.add]
    enrichment_status: dict[str, Any]
    require_approval: bool
    approval_threshold_usd: float
    approval_status: str
    approval_decision: dict[str, Any]
    analyzer_coverage: list[dict[str, str]]
    dependency_facts: list[dict[str, Any]]


class ResourceBlock(TypedDict):
    type: str
    name: str
    text: str
    start: int
    end: int


def _append(state: CloudSweepState, key: str, values: list[str]) -> list[str]:
    return [*state.get(key, []), *values]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _existing(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _metric_path(work_dir: Path) -> Path | None:
    candidates = [work_dir / "metrics.json", work_dir / "metrics" / "metrics.json"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _inventory_evidence(work_dir: Path) -> dict[str, Any]:
    mock_dir = work_dir / "mock_responses"
    ce_files = sorted(str(path) for path in mock_dir.glob("get_cost_and_usage*.json"))
    cloudtrail_files = sorted(str(path) for path in mock_dir.glob("cloudtrail*.json"))
    if (work_dir / "cloudtrail.json").exists():
        cloudtrail_files.append(str(work_dir / "cloudtrail.json"))

    metric_path = _metric_path(work_dir)
    evidence = {
        "terraform": _existing(work_dir / "main.tf"),
        "genai_evidence": _existing(work_dir / "genai_evidence.json"),
        "metrics": str(metric_path) if metric_path else None,
        "cost_report": _existing(work_dir / "cost_report.json"),
        "parsed_input": _existing(work_dir / "parsed_input.json"),
        "existing_findings": _existing(work_dir / "findings.json"),
        "cost_explorer": ce_files,
        "anomalies": _existing(mock_dir / "get_anomalies.json"),
        "cloudtrail": cloudtrail_files,
    }
    evidence["available"] = sorted(key for key, value in evidence.items() if value and key != "available")
    return evidence


def _infer_intent(work_dir: Path, evidence: dict[str, Any]) -> str:
    readme = ""
    readme_path = work_dir / "README.md"
    if readme_path.exists():
        readme = _read_text(readme_path).lower()

    has_incident = bool(evidence.get("cost_explorer") or evidence.get("anomalies"))
    has_waste = bool(evidence.get("terraform") or evidence.get("metrics") or evidence.get("cost_report"))
    incident_words = ("spike", "anomaly", "cost explorer", "hourly", "cloudtrail")
    waste_words = ("rightsizing", "overprovision", "lifecycle", "unused", "waste", "terraform")

    if has_incident and has_waste:
        return "blended"
    if has_incident or any(word in readme for word in incident_words):
        return "cost_spike_incident"
    if has_waste or any(word in readme for word in waste_words):
        return "waste_optimization"
    return "unknown"


def _build_execution_plan(evidence: dict[str, Any], intent: str) -> list[str]:
    plan: list[str] = []
    if evidence.get("cost_explorer") or evidence.get("anomalies"):
        plan.append("anomaly_analysis")
    if any(evidence.get(key) for key in ("terraform", "genai_evidence", "metrics", "parsed_input", "cost_report")):
        plan.append("domain_analysis")
    if not plan and evidence.get("existing_findings"):
        plan.append("existing_findings_summary")
    plan.append("report")
    return plan


def inventory_node(state: CloudSweepState) -> dict[str, Any]:
    work_dir = Path(state["work_dir"]).resolve()
    result_dir = Path(state.get("result_dir") or work_dir / "result").resolve()
    evidence = _inventory_evidence(work_dir)
    intent = _infer_intent(work_dir, evidence)
    return {
        "work_dir": str(work_dir),
        "result_dir": str(result_dir),
        "evidence": evidence,
        "intent": intent,
        "trace": _append(state, "trace", [f"inventory: {', '.join(evidence['available']) or 'no known evidence'}"]),
    }


def plan_node(state: CloudSweepState) -> dict[str, Any]:
    plan = _build_execution_plan(state["evidence"], state["intent"])
    return {
        "execution_plan": plan,
        "trace": _append(state, "trace", [f"plan: {' -> '.join(plan)}"]),
    }


def _route_from_plan(state: CloudSweepState) -> Literal["anomaly_analysis", "detect_domains", "render_outputs"]:
    plan = state.get("execution_plan", [])
    if "anomaly_analysis" in plan:
        return "anomaly_analysis"
    if "domain_analysis" in plan:
        return "detect_domains"
    return "render_outputs"


def _route_after_anomaly(state: CloudSweepState) -> Literal["detect_domains", "render_outputs"]:
    if "domain_analysis" in state.get("execution_plan", []):
        return "detect_domains"
    return "render_outputs"


def _resource_blocks(tf_text: str) -> list[ResourceBlock]:
    blocks: list[ResourceBlock] = []
    header = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
    for match in header.finditer(tf_text):
        depth = 0
        end = match.end()
        for idx in range(match.end() - 1, len(tf_text)):
            char = tf_text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        blocks.append(
            {
                "type": match.group(1),
                "name": match.group(2),
                "text": tf_text[match.start():end],
                "start": match.start(),
                "end": end,
            }
        )
    return blocks


def _resource_type_matches(resource_type: str, keyword: str) -> bool:
    if keyword.endswith("*"):
        return resource_type.startswith(keyword[:-1])
    return resource_type == keyword


def _detect_domains(tf_text: str) -> tuple[list[str], dict[str, list[str]]]:
    seen: list[str] = []
    resources: dict[str, list[str]] = {}
    for block in _resource_blocks(tf_text):
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(_resource_type_matches(block["type"], keyword) for keyword in keywords):
                if domain not in seen:
                    seen.append(domain)
                resources.setdefault(domain, []).append(block["name"])
    return seen, resources


def _add_domain_resource(
    domains: list[str],
    resources: dict[str, list[str]],
    domain: str,
    resource_name: str,
) -> None:
    if domain not in domains:
        domains.append(domain)
    domain_resources = resources.setdefault(domain, [])
    if resource_name not in domain_resources:
        domain_resources.append(resource_name)


def _domain_from_service(service: Any) -> str | None:
    service_name = str(service or "").strip().lower()
    if not service_name:
        return None
    for domain, aliases in SERVICE_ALIASES.items():
        if any(alias == service_name or alias in service_name for alias in aliases):
            return domain
    return None


def _domains_from_records(data: Any) -> tuple[list[str], dict[str, list[str]]]:
    if not isinstance(data, dict):
        return [], {}

    records: list[tuple[str, dict[str, Any]]] = []
    resources = data.get("resources")
    if isinstance(resources, dict):
        records.extend((str(name), record) for name, record in resources.items() if isinstance(record, dict))
    elif isinstance(resources, list):
        records.extend(
            (str(record.get("resource_id") or record.get("name") or f"resource-{index}"), record)
            for index, record in enumerate(resources)
            if isinstance(record, dict)
        )

    tf_resources = data.get("tf_resources")
    if isinstance(tf_resources, list):
        records.extend(
            (str(record.get("resource_id") or record.get("name") or f"tf-resource-{index}"), record)
            for index, record in enumerate(tf_resources)
            if isinstance(record, dict)
        )

    domains: list[str] = []
    domain_resources: dict[str, list[str]] = {}
    for resource_name, record in records:
        explicit_domain = str(record.get("domain") or "").strip().lower()
        service_domain = _domain_from_service(record.get("service"))
        resource_type = str(record.get("resource_type") or record.get("type") or "")
        matched_domains = [
            domain
            for domain, keywords in DOMAIN_KEYWORDS.items()
            if resource_type and any(_resource_type_matches(resource_type, keyword) for keyword in keywords)
        ]
        candidates = [explicit_domain, service_domain, *matched_domains]
        for domain in candidates:
            if domain in DOMAIN_KEYWORDS:
                _add_domain_resource(domains, domain_resources, domain, resource_name)
    return domains, domain_resources


def _domains_from_cost_report(path: str | None) -> tuple[list[str], dict[str, list[str]]]:
    if not path:
        return [], {}
    data = _load_json(Path(path))
    months = data.get("monthly_data") or data.get("months") or data.get("cost_summary", {}).get("months") or []
    domains: list[str] = []
    resources: dict[str, list[str]] = {}
    for month in months:
        for service in month.get("services", []):
            if not isinstance(service, dict):
                continue
            service_name = str(service.get("service") or "")
            domain = _domain_from_service(service_name)
            if domain:
                _add_domain_resource(domains, resources, domain, f"cost:{service_name}")
    return domains, resources


def _validate_genai_evidence(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["genai_evidence.json must contain a JSON object"]
    errors: list[str] = []
    if data.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    else:
        for field in ("period_start", "period_end", "period_days", "resolution", "region", "currency"):
            if field not in metadata:
                errors.append(f"metadata.{field} is required")
        if "period_days" in metadata and (
            not isinstance(metadata["period_days"], int) or isinstance(metadata["period_days"], bool) or metadata["period_days"] < 1
        ):
            errors.append("metadata.period_days must be a positive integer")
        if "resolution" in metadata and metadata["resolution"] not in {"hourly", "daily", "monthly"}:
            errors.append("metadata.resolution must be hourly, daily, or monthly")
        if "currency" in metadata and metadata["currency"] != "USD":
            errors.append("metadata.currency must be USD")
    resources = data.get("resources")
    if not isinstance(resources, dict) or not resources:
        errors.append("resources must be a non-empty object")
        return errors
    for name, record in resources.items():
        if not isinstance(record, dict):
            errors.append(f"resources.{name} must be an object")
            continue
        service = record.get("service")
        if service not in {"bedrock", "sagemaker", "ec2"}:
            errors.append(f"resources.{name}.service must be bedrock, sagemaker, or ec2")
        if not isinstance(record.get("resource_type"), str) or not record["resource_type"]:
            errors.append(f"resources.{name}.resource_type must be a non-empty string")
        if not isinstance(record.get("configuration"), dict):
            errors.append(f"resources.{name}.configuration must be an object")
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            errors.append(f"resources.{name}.metrics must be an object")
        else:
            for metric_name, metric in metrics.items():
                prefix = f"resources.{name}.metrics.{metric_name}"
                if not isinstance(metric, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                if not isinstance(metric.get("unit"), str) or not metric["unit"]:
                    errors.append(f"{prefix}.unit must be a non-empty string")
                datapoints = metric.get("datapoints")
                if not isinstance(datapoints, list) or any(
                    not isinstance(value, (int, float)) or isinstance(value, bool) for value in datapoints
                ):
                    errors.append(f"{prefix}.datapoints must be an array of numbers")

        if service == "bedrock" and not isinstance(record.get("model_id"), str):
            errors.append(f"resources.{name}.model_id is required for bedrock")
        if service == "sagemaker":
            for field in ("endpoint_name", "instance_type"):
                if not isinstance(record.get(field), str) or not record[field]:
                    errors.append(f"resources.{name}.{field} is required for sagemaker")
            if not isinstance(record.get("instance_count"), int) or isinstance(record.get("instance_count"), bool):
                errors.append(f"resources.{name}.instance_count is required for sagemaker")
        if service == "ec2":
            instance_type = record.get("instance_type")
            if not isinstance(instance_type, str) or not re.match(r"^(g|p|inf|trn)[0-9]", instance_type):
                errors.append(f"resources.{name}.instance_type must be an accelerator family for ec2")
            if not isinstance(record.get("instance_count"), int) or isinstance(record.get("instance_count"), bool):
                errors.append(f"resources.{name}.instance_count is required for ec2")

        costs = record.get("costs")
        if costs is not None and (
            not isinstance(costs, dict)
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in costs.values())
        ):
            errors.append(f"resources.{name}.costs must contain only numeric values")
    return errors


def detect_domains_node(state: CloudSweepState) -> dict[str, Any]:
    tf_path = state["evidence"].get("terraform")
    domains: list[str] = []
    resources: dict[str, list[str]] = {}
    warnings: list[str] = []

    def merge(found_domains: list[str], found_resources: dict[str, list[str]]) -> None:
        for domain in found_domains:
            for resource_name in found_resources.get(domain, []):
                _add_domain_resource(domains, resources, domain, resource_name)

    if tf_path:
        merge(*_detect_domains(_read_text(Path(tf_path))))

    for evidence_key in ("genai_evidence", "metrics", "parsed_input"):
        evidence_path = state["evidence"].get(evidence_key)
        if not evidence_path:
            continue
        data = _load_json(Path(evidence_path))
        if evidence_key == "genai_evidence":
            warnings.extend(f"Invalid GenAI evidence: {error}" for error in _validate_genai_evidence(data))
        merge(*_domains_from_records(data))

    merge(*_domains_from_cost_report(state["evidence"].get("cost_report")))
    return {
        "domains": domains,
        "domain_resources": resources,
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", [f"domains: {', '.join(domains) or 'none'}"]),
    }


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


def _pctl(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[low], 4)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (rank - low), 4)


def _attr(block_text: str, name: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(block_text)
    if not match:
        return None
    value = match.group(1).split("#", 1)[0].strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _attr_int(block_text: str, name: str) -> int | None:
    value = _attr(block_text, name)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _attr_float(block_text: str, name: str) -> float | None:
    value = _attr(block_text, name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _attr_bool(block_text: str, name: str) -> bool | None:
    value = _attr(block_text, name)
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return None


def _tag_value(block_text: str, name: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*\"([^\"]+)\"", block_text, re.MULTILINE | re.IGNORECASE)
    return match.group(1) if match else None


def _load_metric_resources(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    data = _load_json(Path(path))
    if isinstance(data, dict) and isinstance(data.get("resources"), dict):
        return data["resources"]
    if isinstance(data, dict) and isinstance(data.get("metrics"), dict):
        return {
            key: {"resource_type": "unknown", "metrics": value, "is_problem": None}
            for key, value in data["metrics"].items()
        }
    return {}


def _metric_record(metrics: dict[str, dict[str, Any]], block: ResourceBlock) -> dict[str, Any] | None:
    names = [
        block["name"],
        _attr(block["text"], "function_name"),
        _attr(block["text"], "name"),
        _attr(block["text"], "bucket"),
    ]
    for name in [item for item in names if item]:
        if name in metrics:
            return metrics[name]
    for key, value in metrics.items():
        if any(name and (key.endswith(name) or name in key) for name in names):
            return value
    return None


def _load_cost_summary(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    data = _load_json(Path(path))
    months = data.get("monthly_data") or data.get("months") or data.get("cost_summary", {}).get("months") or []
    period_months = data.get("period_months") or len(months) or 1
    summary: dict[str, Any] = {
        "period_months": period_months,
        "pricing_note": (
            data.get("summary", {}).get("pricing_note")
            or data.get("pricing_note")
            or data.get("cost_summary", {}).get("pricing_note")
            or ""
        ),
        "domains": {},
    }
    for domain, aliases in SERVICE_ALIASES.items():
        total = 0.0
        contains_waste = False
        for month in months:
            for service in month.get("services", []):
                service_name = str(service.get("service", "")).lower()
                if any(alias in service_name for alias in aliases):
                    total += float(service.get("spend_usd", 0) or 0)
                    contains_waste = contains_waste or bool(service.get("contains_waste"))
        if total:
            summary["domains"][domain] = {
                "total_period_spend_usd": round(total, 2),
                "avg_monthly_spend_usd": round(total / period_months, 2),
                "contains_waste": contains_waste,
            }
    return summary


def _domain_cost(cost_summary: dict[str, Any], domain: str) -> float:
    return float(cost_summary.get("domains", {}).get(domain, {}).get("avg_monthly_spend_usd", 0.0))


def _merge_record(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {**base, **incoming}
    for key in ("configuration", "metrics", "costs"):
        left = base.get(key)
        right = incoming.get(key)
        if isinstance(left, dict) or isinstance(right, dict):
            merged[key] = {
                **(left if isinstance(left, dict) else {}),
                **(right if isinstance(right, dict) else {}),
            }
    return merged


def _load_analysis_resources(evidence: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    metadata: dict[str, Any] = {}
    for evidence_key in ("parsed_input", "metrics", "genai_evidence"):
        path = evidence.get(evidence_key)
        if not path:
            continue
        data = _load_json(Path(path))
        if not isinstance(data, dict):
            continue
        if isinstance(data.get("metadata"), dict):
            metadata.update(data["metadata"])
        raw_resources = data.get("resources")
        if isinstance(raw_resources, dict):
            for name, record in raw_resources.items():
                if isinstance(record, dict):
                    resources[str(name)] = _merge_record(resources.get(str(name), {}), record)
        tf_resources = data.get("tf_resources")
        if isinstance(tf_resources, list):
            for index, record in enumerate(tf_resources):
                if not isinstance(record, dict):
                    continue
                name = str(record.get("resource_id") or record.get("name") or f"tf-resource-{index}")
                resources[name] = _merge_record(resources.get(name, {}), record)
    return resources, metadata


def _record_domain(record: dict[str, Any]) -> str | None:
    explicit = str(record.get("domain") or "").strip().lower()
    if explicit in DOMAIN_KEYWORDS:
        return explicit
    service = _domain_from_service(record.get("service"))
    if service:
        return service
    resource_type = str(record.get("resource_type") or record.get("type") or "")
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(_resource_type_matches(resource_type, keyword) for keyword in keywords):
            return domain
    return None


def _metric_values(record: dict[str, Any], name: str) -> list[float]:
    return _series(record.get("metrics", {}).get(name, {}))


def _metric_avg(record: dict[str, Any], name: str) -> float | None:
    return _avg(_metric_values(record, name))


def _metric_p95(record: dict[str, Any], name: str) -> float | None:
    return _pctl(_metric_values(record, name), 0.95)


def _monthly_metric_total(record: dict[str, Any], name: str, metadata: dict[str, Any]) -> float | None:
    values = _metric_values(record, name)
    if not values:
        return None
    period_days = metadata.get("period_days")
    if isinstance(period_days, (int, float)) and period_days > 0:
        return sum(values) * 30.0 / float(period_days)
    return sum(values)


def _number(source: dict[str, Any], name: str) -> float | None:
    value = source.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _record_number(record: dict[str, Any], name: str) -> float | None:
    for section_name in ("costs", "configuration"):
        section = record.get(section_name, {})
        if isinstance(section, dict):
            value = _number(section, name)
            if value is not None:
                return value
    return _number(record, name)


def _record_bool(record: dict[str, Any], name: str, default: bool = False) -> bool:
    configuration = record.get("configuration", {})
    value = configuration.get(name) if isinstance(configuration, dict) else None
    return value if isinstance(value, bool) else default


def _pricing_source(record: dict[str, Any], cost_summary: dict[str, Any]) -> str:
    if record.get("costs"):
        return "genai_evidence"
    if _domain_cost(cost_summary, _record_domain(record) or ""):
        return "cost_report"
    return "unavailable"


def _coefficient_of_variation(values: list[float]) -> float | None:
    if not values:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return statistics.pstdev(values) / mean


def _replace_attr(block_text: str, attr_name: str, value: int | str) -> str:
    replacement = f"  {attr_name} = {value}"
    pattern = re.compile(rf"^(\s*){re.escape(attr_name)}\s*=\s*.+$", re.MULTILINE)
    if pattern.search(block_text):
        return pattern.sub(lambda m: f"{m.group(1)}{attr_name} = {value}", block_text, count=1)
    insert_at = block_text.rfind("}")
    return block_text[:insert_at].rstrip() + "\n\n" + replacement + "\n" + block_text[insert_at:]


def _next_lambda_memory(observed_p99_mb: float | None) -> int:
    if observed_p99_mb is None:
        return 512
    target = max(128, observed_p99_mb * 2)
    for size in (128, 256, 512, 768, 1024, 1536, 2048):
        if target <= size:
            return size
    return int(math.ceil(target / 512) * 512)


def _analyze_lambda(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    lambda_blocks = [block for block in blocks if block["type"] == "aws_lambda_function"]
    findings: list[dict[str, Any]] = []
    flagged: list[tuple[ResourceBlock, dict[str, Any], int, int]] = []
    for block in lambda_blocks:
        allocated = _attr_int(block["text"], "memory_size")
        record = _metric_record(metrics, block)
        metric_values = _series((record or {}).get("metrics", {}).get("memory_used_mb", {}))
        p99 = _pctl(metric_values, 0.99)
        avg = _avg(metric_values)
        is_problem = bool((record or {}).get("is_problem"))
        if allocated and allocated >= 1024 and ((p99 is not None and p99 / allocated < 0.2) or is_problem):
            recommended = min(allocated, _next_lambda_memory(p99))
            flagged.append((block, {"avg": avg, "p99": p99, "points": len(metric_values)}, allocated, recommended))

    monthly = _domain_cost(cost_summary, "lambda")
    for block, metric_summary, allocated, recommended in flagged:
        per_resource = round((monthly * max(0.0, 1 - recommended / allocated)) / max(len(flagged), 1), 2) if monthly else 0.0
        new_block = _replace_attr(block["text"], "memory_size", recommended)
        findings.append(
            {
                "domain": "lambda",
                "resource": block["name"],
                "rule_id": "LAMBDA_MEMORY_RIGHTSIZE",
                "severity": "HIGH",
                "confidence": "MEDIUM" if metric_summary["p99"] is not None else "LOW",
                "estimated_monthly_saving_usd": per_resource,
                "evidence": [
                    f"allocated_memory_mb={allocated}",
                    f"p99_memory_used_mb={metric_summary['p99']}",
                    f"datapoints={metric_summary['points']}",
                ],
                "recommendation": f"Set memory_size to {recommended} MB, then validate p95/p99 duration and errors.",
                "optimized_replacement": {"resource": block["name"], "text": new_block},
            }
        )
    return findings


def _lifecycle_targets(blocks: list[ResourceBlock]) -> set[str]:
    targets: set[str] = set()
    for block in blocks:
        if block["type"] != "aws_s3_bucket_lifecycle_configuration":
            continue
        refs = re.findall(r"aws_s3_bucket\.([A-Za-z0-9_-]+)\.", block["text"])
        targets.update(refs)
        bucket_literal = _attr(block["text"], "bucket")
        if bucket_literal:
            targets.add(bucket_literal)
    return targets


def _lifecycle_block(bucket_block: ResourceBlock) -> str:
    local = bucket_block["name"]
    return f'''

resource "aws_s3_bucket_lifecycle_configuration" "{local}_cloudsweep_lifecycle" {{
  bucket = aws_s3_bucket.{local}.id

  rule {{
    id     = "cloudsweep-standard-ia-then-glacier"
    status = "Enabled"

    transition {{
      days          = 30
      storage_class = "STANDARD_IA"
    }}

    transition {{
      days          = 90
      storage_class = "GLACIER"
    }}

    abort_incomplete_multipart_upload {{
      days_after_initiation = 7
    }}
  }}
}}
'''.strip()


def _analyze_s3(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    bucket_blocks = [block for block in blocks if block["type"] == "aws_s3_bucket"]
    lifecycle_targets = _lifecycle_targets(blocks)
    flagged: list[ResourceBlock] = []
    for block in bucket_blocks:
        bucket_name = _attr(block["text"], "bucket") or block["name"]
        record = _metric_record(metrics, block)
        is_problem = bool((record or {}).get("is_problem"))
        has_lifecycle = block["name"] in lifecycle_targets or bucket_name in lifecycle_targets
        if not has_lifecycle and (is_problem or _domain_cost(cost_summary, "s3") or "archive" in bucket_name or "raw" in bucket_name):
            flagged.append(block)

    monthly = _domain_cost(cost_summary, "s3")
    findings: list[dict[str, Any]] = []
    for block in flagged:
        bucket_name = _attr(block["text"], "bucket") or block["name"]
        per_resource = round((monthly * 0.75) / max(len(flagged), 1), 2) if monthly else 0.0
        findings.append(
            {
                "domain": "s3",
                "resource": block["name"],
                "rule_id": "S3_MISSING_LIFECYCLE",
                "severity": "MEDIUM",
                "confidence": "MEDIUM",
                "estimated_monthly_saving_usd": per_resource,
                "evidence": [f"bucket={bucket_name}", "no aws_s3_bucket_lifecycle_configuration reference found"],
                "recommendation": "Add lifecycle transitions only after validating restore, compliance, and access patterns.",
                "optimized_append": _lifecycle_block(block),
            }
        )
    return findings


def _has_autoscaling_for_table(blocks: list[ResourceBlock], table_name: str) -> bool:
    for block in blocks:
        if block["type"] not in {"aws_appautoscaling_target", "aws_appautoscaling_policy"}:
            continue
        if table_name in block["text"]:
            return True
    return False


def _analyze_dynamodb(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    table_blocks = [block for block in blocks if block["type"] == "aws_dynamodb_table"]
    findings: list[dict[str, Any]] = []
    flagged: list[tuple[ResourceBlock, dict[str, Any], int, int, int, int]] = []
    for block in table_blocks:
        billing = (_attr(block["text"], "billing_mode") or "PROVISIONED").strip('"')
        if billing != "PROVISIONED":
            continue
        read_capacity = _attr_int(block["text"], "read_capacity") or 0
        write_capacity = _attr_int(block["text"], "write_capacity") or 0
        record = _metric_record(metrics, block)
        metric_map = (record or {}).get("metrics", {})
        reads = _series(metric_map.get("consumed_read_capacity_units", {}))
        writes = _series(metric_map.get("consumed_write_capacity_units", {}))
        read_p99 = _pctl(reads, 0.99) or _avg(reads) or 0
        write_p99 = _pctl(writes, 0.99) or _avg(writes) or 0
        read_util = read_p99 / read_capacity if read_capacity else 0
        write_util = write_p99 / write_capacity if write_capacity else 0
        table_name = _attr(block["text"], "name") or block["name"]
        no_autoscaling = not _has_autoscaling_for_table(blocks, table_name)
        is_problem = bool((record or {}).get("is_problem"))
        if is_problem or (no_autoscaling and read_capacity and write_capacity and max(read_util, write_util) < 0.5):
            rec_read = max(1, int(math.ceil(read_p99 * 1.2)))
            rec_write = max(1, int(math.ceil(write_p99 * 1.2)))
            flagged.append((block, {"read_p99": read_p99, "write_p99": write_p99, "read_util": read_util, "write_util": write_util}, read_capacity, write_capacity, rec_read, rec_write))

    monthly = _domain_cost(cost_summary, "dynamodb")
    for block, metric_summary, read_capacity, write_capacity, rec_read, rec_write in flagged:
        before = read_capacity + write_capacity
        after = rec_read + rec_write
        per_resource = round(monthly * max(0.0, 1 - after / before) / max(len(flagged), 1), 2) if monthly and before else 0.0
        new_block = _replace_attr(block["text"], "read_capacity", rec_read)
        new_block = _replace_attr(new_block, "write_capacity", rec_write)
        findings.append(
            {
                "domain": "dynamodb",
                "resource": block["name"],
                "rule_id": "DYNAMODB_PROVISIONED_RIGHTSIZE",
                "severity": "HIGH",
                "confidence": "MEDIUM",
                "estimated_monthly_saving_usd": per_resource,
                "evidence": [
                    f"read_capacity={read_capacity}",
                    f"write_capacity={write_capacity}",
                    f"read_p99={round(metric_summary['read_p99'], 2)}",
                    f"write_p99={round(metric_summary['write_p99'], 2)}",
                ],
                "recommendation": f"Set read/write capacity to {rec_read}/{rec_write} and add Application Auto Scaling guardrails.",
                "optimized_replacement": {"resource": block["name"], "text": new_block},
            }
        )
    return findings


def _analyze_bedrock(
    resources: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
    cost_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    bedrock_records = [(name, record) for name, record in resources.items() if _record_domain(record) == "bedrock"]
    domain_spend = _domain_cost(cost_summary, "bedrock")

    for name, record in bedrock_records:
        costs = record.get("costs", {}) if isinstance(record.get("costs"), dict) else {}
        configuration = record.get("configuration", {}) if isinstance(record.get("configuration"), dict) else {}
        model_id = str(record.get("model_id") or name)
        source = _pricing_source(record, cost_summary)
        input_tokens = _monthly_metric_total(record, "input_tokens", metadata)
        output_tokens = _monthly_metric_total(record, "output_tokens", metadata)
        requests = _monthly_metric_total(record, "requests", metadata)
        input_price = _number(costs, "input_price_per_1m_tokens")
        output_price = _number(costs, "output_price_per_1m_tokens")
        scenario_spend = _number(costs, "monthly_spend_usd") or domain_spend
        on_demand = None
        if input_tokens is not None and output_tokens is not None and input_price is not None and output_price is not None:
            on_demand = input_tokens / 1_000_000 * input_price + output_tokens / 1_000_000 * output_price
        current_monthly = on_demand if on_demand is not None else scenario_spend

        steady_tpm = _metric_values(record, "traffic_tokens_per_minute")
        observed_tpm = _avg(steady_tpm)
        traffic_cv = _coefficient_of_variation(steady_tpm)
        committed_tpm = _record_number(record, "committed_tokens_per_minute")
        effective_utilization = (
            observed_tpm / committed_tpm * 100
            if observed_tpm is not None and committed_tpm is not None and committed_tpm > 0
            else None
        )
        committed_units = _record_number(record, "committed_units")
        hourly_price = _record_number(record, "hourly_price_per_unit")
        committed_hours = _record_number(record, "committed_hours_per_month")
        committed_monthly = (
            committed_units * hourly_price * committed_hours
            if committed_units is not None and hourly_price is not None and committed_hours is not None
            else None
        )
        observation_days = metadata.get("period_days")
        commitment_supported = _record_bool(record, "model_region_supports_commitment")
        throughput_need = _record_bool(record, "latency_or_throughput_need")

        if (
            current_monthly is not None
            and committed_monthly is not None
            and committed_monthly > 0
            and isinstance(observation_days, int)
            and observation_days >= 14
            and traffic_cv is not None
            and traffic_cv <= 0.35
            and effective_utilization is not None
            and effective_utilization >= 60
            and commitment_supported
            and throughput_need
        ):
            savings = current_monthly - committed_monthly
            savings_pct = savings / current_monthly * 100 if current_monthly else 0
            if savings > 0 and savings_pct >= 10:
                findings.append(
                    {
                        "domain": "bedrock",
                        "resource": name,
                        "rule_id": "BEDROCK_B1_THROUGHPUT_COMMIT",
                        "severity": "HIGH",
                        "confidence": "MEDIUM",
                        "estimated_monthly_saving_usd": round(savings, 2),
                        "savings_group": f"bedrock:{name}",
                        "evidence": [
                            f"model_id={model_id}",
                            f"on_demand_monthly_usd={round(current_monthly, 2)}",
                            f"committed_monthly_usd={round(committed_monthly, 2)}",
                            f"effective_utilization_pct={round(effective_utilization, 2)}",
                            f"traffic_cv={round(traffic_cv, 4)}",
                            f"pricing_source={source}",
                        ],
                        "recommendation": "Validate model/region support and p95/p99 latency, then evaluate committed throughput before purchase.",
                    }
                )

        if (
            _record_bool(record, "committed_capacity_exists")
            and committed_monthly is not None
            and effective_utilization is not None
            and effective_utilization < 40
        ):
            wasted_commitment = committed_monthly * max(0.0, 1 - effective_utilization / 100)
            findings.append(
                {
                    "domain": "bedrock",
                    "resource": name,
                    "rule_id": "BEDROCK_B2_UNDERUTILIZED_COMMITMENT",
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": round(wasted_commitment, 2),
                    "savings_group": f"bedrock:{name}",
                    "evidence": [
                        f"model_id={model_id}",
                        f"committed_monthly_usd={round(committed_monthly, 2)}",
                        f"effective_utilization_pct={round(effective_utilization, 2)}",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Review commitment size, traffic routing, and expiration before renewal; do not abandon an active commitment without contract review.",
                }
            )

        repeated_prefix = _metric_avg(record, "repeated_prefix_tokens")
        repeated_requests = _metric_avg(record, "repeated_requests_per_day")
        cache_read = _monthly_metric_total(record, "cache_read_tokens", metadata)
        if (
            repeated_prefix is not None
            and repeated_prefix >= 1024
            and repeated_requests is not None
            and repeated_requests >= 100
            and cache_read == 0
            and _record_bool(record, "model_supports_prompt_cache")
        ):
            repeated_tokens = repeated_prefix * repeated_requests * 30
            write_price = _number(costs, "cache_write_price_per_1m_tokens")
            read_price = _number(costs, "cache_read_price_per_1m_tokens")
            hit_rate = _record_number(record, "prompt_cache_hit_rate_target_pct") or 70.0
            prompt_savings = 0.0
            confidence = "LOW"
            if input_price is not None and write_price is not None and read_price is not None:
                uncached = repeated_tokens / 1_000_000 * input_price
                cached = repeated_tokens / 1_000_000 * (
                    (1 - hit_rate / 100) * write_price + (hit_rate / 100) * read_price
                )
                prompt_savings = max(0.0, uncached - cached)
                confidence = "MEDIUM"
            findings.append(
                {
                    "domain": "bedrock",
                    "resource": name,
                    "rule_id": "BEDROCK_B3_MISSING_PROMPT_CACHE",
                    "severity": "HIGH",
                    "confidence": confidence,
                    "estimated_monthly_saving_usd": round(prompt_savings, 2),
                    "savings_group": f"bedrock:{name}",
                    "evidence": [
                        f"model_id={model_id}",
                        f"repeated_prefix_tokens={round(repeated_prefix, 2)}",
                        f"repeated_requests_per_day={round(repeated_requests, 2)}",
                        "cache_read_tokens=0",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add prompt cache points for stable prefixes, then measure cache read/write tokens and review secrets or volatile policy text.",
                }
            )

        similar_rate = _metric_avg(record, "similar_query_rate_pct")
        expected_hit_rate = _metric_avg(record, "expected_cache_hit_rate_pct")
        semantic_absent = not _record_bool(record, "semantic_cache_layer_present")
        if (
            similar_rate is not None
            and similar_rate >= 15
            and expected_hit_rate is not None
            and expected_hit_rate >= 30
            and semantic_absent
            and scenario_spend >= 500
        ):
            embedding_cost = _number(costs, "embedding_cost_per_request")
            cache_node = _number(costs, "cache_node_monthly_cost")
            cache_network = _number(costs, "cache_network_and_storage_cost")
            semantic_savings = 0.0
            confidence = "LOW"
            if requests is not None and embedding_cost is not None and cache_node is not None and cache_network is not None:
                avoidable = scenario_spend * expected_hit_rate / 100
                semantic_cost = requests * embedding_cost + cache_node + cache_network
                semantic_savings = max(0.0, avoidable - semantic_cost)
                confidence = "MEDIUM"
            findings.append(
                {
                    "domain": "bedrock",
                    "resource": name,
                    "rule_id": "BEDROCK_B4_MISSING_SEMANTIC_CACHE",
                    "severity": "MEDIUM",
                    "confidence": confidence,
                    "estimated_monthly_saving_usd": round(semantic_savings, 2),
                    "savings_group": f"bedrock:{name}",
                    "evidence": [
                        f"model_id={model_id}",
                        f"similar_query_rate_pct={round(similar_rate, 2)}",
                        f"expected_cache_hit_rate_pct={round(expected_hit_rate, 2)}",
                        f"monthly_bedrock_spend_usd={round(scenario_spend, 2)}",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Pilot semantic caching with an explicit similarity threshold, TTL, invalidation, tenant isolation, PII controls, and fallback to Bedrock.",
                }
            )
    return findings


def _sagemaker_tf_records(blocks: list[ResourceBlock]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    endpoint_blocks = [block for block in blocks if block["type"] == "aws_sagemaker_endpoint"]
    config_blocks = [block for block in blocks if block["type"] == "aws_sagemaker_endpoint_configuration"]
    scaling_blocks = [
        block
        for block in blocks
        if block["type"] in {
            "aws_appautoscaling_target",
            "aws_appautoscaling_policy",
            "aws_appautoscaling_scheduled_action",
        }
    ]
    for config_block in config_blocks:
        endpoint = next(
            (
                block
                for block in endpoint_blocks
                if config_block["name"] in block["text"]
                or (_attr(config_block["text"], "name") and _attr(config_block["text"], "name") in block["text"])
            ),
            None,
        )
        endpoint_name = (
            _attr(endpoint["text"], "name") if endpoint else None
        ) or (endpoint["name"] if endpoint else config_block["name"])
        variant_name = _attr(config_block["text"], "variant_name") or "AllTraffic"
        control_text = "\n".join(
            block["text"]
            for block in scaling_blocks
            if endpoint_name in block["text"] and variant_name in block["text"]
        )
        records[endpoint_name] = {
            "service": "sagemaker",
            "resource_type": "aws_sagemaker_endpoint",
            "endpoint_name": endpoint_name,
            "variant_name": variant_name,
            "instance_type": _attr(config_block["text"], "instance_type") or "unknown",
            "instance_count": _attr_int(config_block["text"], "initial_instance_count") or 1,
            "configuration": {
                "real_time_endpoint": True,
                "autoscaling_target_present": "aws_appautoscaling_target" in control_text,
                "autoscaling_policy_present": "aws_appautoscaling_policy" in control_text,
                "scheduled_scaling_present": "aws_appautoscaling_scheduled_action" in control_text,
            },
            "metrics": {},
        }
    return records


def _sagemaker_savings(
    record: dict[str, Any],
    cost_summary: dict[str, Any],
    reduced_instances: int,
    hours: float,
) -> float:
    if reduced_instances <= 0 or hours <= 0:
        return 0.0
    hourly_price = _record_number(record, "instance_hourly_price")
    if hourly_price is not None:
        return reduced_instances * hourly_price * hours
    current_count = int(_record_number(record, "instance_count") or record.get("instance_count") or 0)
    monthly = _record_number(record, "monthly_spend_usd") or _domain_cost(cost_summary, "sagemaker")
    if monthly and current_count:
        return monthly * reduced_instances / current_count * min(hours / 730, 1.0)
    return 0.0


def _analyze_sagemaker(
    blocks: list[ResourceBlock],
    resources: dict[str, dict[str, Any]],
    cost_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    records = _sagemaker_tf_records(blocks)
    for name, record in resources.items():
        if _record_domain(record) != "sagemaker":
            continue
        key = str(record.get("endpoint_name") or name)
        records[key] = _merge_record(records.get(key, {}), record)

    findings: list[dict[str, Any]] = []
    for name, record in records.items():
        configuration = record.get("configuration", {}) if isinstance(record.get("configuration"), dict) else {}
        endpoint_name = str(record.get("endpoint_name") or name)
        variant_name = str(record.get("variant_name") or "AllTraffic")
        instance_type = str(record.get("instance_type") or "unknown")
        current_count = int(_record_number(record, "instance_count") or record.get("instance_count") or 0)
        min_safe = int(_record_number(record, "minimum_safe_capacity") or 1)
        reduced_instances = max(0, current_count - min_safe)
        source = _pricing_source(record, cost_summary)
        target_present = _record_bool(record, "autoscaling_target_present")
        policy_present = _record_bool(record, "autoscaling_policy_present")
        scheduled_present = _record_bool(record, "scheduled_scaling_present")
        hours_reduced = _record_number(record, "hours_reduced_per_month") or 360.0

        if current_count > 1 and (not target_present or not policy_present):
            savings = _sagemaker_savings(record, cost_summary, reduced_instances, hours_reduced)
            findings.append(
                {
                    "domain": "sagemaker",
                    "resource": endpoint_name,
                    "rule_id": "SAGEMAKER_SM1_MISSING_TARGET_TRACKING",
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": round(savings, 2),
                    "savings_group": f"sagemaker:{endpoint_name}",
                    "evidence": [
                        f"variant={variant_name}",
                        f"instance_type={instance_type}",
                        f"initial_instance_count={current_count}",
                        "autoscaling_target_present=false",
                        "autoscaling_policy_present=false",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add a SageMaker variant Application Auto Scaling target and target-tracking policy, keeping a validated minimum capacity.",
                }
            )

        if _record_bool(record, "predictable_low_traffic_windows") and not scheduled_present:
            off_hours = _record_number(record, "off_hours_per_month") or 360.0
            savings = _sagemaker_savings(record, cost_summary, reduced_instances, off_hours)
            findings.append(
                {
                    "domain": "sagemaker",
                    "resource": endpoint_name,
                    "rule_id": "SAGEMAKER_SM2_MISSING_SCHEDULED_SCALING",
                    "severity": "MEDIUM",
                    "confidence": "MEDIUM",
                    "estimated_monthly_saving_usd": round(savings, 2),
                    "savings_group": f"sagemaker:{endpoint_name}",
                    "evidence": [
                        f"variant={variant_name}",
                        f"off_hours_per_month={round(off_hours, 2)}",
                        "scheduled_scaling_present=false",
                        f"minimum_safe_capacity={min_safe}",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add scheduled scaling for approved low-traffic windows; retain minimum safe capacity when 24x7 latency is required.",
                }
            )

        gpu_avg = _metric_avg(record, "gpu_utilization_pct")
        gpu_memory_p95 = _metric_p95(record, "gpu_memory_utilization_pct")
        latency_p95 = _metric_p95(record, "model_latency_ms")
        errors = _metric_values(record, "errors")
        latency_sla = _record_number(record, "latency_sla_ms")
        latency_headroom = _record_bool(record, "p95_latency_has_headroom") or (
            latency_p95 is not None and latency_sla is not None and latency_p95 <= latency_sla * 0.75
        )
        accelerator = bool(re.match(r"^(?:ml\.)?(?:g|p|inf|trn)[0-9]", instance_type))
        if (
            accelerator
            and gpu_avg is not None
            and gpu_avg < 25
            and gpu_memory_p95 is not None
            and gpu_memory_p95 < 60
            and latency_headroom
            and errors
            and sum(errors) == 0
        ):
            explicit_rightsize_savings = _record_number(record, "rightsize_monthly_savings_usd")
            savings = (
                explicit_rightsize_savings
                if explicit_rightsize_savings is not None
                else _sagemaker_savings(record, cost_summary, reduced_instances, 730.0)
            )
            findings.append(
                {
                    "domain": "sagemaker",
                    "resource": endpoint_name,
                    "rule_id": "SAGEMAKER_SM3_GPU_UNDERUTILIZED",
                    "severity": "HIGH",
                    "confidence": "MEDIUM",
                    "estimated_monthly_saving_usd": round(savings, 2),
                    "savings_group": f"sagemaker:{endpoint_name}",
                    "evidence": [
                        f"instance_type={instance_type}",
                        f"gpu_utilization_avg_pct={round(gpu_avg, 2)}",
                        f"gpu_memory_utilization_p95_pct={round(gpu_memory_p95, 2)}",
                        f"model_latency_p95_ms={latency_p95}",
                        "errors=0",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Canary a smaller instance or lower count while monitoring p95/p99 latency, GPU memory, errors, throttles, and model load time.",
                }
            )

        invocations_p95 = _metric_p95(record, "invocations_per_instance")
        if (
            _record_bool(record, "real_time_endpoint", default=True)
            and invocations_p95 is not None
            and invocations_p95 < 5
            and not _record_bool(record, "strict_low_latency_sla")
        ):
            findings.append(
                {
                    "domain": "sagemaker",
                    "resource": endpoint_name,
                    "rule_id": "SAGEMAKER_SM4_BURSTY_ALWAYS_ON_ENDPOINT",
                    "severity": "LOW",
                    "confidence": "LOW",
                    "estimated_monthly_saving_usd": 0.0,
                    "savings_group": f"sagemaker:{endpoint_name}",
                    "evidence": [
                        f"invocations_per_instance_p95={round(invocations_p95, 2)}",
                        "real_time_endpoint=true",
                        "strict_low_latency_sla=false",
                    ],
                    "recommendation": "Benchmark async, serverless, batch, Bedrock, or scheduled endpoint options before changing the real-time architecture.",
                }
            )
    return findings


def _accelerator_instance_type(instance_type: str) -> bool:
    return bool(re.match(r"^(?:g|p|inf|trn)[0-9]", instance_type))


def _terraform_schedule_present(block: ResourceBlock, blocks: list[ResourceBlock]) -> bool:
    text = block["text"].lower()
    tag_markers = ("schedule", "scheduler:enabled", "office-hours", "startstop")
    if any(marker in text for marker in tag_markers):
        return True
    control_types = {
        "aws_scheduler_schedule",
        "aws_cloudwatch_event_rule",
        "aws_ssm_association",
        "aws_autoscaling_schedule",
    }
    return any(
        candidate["type"] in control_types and block["name"].lower() in candidate["text"].lower()
        for candidate in blocks
    )


def _ec2_tf_records(blocks: list[ResourceBlock]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for block in blocks:
        if block["type"] != "aws_instance":
            continue
        instance_type = _attr(block["text"], "instance_type") or ""
        if not _accelerator_instance_type(instance_type):
            continue
        records[block["name"]] = {
            "service": "ec2",
            "resource_type": "aws_instance",
            "instance_type": instance_type,
            "instance_count": 1,
            "configuration": {
                "schedule_control_present": _terraform_schedule_present(block, blocks),
                "off_hours_per_week": _attr_int(block["text"], "off_hours_per_week"),
                "workload_role": _attr(block["text"], "workload_role") or "unknown",
            },
            "metrics": {},
        }

    launch_templates = {block["name"]: block for block in blocks if block["type"] == "aws_launch_template"}
    for asg in [block for block in blocks if block["type"] == "aws_autoscaling_group"]:
        template = next((block for name, block in launch_templates.items() if name in asg["text"]), None)
        if not template:
            continue
        instance_type = _attr(template["text"], "instance_type") or ""
        if not _accelerator_instance_type(instance_type):
            continue
        records[asg["name"]] = {
            "service": "ec2",
            "resource_type": "aws_autoscaling_group",
            "instance_type": instance_type,
            "instance_count": _attr_int(asg["text"], "desired_capacity") or 0,
            "configuration": {
                "gpu_launch_template_or_asg": True,
                "desired_capacity_static": True,
                "schedule_control_present": _terraform_schedule_present(asg, blocks),
                "scheduled_action_or_scaling_present": _terraform_schedule_present(asg, blocks),
                "off_hours_per_week": _attr_int(asg["text"], "off_hours_per_week"),
            },
            "metrics": {},
        }
    return records


def _ec2_net_savings(record: dict[str, Any], cost_summary: dict[str, Any], off_hours_per_week: float) -> float:
    count = int(_record_number(record, "instance_count") or record.get("instance_count") or 0)
    hourly_price = _record_number(record, "instance_hourly_price")
    stopped_hours = off_hours_per_week * 4.345
    if hourly_price is not None:
        gross = count * hourly_price * stopped_hours
    else:
        monthly = _record_number(record, "monthly_spend_usd") or _domain_cost(cost_summary, "ec2")
        gross = monthly * min(off_hours_per_week / 168, 1.0)
    residual = sum(
        _record_number(record, key) or 0.0
        for key in ("ebs_monthly_usd", "eip_monthly_usd", "snapshot_monthly_usd", "scheduler_monthly_usd")
    )
    return max(0.0, gross - residual)


def _analyze_ec2(
    blocks: list[ResourceBlock],
    resources: dict[str, dict[str, Any]],
    cost_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    records = _ec2_tf_records(blocks)
    for name, record in resources.items():
        if _record_domain(record) != "ec2":
            continue
        instance_type = str(record.get("instance_type") or "")
        if not _accelerator_instance_type(instance_type):
            continue
        records[name] = _merge_record(records.get(name, {}), record)

    findings: list[dict[str, Any]] = []
    for name, record in records.items():
        configuration = record.get("configuration", {}) if isinstance(record.get("configuration"), dict) else {}
        instance_type = str(record.get("instance_type") or "unknown")
        count = int(_record_number(record, "instance_count") or record.get("instance_count") or 0)
        off_hours = _record_number(record, "off_hours_per_week")
        schedule_present = _record_bool(record, "schedule_control_present")
        workload_role = str(configuration.get("workload_role") or "unknown").lower()
        gpu_avg = _metric_avg(record, "gpu_utilization_pct")
        source = _pricing_source(record, cost_summary)
        net_savings = _ec2_net_savings(record, cost_summary, off_hours) if off_hours is not None else 0.0
        specific_idle_training = (
            workload_role in {"dev", "training", "notebook"}
            and gpu_avg is not None
            and gpu_avg < 20
            and not schedule_present
        )

        if specific_idle_training:
            findings.append(
                {
                    "domain": "ec2",
                    "resource": name,
                    "rule_id": "EC2G2_IDLE_DEV_TRAINING_ACCELERATOR",
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": round(net_savings, 2),
                    "savings_group": f"ec2:{name}",
                    "evidence": [
                        f"instance_type={instance_type}",
                        f"instance_count={count}",
                        f"workload_role={workload_role}",
                        f"gpu_utilization_avg_pct={round(gpu_avg, 2)}",
                        f"off_hours_per_week={off_hours}",
                        "schedule_control_present=false",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add SSM Quick Setup or EventBridge Scheduler automation after validating checkpoint, warm-up, and resume behavior.",
                }
            )
        elif off_hours is not None and off_hours >= 40 and not schedule_present:
            findings.append(
                {
                    "domain": "ec2",
                    "resource": name,
                    "rule_id": "EC2G1_UNSCHEDULED_ACCELERATOR",
                    "severity": "HIGH",
                    "confidence": "MEDIUM",
                    "estimated_monthly_saving_usd": round(net_savings, 2),
                    "savings_group": f"ec2:{name}",
                    "evidence": [
                        f"instance_type={instance_type}",
                        f"instance_count={count}",
                        f"off_hours_per_week={off_hours}",
                        "schedule_control_present=false",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add Instance Scheduler, SSM Quick Setup, EventBridge Scheduler, or an approved workload-specific schedule.",
                }
            )

        if (
            _record_bool(record, "gpu_launch_template_or_asg")
            and _record_bool(record, "desired_capacity_static")
            and not _record_bool(record, "scheduled_action_or_scaling_present")
        ):
            findings.append(
                {
                    "domain": "ec2",
                    "resource": name,
                    "rule_id": "EC2G3_FIXED_GPU_ASG_CAPACITY",
                    "severity": "MEDIUM",
                    "confidence": "MEDIUM",
                    "estimated_monthly_saving_usd": round(net_savings, 2),
                    "savings_group": f"ec2:{name}",
                    "evidence": [
                        f"instance_type={instance_type}",
                        f"desired_capacity={count}",
                        "scheduled_action_or_scaling_present=false",
                        f"pricing_source={source}",
                    ],
                    "recommendation": "Add compatible ASG scheduled actions or target tracking for min, max, and desired capacity.",
                }
            )

        residual_keys = ("ebs_monthly_usd", "eip_monthly_usd", "snapshot_monthly_usd", "scheduler_monthly_usd")
        residual_known = all(_record_number(record, key) is not None for key in residual_keys)
        schedule_recommended = specific_idle_training or (off_hours is not None and off_hours >= 40 and not schedule_present)
        if schedule_recommended and not residual_known:
            findings.append(
                {
                    "domain": "ec2",
                    "resource": name,
                    "rule_id": "EC2G4_RESIDUAL_COSTS_UNKNOWN",
                    "severity": "INFO",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": 0.0,
                    "savings_group": f"ec2:{name}",
                    "evidence": ["one or more residual EBS/EIP/snapshot/scheduler cost fields are missing"],
                    "recommendation": "Collect residual storage, Elastic IP, snapshot, scheduler, NAT, and transfer costs before presenting net savings.",
                }
            )
    return findings


def _finding(
    domain: str,
    resource: str,
    rule_id: str,
    severity: str,
    confidence: str,
    saving: float,
    evidence: list[str],
    recommendation: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "resource": resource,
        "rule_id": rule_id,
        "severity": severity,
        "confidence": confidence,
        "estimated_monthly_saving_usd": round(max(0.0, saving), 2),
        "savings_group": f"{domain}:{resource}",
        "evidence": evidence,
        "recommendation": recommendation,
        **extra,
    }


def _split_domain_cost(cost_summary: dict[str, Any], domain: str, count: int, fraction: float = 1.0) -> float:
    monthly = _domain_cost(cost_summary, domain)
    return monthly * fraction / max(count, 1) if monthly else 0.0


def _analyze_ebs(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    flagged = [block for block in blocks if block["type"] == "aws_ebs_snapshot" and "sourcevolumestatus" in block["text"].lower() and "deleted" in block["text"].lower()]
    saving = _split_domain_cost(cost_summary, "ebs", len(flagged))
    return [
        _finding("ebs", block["name"], "EBS_S1_ORPHANED_SNAPSHOT", "HIGH", "MEDIUM", saving,
                 ["SourceVolumeStatus=deleted", "no AMI/Backup/DLM dependency evidence in Terraform slice"],
                 "Verify AMI, AWS Backup, DLM, legal hold, audit, and DR dependencies before deleting the snapshot.")
        for block in flagged
    ]


def _analyze_elb(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    lbs = [block for block in blocks if block["type"] in {"aws_lb", "aws_elb", "aws_alb"}]
    findings: list[dict[str, Any]] = []
    for block in lbs:
        record = _metric_record(metrics, block) or {}
        requests = _series(record.get("metrics", {}).get("request_count", {})) or _series(record.get("metrics", {}).get("request_count_sum", {}))
        connections = _series(record.get("metrics", {}).get("active_connection_count", {}))
        is_problem = bool(record.get("is_problem"))
        if (requests and sum(requests) == 0 and (not connections or max(connections) == 0)) or is_problem:
            findings.append(_finding("elb", block["name"], "ELB_LB1_UNUSED", "HIGH", "HIGH" if requests else "MEDIUM",
                                     _split_domain_cost(cost_summary, "elb", len(lbs)),
                                     [f"request_count_sum={sum(requests) if requests else 'not_available'}", f"active_connection_count_max={max(connections) if connections else 'not_available'}"],
                                     "Check DNS, listener, target group, blue/green, and DR dependencies before deletion."))
    return findings


def _analyze_rds(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    dbs = [block for block in blocks if block["type"] == "aws_db_instance"]
    findings: list[dict[str, Any]] = []
    for block in dbs:
        env = (_tag_value(block["text"], "Environment") or "unknown").lower()
        multi_az = _attr_bool(block["text"], "multi_az")
        monthly = _split_domain_cost(cost_summary, "rds", len(dbs))
        if multi_az and env in {"dev", "test", "staging", "sandbox", "nonprod"}:
            findings.append(_finding("rds", block["name"], "RDS_R1_NONPROD_MULTI_AZ", "MEDIUM", "MEDIUM", monthly * 0.5,
                                     ["multi_az=true", f"environment={env}", "SLA/DR/compliance requirement not available"],
                                     "Review SLA, DR, and compliance requirements before changing non-production Multi-AZ.",
                                     optimized_replacement={"resource": block["name"], "text": _replace_attr(block["text"], "multi_az", "false")}))
        record = _metric_record(metrics, block) or {}
        cpu = _series(record.get("metrics", {}).get("cpu_utilization", {}))
        if cpu and (_avg(cpu) or 100) < 20 and (_pctl(cpu, 0.95) or 100) < 40:
            findings.append(_finding("rds", block["name"], "RDS_R2_LOW_UTILIZATION", "HIGH", "MEDIUM", monthly * 0.25,
                                     [f"cpu_avg_pct={_avg(cpu)}", f"cpu_p95_pct={_pctl(cpu, 0.95)}"],
                                     "Benchmark a smaller supported DB class after checking memory, IOPS, connections, and latency."))
    return findings


def _analyze_cloudwatch(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [block for block in blocks if block["type"] == "aws_cloudwatch_log_group"]
    flagged = [block for block in groups if (_attr_int(block["text"], "retention_in_days") or _attr_int(block["text"], "retention_days") or 0) == 0]
    findings = []
    for block in flagged:
        replacement = _replace_attr(block["text"], "retention_days" if _attr(block["text"], "retention_days") is not None else "retention_in_days", 30)
        findings.append(_finding("cloudwatch", block["name"], "CLOUDWATCH_C1_MISSING_RETENTION", "HIGH", "HIGH",
                                 _split_domain_cost(cost_summary, "cloudwatch", len(flagged), 0.5),
                                 ["retention is missing or unlimited"], "Set a retention period after validating audit and compliance requirements.",
                                 optimized_replacement={"resource": block["name"], "text": replacement}))
    return findings


def _analyze_cloudwatch_alarm(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    alarms = [block for block in blocks if block["type"] == "aws_cloudwatch_metric_alarm"]
    flagged = [block for block in alarms if (_attr_int(block["text"], "resolution_seconds") or 60) == 1 and (_attr_int(block["text"], "actual_required_resolution_seconds") or 60) >= 60]
    return [
        _finding("cloudwatch-alarm", block["name"], "CLOUDWATCH_M1_HIGH_RESOLUTION", "HIGH", "HIGH",
                 _split_domain_cost(cost_summary, "cloudwatch-alarm", len(flagged), 0.6),
                 ["resolution_seconds=1", "actual_required_resolution_seconds>=60"],
                 "Use standard-resolution metrics unless a documented sub-minute SLA requires high resolution.",
                 optimized_replacement={"resource": block["name"], "text": _replace_attr(block["text"], "resolution_seconds", 60)})
        for block in flagged
    ]


def _analyze_sqs(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    queues = [block for block in blocks if block["type"] == "aws_sqs_queue"]
    flagged = [block for block in queues if (_attr_int(block["text"], "receive_wait_time_seconds") or 0) == 0 and (_attr_int(block["text"], "empty_receives_per_day") or 0) >= 10000]
    return [
        _finding("sqs", block["name"], "SQS_Q1_ENABLE_LONG_POLLING", "HIGH", "HIGH",
                 _split_domain_cost(cost_summary, "sqs", len(flagged), 0.5),
                 ["receive_wait_time_seconds=0", f"empty_receives_per_day={_attr_int(block['text'], 'empty_receives_per_day')}"],
                 "Enable long polling and ensure the client read timeout exceeds the wait time.",
                 optimized_replacement={"resource": block["name"], "text": _replace_attr(block["text"], "receive_wait_time_seconds", 20)})
        for block in flagged
    ]


def _analyze_kinesis(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    streams = [block for block in blocks if block["type"] == "aws_kinesis_stream"]
    findings = []
    for block in streams:
        if _attr_bool(block["text"], "enhanced_fan_out") and (_attr_int(block["text"], "processing_interval_minutes") or 0) >= 5:
            findings.append(_finding("kinesis", block["name"], "KINESIS_K1_REVIEW_EFO", "MEDIUM", "MEDIUM",
                                     _split_domain_cost(cost_summary, "kinesis", len(streams), 0.4),
                                     ["enhanced_fan_out=true", f"processing_interval_minutes={_attr_int(block['text'], 'processing_interval_minutes')}"],
                                     "Validate latency SLA and consumer contention, then compare standard polling cost."))
    return findings


def _analyze_ecs(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    services = [block for block in blocks if block["type"] == "aws_ecs_service"]
    findings = []
    for block in services:
        if (_attr(block["text"], "launch_type") or "").upper() != "FARGATE":
            continue
        record = _metric_record(metrics, block) or {}
        cpu = _series(record.get("metrics", {}).get("cpu_utilization_pct", {})) or _series(record.get("metrics", {}).get("cpu_utilization", {}))
        if bool(record.get("is_problem")) or (cpu and (_avg(cpu) or 100) < 20 and (_pctl(cpu, .95) or 100) < 50):
            findings.append(_finding("ecs", block["name"], "ECS_E1_FARGATE_RIGHTSIZE", "HIGH", "MEDIUM",
                                     _split_domain_cost(cost_summary, "ecs", len(services), 0.4),
                                     [f"cpu_avg_pct={_avg(cpu) if cpu else 'not_available'}", f"desired_count={_attr_int(block['text'], 'desired_count')}"],
                                     "Select a valid smaller Fargate CPU/memory shape and canary while monitoring p95/p99 and errors."))
    return findings


def _analyze_elasticache(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [block for block in blocks if block["type"] == "aws_elasticache_replication_group"]
    findings = []
    for block in groups:
        count = _attr_int(block["text"], "num_cache_clusters") or 1
        record = _metric_record(metrics, block) or {}
        if count > 2 and bool(record.get("is_problem")):
            findings.append(_finding("elasticache", block["name"], "ELASTICACHE_EC1_REDUCE_REPLICAS", "HIGH", "MEDIUM",
                                     _split_domain_cost(cost_summary, "elasticache", len(groups), (count - 2) / count),
                                     [f"num_cache_clusters={count}", "metrics.is_problem=true"],
                                     "Reduce replicas only after checking memory p95, evictions, CPU, network, replication lag, and HA requirements."))
    return findings


def _analyze_nat(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    gateways = [block for block in blocks if block["type"] == "aws_nat_gateway"]
    endpoints = [block for block in blocks if block["type"] == "aws_vpc_endpoint"]
    has_s3 = any("s3" in block["text"].lower() for block in endpoints)
    if not gateways or has_s3:
        return []
    monthly = _domain_cost(cost_summary, "nat")
    return [_finding("nat", block["name"], "NAT_N1_S3_GATEWAY_ENDPOINT", "HIGH", "LOW", monthly * 0.5,
                     ["aws_nat_gateway present", "no S3 gateway endpoint evidence"],
                     "Confirm same-region S3 traffic and route tables, then add an S3 Gateway Endpoint.") for block in gateways]


def _analyze_tgw(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    gateways = [block for block in blocks if block["type"] == "aws_ec2_transit_gateway"]
    attachments = [block for block in blocks if block["type"] == "aws_ec2_transit_gateway_vpc_attachment"]
    peering = [block for block in blocks if block["type"] == "aws_vpc_peering_connection"]
    if not gateways or len(attachments) > 5 or not peering:
        return []
    return [_finding("tgw", gateways[0]["name"], "TGW_T2_PEERING_CANDIDATE", "MEDIUM", "MEDIUM",
                     _domain_cost(cost_summary, "tgw") * 0.5,
                     [f"attachment_count={len(attachments)}", "same-region VPC peering evidence present"],
                     "Validate transitive routing, inspection, and multi-account requirements before migrating traffic to VPC peering.")]


def _analyze_organizations(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = [block for block in blocks if block["type"] == "aws_account"]
    flagged = [block for block in accounts if _attr_bool(block["text"], "consolidated_billing") is False and (_attr_float(block["text"], "monthly_spend_usd") or 0) > 0]
    return [
        _finding("organizations", block["name"], "ORG_O1_CONSOLIDATED_BILLING", "HIGH", "MEDIUM", 0.0,
                 ["consolidated_billing=false", f"monthly_spend_usd={_attr_float(block['text'], 'monthly_spend_usd')}"],
                 "Model eligible spend and organizational ownership before enabling consolidated billing or discount sharing.")
        for block in flagged
    ]


def _load_existing_findings(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = _load_json(Path(path))
    raw_findings = data.get("findings", []) if isinstance(data, dict) else []
    findings: list[dict[str, Any]] = []
    for item in raw_findings:
        findings.append(
            {
                "domain": "existing",
                "resource": item.get("resource_id") or item.get("resource") or "unknown",
                "rule_id": item.get("rule_id", "EXISTING_FINDING"),
                "severity": item.get("severity", "UNKNOWN"),
                "confidence": item.get("confidence", "UNKNOWN"),
                "estimated_monthly_saving_usd": item.get("estimated_monthly_saving_usd", 0),
                "evidence": [item.get("verdict", "Loaded from existing findings.json")],
                "recommendation": item.get("remediation", "Review existing finding."),
            }
        )
    return findings


def _analyze_single_domain(domain: str, evidence: dict[str, Any]) -> dict[str, Any]:
    tf_path = evidence.get("terraform")
    blocks = _resource_blocks(_read_text(Path(tf_path))) if tf_path else []
    metrics = _load_metric_resources(evidence.get("metrics"))
    analysis_resources, analysis_metadata = _load_analysis_resources(evidence)
    cost_summary = _load_cost_summary(evidence.get("cost_report"))
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []

    if domain == "lambda":
        findings.extend(_analyze_lambda(blocks, metrics, cost_summary))
    elif domain == "s3":
        findings.extend(_analyze_s3(blocks, metrics, cost_summary))
    elif domain == "dynamodb":
        findings.extend(_analyze_dynamodb(blocks, metrics, cost_summary))
    elif domain == "bedrock":
        findings.extend(_analyze_bedrock(analysis_resources, analysis_metadata, cost_summary))
    elif domain == "sagemaker":
        findings.extend(_analyze_sagemaker(blocks, analysis_resources, cost_summary))
    elif domain == "ec2":
        findings.extend(_analyze_ec2(blocks, analysis_resources, cost_summary))
    elif domain == "ebs":
        findings.extend(_analyze_ebs(blocks, cost_summary))
    elif domain == "elb":
        findings.extend(_analyze_elb(blocks, metrics, cost_summary))
    elif domain == "rds":
        findings.extend(_analyze_rds(blocks, metrics, cost_summary))
    elif domain == "cloudwatch":
        findings.extend(_analyze_cloudwatch(blocks, cost_summary))
    elif domain == "cloudwatch-alarm":
        findings.extend(_analyze_cloudwatch_alarm(blocks, cost_summary))
    elif domain == "sqs":
        findings.extend(_analyze_sqs(blocks, cost_summary))
    elif domain == "kinesis":
        findings.extend(_analyze_kinesis(blocks, cost_summary))
    elif domain == "ecs":
        findings.extend(_analyze_ecs(blocks, metrics, cost_summary))
    elif domain == "elasticache":
        findings.extend(_analyze_elasticache(blocks, metrics, cost_summary))
    elif domain == "nat":
        findings.extend(_analyze_nat(blocks, cost_summary))
    elif domain == "tgw":
        findings.extend(_analyze_tgw(blocks, cost_summary))
    elif domain == "organizations":
        findings.extend(_analyze_organizations(blocks, cost_summary))
    else:
        warnings.append(
            f"No built-in graph analyzer yet for domain '{domain}'; load existing findings or service skill output."
        )

    return {
        "domain": domain,
        "findings": findings,
        "warnings": warnings,
    }


def _registry_handler(domain: str):
    def analyze(context: dict[str, Any]) -> list[dict[str, Any]]:
        return _analyze_single_domain(domain, context["evidence"])["findings"]

    return analyze


def _build_analyzer_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for domain in (
        "lambda", "s3", "dynamodb", "bedrock", "sagemaker", "ec2",
        "ebs", "elb", "rds", "cloudwatch", "cloudwatch-alarm", "sqs",
        "kinesis", "ecs", "elasticache", "nat", "tgw", "organizations",
    ):
        registry.register(
            AnalyzerRegistration(
                domain=domain,
                version="2.0.0",
                analyzer=_registry_handler(domain),
            )
        )
    return registry


ANALYZER_REGISTRY = _build_analyzer_registry()


def analyze_domain_node(state: CloudSweepState) -> dict[str, Any]:
    domain = state["analysis_domain"]
    try:
        registration = ANALYZER_REGISTRY.get(domain)
        findings = registration.analyzer({"evidence": state["evidence"]})
        result = {"domain": domain, "findings": findings, "warnings": [], "analyzer_version": registration.version}
    except RuleValidationError as exc:
        result = {"domain": domain, "findings": [], "warnings": [str(exc)], "analyzer_version": ""}
    return {"domain_results": [result]}


def _dispatch_domain_analysis(state: CloudSweepState) -> list[Send] | str:
    domains = state.get("domains", [])
    if not domains:
        return "collect_domain_results"
    return [
        Send(
            "analyze_domain",
            {
                "analysis_domain": domain,
                "evidence": state["evidence"],
            },
        )
        for domain in domains
    ]


def collect_domain_results_node(state: CloudSweepState) -> dict[str, Any]:
    domain_order = {domain: index for index, domain in enumerate(state.get("domains", []))}
    results = sorted(
        state.get("domain_results", []),
        key=lambda item: domain_order.get(str(item.get("domain", "")), len(domain_order)),
    )
    findings = [finding for result in results for finding in result.get("findings", [])]
    versions = {str(result.get("domain")): str(result.get("analyzer_version", "")) for result in results}
    tf_path = state.get("evidence", {}).get("terraform")
    tf_blocks = {block["name"]: block for block in _resource_blocks(_read_text(Path(tf_path)))} if tf_path else {}
    for finding in findings:
        domain = str(finding.get("domain", "unknown"))
        rule_id = str(finding.get("rule_id", "UNKNOWN"))
        resource = str(finding.get("resource", "unknown"))
        finding["finding_id"] = stable_id(state.get("run_id"), domain, rule_id, resource)
        finding["rule_version"] = "2.0.0"
        finding["analyzer_version"] = versions.get(domain, "")
        finding["evidence_facts"] = [
            {
                "fact_id": stable_id(state.get("run_id"), domain, resource, index, statement),
                "statement": statement,
            }
            for index, statement in enumerate(finding.get("evidence", []))
        ]
        replacement = finding.get("optimized_replacement")
        if replacement:
            original = tf_blocks.get(str(replacement.get("resource")))
            if original:
                finding["remediation_patch"] = {
                    "kind": "replace_resource",
                    "resource": replacement["resource"],
                    "source_hash": hashlib.sha256(original["text"].encode("utf-8")).hexdigest(),
                    "content": replacement["text"],
                }
        elif finding.get("optimized_append"):
            finding["remediation_patch"] = {
                "kind": "append_block",
                "source_hash": hashlib.sha256(_read_text(Path(tf_path)).encode("utf-8")).hexdigest() if tf_path else "",
                "content": finding["optimized_append"],
            }
    warnings = [warning for result in results for warning in result.get("warnings", [])]
    trace_items = [f"domain result: {result.get('domain')} ({len(result.get('findings', []))} finding(s))" for result in results]
    return {
        "cost_summary": _load_cost_summary(state["evidence"].get("cost_report")),
        "findings": findings,
        "analyzer_coverage": ANALYZER_REGISTRY.coverage(state.get("domains", [])),
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(
            state,
            "trace",
            [f"domain fan-out: {len(results)} branch(es)", *trace_items, f"domain findings: {len(findings)}"],
        ),
    }


def _pricing_enrichment_node(provider: EnrichmentProvider):
    fallback = FallbackEnrichmentProvider()

    def verify_pricing_node(state: CloudSweepState) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        failures: list[str] = []
        for finding in state.get("findings", []):
            enriched = dict(finding)
            try:
                enriched["pricing_verification"] = provider.verify_pricing(enriched)
            except Exception as exc:  # Provider failures must not stop deterministic analysis.
                enriched["pricing_verification"] = fallback.verify_pricing(enriched)
                failures.append(f"{finding.get('rule_id', 'unknown')}: {type(exc).__name__}: {exc}")
            findings.append(enriched)
        status = {
            **state.get("enrichment_status", {}),
            "pricing": {
                "provider": provider.name,
                "finding_count": len(findings),
                "failure_count": len(failures),
            },
        }
        warnings = [f"Pricing enrichment fallback used for {failure}" for failure in failures]
        return {
            "findings": findings,
            "enrichment_status": status,
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", [f"pricing enrichment: {provider.name}, failures={len(failures)}"]),
        }

    return verify_pricing_node


def _docs_enrichment_node(provider: EnrichmentProvider):
    fallback = FallbackEnrichmentProvider()

    def fetch_doc_refs_node(state: CloudSweepState) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        failures: list[str] = []
        for finding in state.get("findings", []):
            enriched = dict(finding)
            try:
                enriched["documentation"] = provider.fetch_doc_refs(enriched)
            except Exception as exc:  # Provider failures must not stop deterministic analysis.
                enriched["documentation"] = fallback.fetch_doc_refs(enriched)
                failures.append(f"{finding.get('rule_id', 'unknown')}: {type(exc).__name__}: {exc}")
            findings.append(enriched)
        status = {
            **state.get("enrichment_status", {}),
            "documentation": {
                "provider": provider.name,
                "finding_count": len(findings),
                "failure_count": len(failures),
            },
        }
        warnings = [f"Documentation enrichment fallback used for {failure}" for failure in failures]
        return {
            "findings": findings,
            "enrichment_status": status,
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", [f"documentation enrichment: {provider.name}, failures={len(failures)}"]),
        }

    return fetch_doc_refs_node


def approval_gate_node(state: CloudSweepState) -> dict[str, Any]:
    if not state.get("require_approval", False):
        return {
            "approval_status": "not_required",
            "trace": _append(state, "trace", ["approval gate: not required"]),
        }

    threshold = float(state.get("approval_threshold_usd", 500.0))
    candidates = [
        {
            "rule_id": finding.get("rule_id"),
            "resource": finding.get("resource"),
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "estimated_monthly_saving_usd": finding.get("estimated_monthly_saving_usd", 0.0),
        }
        for finding in state.get("findings", [])
        if float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0) >= threshold
        or finding.get("confidence") == "LOW"
    ]
    if not candidates:
        return {
            "approval_status": "not_required",
            "trace": _append(state, "trace", ["approval gate: no candidates"]),
        }

    decision = interrupt(
        {
            "kind": "cloudsweep_finops_approval",
            "scenario": Path(state["work_dir"]).name,
            "threshold_usd": threshold,
            "candidates": candidates,
            "question": "Approve these findings for final reporting and remediation planning?",
        }
    )
    if isinstance(decision, dict):
        approved = bool(decision.get("approved"))
        decision_payload = decision
    else:
        approved = bool(decision)
        decision_payload = {"approved": approved}
    status = "approved" if approved else "rejected"
    warnings = [] if approved else ["Human approval was rejected; findings remain advisory only."]
    return {
        "approval_status": status,
        "approval_decision": decision_payload,
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", [f"approval gate: {status}"]),
    }


def _load_cost_and_usage(files: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in files:
        data = _load_json(Path(file_name))
        rows.extend(data.get("ResultsByTime", []))
    return sorted(rows, key=lambda row: row.get("TimePeriod", {}).get("Start", ""))


def _cost_amount(row: dict[str, Any]) -> float:
    return float(row.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0.0))


def _group_amounts(row: dict[str, Any]) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for group in row.get("Groups", []):
        key = " / ".join(group.get("Keys", []))
        amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0.0))
        amounts[key] = amount
    return amounts


def _detect_spikes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spikes: list[dict[str, Any]] = []
    costs = [_cost_amount(row) for row in rows]
    for idx, row in enumerate(rows):
        prior = costs[max(0, idx - 6):idx]
        if not prior:
            continue
        baseline_mean = statistics.mean(prior)
        baseline_stddev = statistics.pstdev(prior) if len(prior) > 1 else 0.0
        current = costs[idx]
        prev = costs[idx - 1]
        flags = []
        if current > baseline_mean + 2 * baseline_stddev:
            flags.append("statistical")
        if prev and ((current - prev) / prev) > 1.0:
            flags.append("pct_change")
        if flags:
            spikes.append(
                {
                    "timestamp": row.get("TimePeriod", {}).get("Start"),
                    "cost": round(current, 2),
                    "baseline_mean": round(baseline_mean, 2),
                    "baseline_stddev": round(baseline_stddev, 2),
                    "flags": flags,
                }
            )
    return spikes


def _drilldown(rows: list[dict[str, Any]], spikes: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ts = {row.get("TimePeriod", {}).get("Start"): row for row in rows}
    anomaly_usage = {
        item.get("DimensionValue"): [
            cause.get("UsageType")
            for cause in item.get("RootCauses", [])
            if cause.get("UsageType")
        ]
        for item in anomalies
    }
    result: list[dict[str, Any]] = []
    for spike in spikes:
        row = by_ts.get(spike["timestamp"])
        if not row:
            continue
        current = _group_amounts(row)
        ranked = sorted(current.items(), key=lambda item: item[1], reverse=True)
        result.append(
            {
                "timestamp": spike["timestamp"],
                "services": [
                    {
                        "service": service,
                        "spike_cost": round(amount, 2),
                        "usage_types": anomaly_usage.get(service, []),
                    }
                    for service, amount in ranked[:5]
                ],
            }
        )
    return result


def anomaly_node(state: CloudSweepState) -> dict[str, Any]:
    evidence = state["evidence"]
    rows = _load_cost_and_usage(evidence.get("cost_explorer", []))
    anomalies = []
    if evidence.get("anomalies"):
        anomalies = _load_json(Path(evidence["anomalies"])).get("Anomalies", [])

    spikes = _detect_spikes(rows) if rows else []
    anomaly = {
        "datapoints": len(rows),
        "spikes": spikes,
        "drilldown": _drilldown(rows, spikes, anomalies),
        "anomalies": anomalies,
        "cloudtrail_available": bool(evidence.get("cloudtrail")),
        "confidence": {
            "spike_detection": "HIGH" if spikes else "NOT_APPLICABLE",
            "service_attribution": "HIGH" if anomalies else ("MEDIUM" if spikes else "NOT_APPLICABLE"),
            "triggering_event": "MEDIUM" if evidence.get("cloudtrail") else "LOW",
        },
        "fact_ids": [stable_id(state.get("run_id"), "anomaly", spike.get("timestamp"), spike.get("cost")) for spike in spikes],
    }
    return {
        "anomaly": anomaly,
        "trace": _append(state, "trace", [f"anomaly: {len(spikes)} spike(s), {len(anomalies)} anomaly record(s)"]),
    }


def _build_dependency_facts(state: CloudSweepState) -> list[dict[str, Any]]:
    tf_path = state.get("evidence", {}).get("terraform")
    if not tf_path:
        return []
    blocks = _resource_blocks(_read_text(Path(tf_path)))
    by_name = {block["name"]: block for block in blocks}
    facts: list[dict[str, Any]] = []
    for source in blocks:
        refs = re.findall(r"aws_[A-Za-z0-9_]+\.([A-Za-z0-9_-]+)\.", source["text"])
        for target_name in sorted(set(refs)):
            target = by_name.get(target_name)
            if not target or target_name == source["name"]:
                continue
            fact_id = stable_id(state.get("run_id"), "dependency", source["name"], target_name)
            facts.append({
                "fact_id": fact_id,
                "kind": "terraform_reference",
                "source": source["name"],
                "source_type": source["type"],
                "target": target_name,
                "target_type": target["type"],
                "status": "observed",
            })
    return sorted(facts, key=lambda fact: (fact["source"], fact["target"], fact["fact_id"]))


def cross_domain_node(state: CloudSweepState) -> dict[str, Any]:
    domains = set(state.get("domains", []))
    findings = state.get("findings", [])
    notes: list[str] = []
    if {"lambda", "dynamodb"} <= domains:
        notes.append("Lambda and DynamoDB are both present; validate Lambda retry/error metrics after DynamoDB capacity changes.")
    if {"lambda", "s3"} <= domains:
        notes.append("Lambda and S3 are both present; check request amplification before treating storage lifecycle as the only driver.")
    if "bedrock" in domains:
        notes.append("Bedrock token spend should be reviewed for prompt caching, semantic cache, and commitment break-even using token and cache-hit evidence.")
    if "bedrock" in domains and ({"sagemaker", "ec2"} & domains):
        notes.append("Managed Bedrock API cost and hosted accelerator cost are both present; run an LLM TCO comparison before choosing a platform-level remediation.")
    if {"sagemaker", "ec2"} & domains:
        notes.append("Accelerator capacity is present; validate autoscaling, scheduled scaling, and off-hour stop controls before accepting always-on instance-hours.")
    if state.get("anomaly", {}).get("spikes") and findings:
        notes.append("Cost Explorer anomaly evidence and Terraform findings should be reconciled before applying remediation.")
    if not notes:
        notes.append("No explicit cross-domain risk pattern detected from available evidence.")
    dependency_facts = _build_dependency_facts(state)
    return {
        "cross_domain_notes": notes,
        "dependency_facts": dependency_facts,
        "trace": _append(state, "trace", [f"cross-domain notes: {len(notes)}"]),
    }


def _render_optimized_tf(state: CloudSweepState) -> str:
    tf_path = state.get("evidence", {}).get("terraform")
    if not tf_path:
        return "# CloudSweep: no Terraform input was available for this scenario.\n"
    tf_text = _read_text(Path(tf_path))
    append_blocks: list[str] = []
    for finding in state.get("findings", []):
        replacement = finding.get("optimized_replacement")
        if replacement:
            old_block = next((block["text"] for block in _resource_blocks(tf_text) if block["name"] == replacement["resource"]), None)
            if old_block:
                tf_text = tf_text.replace(old_block, replacement["text"], 1)
        if finding.get("optimized_append"):
            append_blocks.append(finding["optimized_append"])
    if append_blocks:
        tf_text = tf_text.rstrip() + "\n\n# CloudSweep generated lifecycle guardrails\n" + "\n\n".join(append_blocks) + "\n"
    return tf_text


def _finding_table(findings: list[dict[str, Any]]) -> list[str]:
    if not findings:
        return ["No findings generated from the available evidence."]
    lines = [
        "| Domain | Resource | Rule | Severity | Confidence | Monthly Savings |",
        "|--------|----------|------|----------|------------|-----------------|",
    ]
    for finding in findings:
        lines.append(
            "| {domain} | {resource} | {rule_id} | {severity} | {confidence} | ${saving:.2f} |".format(
                domain=finding.get("domain", ""),
                resource=finding.get("resource", ""),
                rule_id=finding.get("rule_id", ""),
                severity=finding.get("severity", ""),
                confidence=finding.get("confidence", ""),
                saving=float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0),
            )
        )
    return lines


def _conservative_monthly_savings(findings: list[dict[str, Any]]) -> float:
    grouped: dict[str, float] = {}
    ungrouped = 0.0
    for finding in findings:
        savings = float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0)
        group = finding.get("savings_group")
        if group:
            grouped[str(group)] = max(grouped.get(str(group), 0.0), savings)
        else:
            ungrouped += savings
    return round(ungrouped + sum(grouped.values()), 2)


def _render_report(state: CloudSweepState) -> str:
    evidence = state.get("evidence", {})
    findings = state.get("findings", [])
    anomaly = state.get("anomaly", {})
    total_savings = _conservative_monthly_savings(findings)
    lines = [
        "# CloudSweep LangGraph Report",
        "",
        f"**Scenario**: {Path(state['work_dir']).name}",
        f"**Run date**: {date.today().isoformat()}",
        f"**Intent**: {state.get('intent', 'unknown')}",
        f"**Execution plan**: {' -> '.join(state.get('execution_plan', []))}",
        "",
        "## Evidence Inventory",
        "",
        "| Evidence | Status |",
        "|----------|--------|",
    ]
    for key in ("terraform", "genai_evidence", "metrics", "cost_report", "parsed_input", "existing_findings", "cost_explorer", "anomalies", "cloudtrail"):
        value = evidence.get(key)
        if isinstance(value, list):
            status = f"{len(value)} file(s)" if value else "missing"
        else:
            status = "present" if value else "missing"
        lines.append(f"| {key} | {status} |")

    if anomaly:
        lines.extend(["", "## Cost Anomaly Node", ""])
        lines.append(f"- Datapoints: {anomaly.get('datapoints', 0)}")
        lines.append(f"- Spikes: {len(anomaly.get('spikes', []))}")
        for spike in anomaly.get("spikes", []):
            lines.append(
                f"- {spike['timestamp']}: ${spike['cost']:.2f}/hr "
                f"(baseline ${spike['baseline_mean']:.2f}, flags={', '.join(spike['flags'])})"
            )
        if anomaly.get("drilldown"):
            lines.extend(["", "| Timestamp | Top Service | Spike Cost | Usage Types |", "|-----------|-------------|------------|-------------|"])
            for item in anomaly["drilldown"]:
                top = item["services"][0] if item.get("services") else {}
                lines.append(
                    f"| {item['timestamp']} | {top.get('service', '')} | "
                    f"${float(top.get('spike_cost', 0.0)):.2f} | {', '.join(top.get('usage_types', [])) or 'n/a'} |"
                )

    lines.extend(
        [
            "",
            "## Domain Nodes",
            "",
            f"Domains detected: {', '.join(state.get('domains', [])) or 'none'}",
            "",
            *_finding_table(findings),
            "",
            f"Conservative estimated monthly savings: **${total_savings:.2f}**",
            "",
            "## Enrichment",
            "",
        ]
    )
    enrichment_status = state.get("enrichment_status", {})
    for label in ("pricing", "documentation"):
        details = enrichment_status.get(label, {})
        lines.append(
            f"- {label}: provider={details.get('provider', 'not-run')}, "
            f"findings={details.get('finding_count', 0)}, failures={details.get('failure_count', 0)}"
        )
    doc_findings = [
        finding
        for finding in findings
        if finding.get("documentation", {}).get("urls")
    ]
    for finding in doc_findings:
        lines.append(f"- {finding.get('rule_id')}: {', '.join(finding['documentation']['urls'])}")
    lines.extend(
        [
            "",
            "## Approval",
            "",
            f"Status: **{state.get('approval_status', 'not-run')}**",
            "",
            "## Cross-Domain Review",
            "",
        ]
    )
    for note in state.get("cross_domain_notes", []):
        lines.append(f"- {note}")
    if state.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in state["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(["", "## Graph Trace", ""])
    for item in state.get("trace", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_node(state: CloudSweepState) -> dict[str, Any]:
    result_dir = Path(state["result_dir"])
    standard = bool(state.get("standard_output", False))
    report_name = "finops_report.md" if standard else "cloudsweep_graph_report.md"
    tf_name = "main_optimized.tf" if standard else "cloudsweep_main_optimized.tf"
    output_paths = {
        "report": str(result_dir / report_name),
        "optimized_tf": str(result_dir / tf_name),
        "state": str(result_dir / "cloudsweep_graph_state.json"),
    }
    optimized_tf = _render_optimized_tf(state)
    report = _render_report({**state, "optimized_tf": optimized_tf, "output_paths": output_paths})

    if state.get("write", True):
        result_dir.mkdir(parents=True, exist_ok=True)
        Path(output_paths["report"]).write_text(report, encoding="utf-8")
        Path(output_paths["optimized_tf"]).write_text(optimized_tf, encoding="utf-8")
        state_payload = {
            "schema_version": state.get("schema_version"),
            "run_id": state.get("run_id"),
            "work_dir": state.get("work_dir"),
            "intent": state.get("intent"),
            "execution_plan": state.get("execution_plan"),
            "domains": state.get("domains"),
            "domain_resources": state.get("domain_resources"),
            "analyzer_coverage": state.get("analyzer_coverage"),
            "findings": state.get("findings"),
            "dependency_facts": state.get("dependency_facts"),
            "enrichment_status": state.get("enrichment_status"),
            "approval_status": state.get("approval_status"),
            "approval_decision": state.get("approval_decision"),
            "anomaly": state.get("anomaly"),
            "cross_domain_notes": state.get("cross_domain_notes"),
            "warnings": state.get("warnings"),
            "trace": state.get("trace"),
            "output_paths": output_paths,
        }
        Path(output_paths["state"]).write_text(json.dumps(state_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "optimized_tf": optimized_tf,
        "report_markdown": report,
        "output_paths": output_paths,
        "trace": _append(state, "trace", ["render: outputs prepared"]),
    }


def build_graph(
    *,
    enrichment_provider: EnrichmentProvider | None = None,
    checkpointer: Any = None,
):
    provider = enrichment_provider or FallbackEnrichmentProvider()
    builder = StateGraph(CloudSweepState)
    builder.add_node("inventory", inventory_node)
    builder.add_node("plan", plan_node)
    builder.add_node("anomaly_analysis", anomaly_node)
    builder.add_node("detect_domains", detect_domains_node)
    builder.add_node("analyze_domain", analyze_domain_node)
    builder.add_node("collect_domain_results", collect_domain_results_node)
    builder.add_node("verify_pricing", _pricing_enrichment_node(provider))
    builder.add_node("fetch_doc_refs", _docs_enrichment_node(provider))
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("cross_domain_review", cross_domain_node)
    builder.add_node("render_outputs", render_node)

    builder.add_edge(START, "inventory")
    builder.add_edge("inventory", "plan")
    builder.add_conditional_edges(
        "plan",
        _route_from_plan,
        {
            "anomaly_analysis": "anomaly_analysis",
            "detect_domains": "detect_domains",
            "render_outputs": "render_outputs",
        },
    )
    builder.add_conditional_edges(
        "anomaly_analysis",
        _route_after_anomaly,
        {
            "detect_domains": "detect_domains",
            "render_outputs": "render_outputs",
        },
    )
    builder.add_conditional_edges(
        "detect_domains",
        _dispatch_domain_analysis,
        ["analyze_domain", "collect_domain_results"],
    )
    builder.add_edge("analyze_domain", "collect_domain_results")
    builder.add_edge("collect_domain_results", "verify_pricing")
    builder.add_edge("verify_pricing", "fetch_doc_refs")
    builder.add_edge("fetch_doc_refs", "approval_gate")
    builder.add_edge("approval_gate", "cross_domain_review")
    builder.add_edge("cross_domain_review", "render_outputs")
    builder.add_edge("render_outputs", END)
    return builder.compile(checkpointer=checkpointer)


def _initial_state(
    work_dir: str | Path,
    *,
    write: bool,
    standard_output: bool,
    require_approval: bool,
    approval_threshold_usd: float,
) -> CloudSweepState:
    work_dir = Path(work_dir).resolve()
    run_id = stable_id(str(work_dir), date.today().isoformat())
    return {
        "schema_version": "2.0",
        "run_id": run_id,
        "work_dir": str(work_dir),
        "result_dir": str(work_dir / "result"),
        "write": write,
        "standard_output": standard_output,
        "warnings": [],
        "trace": [],
        "findings": [],
        "domain_results": [],
        "enrichment_status": {},
        "require_approval": require_approval,
        "approval_threshold_usd": approval_threshold_usd,
        "approval_status": "pending" if require_approval else "not_required",
    }


def run_graph(
    work_dir: str | Path,
    *,
    write: bool = True,
    standard_output: bool = False,
    enrichment_provider: EnrichmentProvider | None = None,
) -> CloudSweepState:
    app = build_graph(enrichment_provider=enrichment_provider)
    return app.invoke(
        _initial_state(
            work_dir,
            write=write,
            standard_output=standard_output,
            require_approval=False,
            approval_threshold_usd=500.0,
        )
    )


class CloudSweepRuntime:
    """Checkpointed runtime for interrupt and resume workflows."""

    def __init__(
        self,
        *,
        enrichment_provider: EnrichmentProvider | None = None,
        checkpointer: Any = None,
    ) -> None:
        self.checkpointer = checkpointer or InMemorySaver()
        self.app = build_graph(
            enrichment_provider=enrichment_provider,
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def run(
        self,
        work_dir: str | Path,
        *,
        thread_id: str,
        write: bool = True,
        standard_output: bool = False,
        require_approval: bool = True,
        approval_threshold_usd: float = 500.0,
    ) -> CloudSweepState:
        config = self._config(thread_id)
        if self.app.get_state(config).values:
            raise ValueError(f"Checkpoint thread '{thread_id}' already exists; resume it or use a new thread_id.")
        return self.app.invoke(
            _initial_state(
                work_dir,
                write=write,
                standard_output=standard_output,
                require_approval=require_approval,
                approval_threshold_usd=approval_threshold_usd,
            ),
            config=config,
        )

    def resume(self, thread_id: str, decision: dict[str, Any] | bool) -> CloudSweepState:
        return self.app.invoke(
            Command(resume=decision),
            config=self._config(thread_id),
        )

    def get_state(self, thread_id: str):
        return self.app.get_state(self._config(thread_id))


def main(argv: list[str] | None = None) -> None:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "finalize":
        from .finalizer import finalize

        final_parser = argparse.ArgumentParser(description="Finalize reviewed CloudSweep findings.")
        final_parser.add_argument("command")
        final_parser.add_argument("work_dir")
        final_parser.add_argument("--review", required=True)
        final_args = final_parser.parse_args(args_list)
        outputs = finalize(final_args.work_dir, final_args.review)
        print(f"Final report: {outputs['report']}")
        print(f"Final optimized Terraform: {outputs['optimized_tf']}")
        return
    parser = argparse.ArgumentParser(description="Run the CloudSweep LangGraph FinOps workflow.")
    parser.add_argument("work_dir", nargs="?", default=".", help="Scenario/workload directory to analyze.")
    parser.add_argument("--dry-run", action="store_true", help="Run the graph without writing result files.")
    parser.add_argument(
        "--standard-output",
        action="store_true",
        help="Write result/finops_report.md and result/main_optimized.tf instead of graph-specific filenames.",
    )
    args = parser.parse_args(args_list)

    state = run_graph(args.work_dir, write=not args.dry_run, standard_output=args.standard_output)
    print(f"Intent: {state.get('intent')}")
    print(f"Plan: {' -> '.join(state.get('execution_plan', []))}")
    print(f"Domains: {', '.join(state.get('domains', [])) or 'none'}")
    print(f"Findings: {len(state.get('findings', []))}")
    if args.dry_run:
        print("Dry run: no files written.")
    else:
        print(f"Report: {state['output_paths']['report']}")
        print(f"Optimized Terraform: {state['output_paths']['optimized_tf']}")


if __name__ == "__main__":
    main()
