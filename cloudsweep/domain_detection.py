"""Domain detection and evidence validation for CloudSweep inputs."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict


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


class ResourceBlock(TypedDict):
    type: str
    name: str
    text: str
    start: int
    end: int


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


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


def _resource_key(record: dict[str, Any], fallback: str = "") -> str:
    """Return a human-readable key for a resource record.

    Prefers ``name`` over ``resource_id``; skips ARN values entirely since
    they are not useful as short-form identifiers.  Returns ``fallback`` when
    neither field yields a usable key.
    """
    resource_id = str(record.get("resource_id") or "")
    name = str(record.get("name") or "")
    return name or (resource_id if not resource_id.startswith("arn:") else "") or fallback


def _add_domain_resource(
    domains: list[str],
    resources: dict[str, list[str]],
    domain: str,
    resource_name: str,
) -> None:
    if resource_name.startswith("arn:"):
        return
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
        for name, record in resources.items():
            if isinstance(record, dict) and not str(name).startswith("arn:"):
                records.append((str(name), record))
    elif isinstance(resources, list):
        for record in resources:
            if isinstance(record, dict):
                key = _resource_key(record)
                if key:
                    records.append((key, record))

    tf_resources = data.get("tf_resources")
    if isinstance(tf_resources, list):
        for record in tf_resources:
            if isinstance(record, dict):
                key = _resource_key(record)
                if key:
                    records.append((key, record))

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
    data = _read_json(path)
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
            not isinstance(metadata["period_days"], int)
            or isinstance(metadata["period_days"], bool)
            or metadata["period_days"] < 1
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

