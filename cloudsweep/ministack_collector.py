"""Read-only MiniStack evidence collector for CloudSweep."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .evidence_normalization import environment_fields, normalize_metric_name


DEFAULT_ENDPOINT_URL = "http://localhost:4566"
DEFAULT_REGION = "us-east-1"
COLLECTION_PERIOD_DAYS = 30

# Keep the collector's infrastructure boundary explicit and reviewable. No
# create, update, put, delete, or mutation APIs belong in this module.
READ_ONLY_OPERATIONS = frozenset(
    {
        "s3.list_buckets",
        "s3.get_bucket_tagging",
        "s3.get_bucket_lifecycle_configuration",
        "lambda.list_functions",
        "lambda.list_tags",
        "rds.describe_db_instances",
        "rds.list_tags_for_resource",
        "logs.describe_log_groups",
        "cloudwatch.describe_alarms",
        "cloudwatch.list_metrics",
        "cloudwatch.get_metric_statistics",
    }
)


def _json_string(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _hcl_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _terraform_name(service: str, resource_id: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", resource_id).strip("_") or "resource"
    if base[0].isdigit():
        base = f"resource_{base}"
    suffix = hashlib.sha256(f"{service}:{resource_id}".encode("utf-8")).hexdigest()[:8]
    return f"{base}_{suffix}"


def _tags_from_list(tags: Any) -> dict[str, str]:
    if not isinstance(tags, list):
        return {}
    return {
        str(tag["Key"]): str(tag.get("Value", ""))
        for tag in tags
        if isinstance(tag, dict) and tag.get("Key") is not None
    }


def _render_tags(tags: dict[str, str], indent: str = "  ") -> list[str]:
    if not tags:
        return []
    lines = [f"{indent}tags = {{"]
    for key, value in sorted(tags.items()):
        rendered_key = key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key) else _json_string(key)
        lines.append(f"{indent}  {rendered_key} = {_json_string(value)}")
    lines.append(f"{indent}}}")
    return lines


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def _read_call(
    errors: list[dict[str, str]],
    service: str,
    operation: str,
    call: Callable[..., dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any] | None:
    operation_id = f"{service}.{operation}"
    if operation_id not in READ_ONLY_OPERATIONS:
        raise ValueError(f"MiniStack collector blocked non-read operation: {operation_id}")
    try:
        return call(**kwargs)
    except Exception as error:  # Service failures must not stop other evidence collection.
        errors.append({"service": service, "operation": operation, "error": _error_text(error)})
        return None


def _optional_read_call(
    errors: list[dict[str, str]],
    service: str,
    operation: str,
    call: Callable[..., dict[str, Any]],
    absent_error_codes: set[str],
    **kwargs: Any,
) -> dict[str, Any] | None:
    operation_id = f"{service}.{operation}"
    if operation_id not in READ_ONLY_OPERATIONS:
        raise ValueError(f"MiniStack collector blocked non-read operation: {operation_id}")
    try:
        return call(**kwargs)
    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code in absent_error_codes:
            return {}
        errors.append({"service": service, "operation": operation, "error": _error_text(error)})
        return None
    except Exception as error:
        errors.append({"service": service, "operation": operation, "error": _error_text(error)})
        return None


def _client(
    session: boto3.session.Session,
    service: str,
    endpoint_url: str,
    errors: list[dict[str, str]],
) -> Any | None:
    try:
        config = Config(
            connect_timeout=2,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
            s3={"addressing_style": "path"},
        )
        return session.client(service, endpoint_url=endpoint_url, config=config)
    except Exception as error:
        errors.append({"service": service, "operation": "client", "error": _error_text(error)})
        return None


def _paginated_read(
    errors: list[dict[str, str]],
    service: str,
    operation: str,
    call: Callable[..., dict[str, Any]],
    result_key: str,
    *,
    request_token: str = "NextToken",
    response_token: str = "NextToken",
) -> list[Any]:
    items: list[Any] = []
    token: str | None = None
    while True:
        kwargs = {request_token: token} if token else {}
        response = _read_call(errors, service, operation, call, **kwargs)
        if response is None:
            break
        page_items = response.get(result_key, [])
        if isinstance(page_items, list):
            items.extend(page_items)
        next_token = response.get(response_token)
        if not isinstance(next_token, str) or not next_token or next_token == token:
            break
        token = next_token
    return items


def _collect_s3(
    client: Any,
    resources: dict[str, dict[str, Any]],
    blocks: list[str],
    errors: list[dict[str, str]],
) -> None:
    response = _read_call(errors, "s3", "list_buckets", client.list_buckets)
    for bucket in (response or {}).get("Buckets", []) or []:
        if not isinstance(bucket, dict) or not bucket.get("Name"):
            continue
        name = str(bucket["Name"])
        local_name = _terraform_name("s3", name)
        tag_response = _optional_read_call(
            errors,
            "s3",
            "get_bucket_tagging",
            client.get_bucket_tagging,
            {"NoSuchTagSet", "NoSuchTagSetError"},
            Bucket=name,
        )
        tags = _tags_from_list((tag_response or {}).get("TagSet"))
        lifecycle_response = _optional_read_call(
            errors,
            "s3",
            "get_bucket_lifecycle_configuration",
            client.get_bucket_lifecycle_configuration,
            {"NoSuchLifecycle", "NoSuchLifecycleConfiguration"},
            Bucket=name,
        )
        lifecycle_rules = (lifecycle_response or {}).get("Rules", [])
        has_lifecycle = isinstance(lifecycle_rules, list) and bool(lifecycle_rules)
        resources[local_name] = {
            "resource_id": name,
            "service": "s3",
            "resource_type": "aws_s3_bucket",
            "configuration": {
                "bucket": name,
                "has_lifecycle": has_lifecycle,
                "lifecycle_rules": lifecycle_rules,
                **environment_fields(tags),
            },
            "tags": tags,
        }

        lines = [f'resource "aws_s3_bucket" "{local_name}" {{', f"  bucket = {_json_string(name)}"]
        lines.extend(_render_tags(tags))
        lines.append("}")
        blocks.append("\n".join(lines))
        if has_lifecycle:
            lifecycle_name = f"{local_name}_lifecycle"
            first_rule = lifecycle_rules[0] if isinstance(lifecycle_rules[0], dict) else {}
            blocks.append(
                "\n".join(
                    [
                        f'resource "aws_s3_bucket_lifecycle_configuration" "{lifecycle_name}" {{',
                        f"  bucket = aws_s3_bucket.{local_name}.id",
                        "",
                        "  rule {",
                        f"    id     = {_json_string(first_rule.get('ID', 'ministack-existing-lifecycle'))}",
                        f"    status = {_json_string(first_rule.get('Status', 'Enabled'))}",
                        "    filter {}",
                        "    # Additional rule details remain in parsed_input.json.",
                        "  }",
                        "}",
                    ]
                )
            )


def _collect_lambda(
    client: Any,
    resources: dict[str, dict[str, Any]],
    blocks: list[str],
    errors: list[dict[str, str]],
) -> None:
    functions = _paginated_read(
        errors, "lambda", "list_functions", client.list_functions, "Functions", request_token="Marker", response_token="NextMarker"
    )
    for function in functions:
        if not isinstance(function, dict) or not function.get("FunctionName"):
            continue
        name = str(function["FunctionName"])
        local_name = _terraform_name("lambda", name)
        arn = str(function.get("FunctionArn") or "")
        tag_response = (
            _read_call(errors, "lambda", "list_tags", client.list_tags, Resource=arn) if arn else None
        )
        raw_tags = (tag_response or {}).get("Tags", {})
        tags = {str(key): str(value) for key, value in raw_tags.items()} if isinstance(raw_tags, dict) else {}
        configuration = {
            "function_name": name,
            "runtime": function.get("Runtime"),
            "handler": function.get("Handler"),
            "memory_size": function.get("MemorySize", 128),
            "timeout": function.get("Timeout", 3),
            **environment_fields(tags),
        }
        resources[local_name] = {
            "resource_id": arn or name,
            "service": "lambda",
            "resource_type": "aws_lambda_function",
            "configuration": configuration,
            "tags": tags,
        }

        lines = [
            f'resource "aws_lambda_function" "{local_name}" {{',
            f"  function_name = {_json_string(name)}",
        ]
        if function.get("Role"):
            lines.append(f"  role          = {_json_string(function['Role'])}")
        if function.get("Handler"):
            lines.append(f"  handler       = {_json_string(function['Handler'])}")
        if function.get("Runtime"):
            lines.append(f"  runtime       = {_json_string(function['Runtime'])}")
        lines.extend(
            [
                f"  memory_size = {_int_value(function.get('MemorySize'), 128)}",
                f"  timeout     = {_int_value(function.get('Timeout'), 3)}",
            ]
        )
        lines.extend(_render_tags(tags))
        lines.append("}")
        blocks.append("\n".join(lines))


def _collect_rds(
    client: Any,
    resources: dict[str, dict[str, Any]],
    blocks: list[str],
    errors: list[dict[str, str]],
) -> None:
    instances = _paginated_read(
        errors,
        "rds",
        "describe_db_instances",
        client.describe_db_instances,
        "DBInstances",
        request_token="Marker",
        response_token="Marker",
    )
    for instance in instances:
        if not isinstance(instance, dict) or not instance.get("DBInstanceIdentifier"):
            continue
        identifier = str(instance["DBInstanceIdentifier"])
        local_name = _terraform_name("rds", identifier)
        arn = str(instance.get("DBInstanceArn") or "")
        tag_response = (
            _read_call(
                errors, "rds", "list_tags_for_resource", client.list_tags_for_resource, ResourceName=arn
            )
            if arn
            else None
        )
        tags = _tags_from_list((tag_response or {}).get("TagList"))
        configuration = {
            "identifier": identifier,
            "engine": instance.get("Engine"),
            "engine_version": instance.get("EngineVersion"),
            "instance_class": instance.get("DBInstanceClass"),
            "allocated_storage_gb": instance.get("AllocatedStorage"),
            "storage_type": instance.get("StorageType"),
            "multi_az": bool(instance.get("MultiAZ", False)),
            "backup_retention_days": instance.get("BackupRetentionPeriod", 0),
            **environment_fields(tags),
        }
        resources[local_name] = {
            "resource_id": identifier,
            "service": "rds",
            "resource_type": "aws_db_instance",
            "configuration": configuration,
            "tags": tags,
        }

        lines = [
            f'resource "aws_db_instance" "{local_name}" {{',
            f"  identifier              = {_json_string(identifier)}",
        ]
        optional_strings = (
            ("engine", "Engine"),
            ("engine_version", "EngineVersion"),
            ("instance_class", "DBInstanceClass"),
            ("storage_type", "StorageType"),
            ("replicate_source_db", "ReadReplicaSourceDBInstanceIdentifier"),
        )
        for hcl_name, response_name in optional_strings:
            if instance.get(response_name):
                lines.append(f"  {hcl_name:<23} = {_json_string(instance[response_name])}")
        if instance.get("AllocatedStorage") is not None:
            lines.append(f"  allocated_storage       = {_int_value(instance['AllocatedStorage'])}")
        lines.extend(
            [
                f"  multi_az                = {_hcl_bool(instance.get('MultiAZ', False))}",
                f"  backup_retention_period = {_int_value(instance.get('BackupRetentionPeriod'))}",
            ]
        )
        lines.extend(_render_tags(tags))
        lines.append("}")
        blocks.append("\n".join(lines))


def _collect_logs(
    client: Any,
    resources: dict[str, dict[str, Any]],
    blocks: list[str],
    errors: list[dict[str, str]],
) -> None:
    groups = _paginated_read(
        errors,
        "logs",
        "describe_log_groups",
        client.describe_log_groups,
        "logGroups",
        request_token="nextToken",
        response_token="nextToken",
    )
    for group in groups:
        if not isinstance(group, dict) or not group.get("logGroupName"):
            continue
        name = str(group["logGroupName"])
        local_name = _terraform_name("logs", name)
        retention = group.get("retentionInDays")
        resources[local_name] = {
            "resource_id": str(group.get("arn") or name),
            "service": "cloudwatch",
            "resource_type": "aws_cloudwatch_log_group",
            "configuration": {
                "name": name,
                "retention_in_days": retention if retention is not None else 0,
                "stored_bytes": group.get("storedBytes", 0),
            },
        }
        lines = [
            f'resource "aws_cloudwatch_log_group" "{local_name}" {{',
            f"  name = {_json_string(name)}",
        ]
        if retention is not None:
            lines.append(f"  retention_in_days = {_int_value(retention)}")
        lines.append("}")
        blocks.append("\n".join(lines))


def _collect_alarms(
    client: Any,
    resources: dict[str, dict[str, Any]],
    blocks: list[str],
    errors: list[dict[str, str]],
) -> None:
    alarms = _paginated_read(
        errors, "cloudwatch", "describe_alarms", client.describe_alarms, "MetricAlarms"
    )
    for alarm in alarms:
        if not isinstance(alarm, dict) or not alarm.get("AlarmName"):
            continue
        name = str(alarm["AlarmName"])
        local_name = _terraform_name("cloudwatch-alarm", name)
        resources[local_name] = {
            "resource_id": str(alarm.get("AlarmArn") or name),
            "service": "cloudwatch-alarm",
            "resource_type": "aws_cloudwatch_metric_alarm",
            "configuration": {
                "alarm_name": name,
                "namespace": alarm.get("Namespace"),
                "metric_name": alarm.get("MetricName"),
                "period": alarm.get("Period"),
                "evaluation_periods": alarm.get("EvaluationPeriods"),
                "threshold": alarm.get("Threshold"),
            },
        }
        lines = [
            f'resource "aws_cloudwatch_metric_alarm" "{local_name}" {{',
            f"  alarm_name          = {_json_string(name)}",
            f"  comparison_operator = {_json_string(alarm.get('ComparisonOperator', 'GreaterThanThreshold'))}",
            f"  evaluation_periods  = {_int_value(alarm.get('EvaluationPeriods'), 1)}",
            f"  metric_name         = {_json_string(alarm.get('MetricName', 'Unknown'))}",
            f"  namespace           = {_json_string(alarm.get('Namespace', 'AWS/Custom'))}",
            f"  period              = {_int_value(alarm.get('Period'), 60)}",
            f"  statistic           = {_json_string(alarm.get('Statistic', 'Average'))}",
            f"  threshold           = {_float_value(alarm.get('Threshold'))}",
            "}",
        ]
        blocks.append("\n".join(lines))


def _snake_case(name: str) -> str:
    return normalize_metric_name(name)


def _metric_resource(
    metric: dict[str, Any],
    resource_lookup: dict[tuple[str, str], str],
) -> str | None:
    namespace = str(metric.get("Namespace") or "")
    namespace_service = {
        "AWS/Lambda": "lambda",
        "AWS/RDS": "rds",
        "AWS/S3": "s3",
        "AWS/Logs": "logs",
        "CWAgent": "lambda",
        "LambdaInsights": "lambda",
    }.get(namespace)
    dimension_names = {
        "FunctionName": "lambda",
        "DBInstanceIdentifier": "rds",
        "BucketName": "s3",
        "LogGroupName": "logs",
    }
    for dimension in metric.get("Dimensions", []):
        if not isinstance(dimension, dict):
            continue
        dimension_service = dimension_names.get(str(dimension.get("Name") or ""))
        service = dimension_service or namespace_service
        value = str(dimension.get("Value") or "")
        if service and value and (service, value) in resource_lookup:
            return resource_lookup[(service, value)]
    return None


def _metric_statistic(metric_name: str) -> str:
    lowered = metric_name.lower()
    if "memory" in lowered and ("max" in lowered or "used" in lowered):
        return "Maximum"
    if any(word in lowered for word in ("invocation", "error", "throttle", "request", "count")):
        return "Sum"
    return "Average"


def _collect_metrics(
    client: Any,
    resources: dict[str, dict[str, Any]],
    resource_lookup: dict[tuple[str, str], str],
    errors: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    output = {
        name: {
            "resource_id": record["resource_id"],
            "service": record["service"],
            "resource_type": record["resource_type"],
            "is_problem": None,
            "metrics": {},
        }
        for name, record in resources.items()
    }
    metrics = _paginated_read(
        errors, "cloudwatch", "list_metrics", client.list_metrics, "Metrics"
    )
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=COLLECTION_PERIOD_DAYS)
    for metric in metrics:
        if not isinstance(metric, dict) or not metric.get("Namespace") or not metric.get("MetricName"):
            continue
        resource_name = _metric_resource(metric, resource_lookup)
        if not resource_name or resource_name not in output:
            continue
        metric_name = str(metric["MetricName"])
        statistic = _metric_statistic(metric_name)
        response = _read_call(
            errors,
            "cloudwatch",
            "get_metric_statistics",
            client.get_metric_statistics,
            Namespace=metric["Namespace"],
            MetricName=metric_name,
            Dimensions=metric.get("Dimensions", []),
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=[statistic],
        )
        if response is None:
            continue
        datapoints = response.get("Datapoints", [])
        if not isinstance(datapoints, list):
            continue
        ordered = sorted(
            (point for point in datapoints if isinstance(point, dict)),
            key=lambda point: str(point.get("Timestamp", "")),
        )
        values = [
            float(point[statistic])
            for point in ordered
            if isinstance(point.get(statistic), (int, float)) and not isinstance(point.get(statistic), bool)
        ]
        unit = str(next((point.get("Unit") for point in ordered if point.get("Unit")), "None"))
        output[resource_name]["metrics"][_snake_case(metric_name)] = {
            "unit": unit,
            "statistic": statistic,
            "datapoints": values,
            "source_namespace": str(metric["Namespace"]),
            "source_metric_name": metric_name,
        }
    return output


def _terraform_document(region: str, blocks: list[str]) -> str:
    header = f'''terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = "{region}"
}}

# Generated as read-only evidence from MiniStack. Do not apply this file blindly.
'''
    return header + ("\n\n".join(blocks) if blocks else "# No supported resources were returned.\n") + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def collect_ministack(output_dir: str | Path) -> Path:
    """Collect MiniStack state into CloudSweep evidence files.

    Only operations listed in :data:`READ_ONLY_OPERATIONS` are allowed. A
    service or resource API failure is recorded in both JSON evidence files and
    does not prevent the remaining services from being collected.
    """
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    endpoint_url = os.environ.get("MINISTACK_ENDPOINT_URL", DEFAULT_ENDPOINT_URL).rstrip("/")
    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or DEFAULT_REGION
    errors: list[dict[str, str]] = []
    resources: dict[str, dict[str, Any]] = {}
    blocks: list[str] = []
    session = boto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
        region_name=region,
    )

    clients = {
        service: _client(session, service, endpoint_url, errors)
        for service in ("s3", "lambda", "rds", "logs", "cloudwatch")
    }
    if clients["s3"] is not None:
        _collect_s3(clients["s3"], resources, blocks, errors)
    if clients["lambda"] is not None:
        _collect_lambda(clients["lambda"], resources, blocks, errors)
    if clients["rds"] is not None:
        _collect_rds(clients["rds"], resources, blocks, errors)
    if clients["logs"] is not None:
        _collect_logs(clients["logs"], resources, blocks, errors)
    if clients["cloudwatch"] is not None:
        _collect_alarms(clients["cloudwatch"], resources, blocks, errors)

    resource_lookup: dict[tuple[str, str], str] = {}
    for local_name, record in resources.items():
        configuration = record.get("configuration", {})
        for service, key in (
            ("s3", "bucket"),
            ("lambda", "function_name"),
            ("rds", "identifier"),
            ("logs", "name"),
        ):
            value = configuration.get(key) if isinstance(configuration, dict) else None
            if value:
                resource_lookup[(service, str(value))] = local_name

    metric_resources = (
        _collect_metrics(clients["cloudwatch"], resources, resource_lookup, errors)
        if clients["cloudwatch"] is not None
        else {
            name: {
                "resource_id": record["resource_id"],
                "service": record["service"],
                "resource_type": record["resource_type"],
                "is_problem": None,
                "metrics": {},
            }
            for name, record in resources.items()
        }
    )

    collected_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "collector": "ministack",
        "collected_at": collected_at,
        "endpoint_url": endpoint_url,
        "region": region,
        "period_days": COLLECTION_PERIOD_DAYS,
        "resolution": "daily",
        "collection_errors": errors,
    }
    parsed_resources = {
        name: {**record, "metrics": metric_resources.get(name, {}).get("metrics", {})}
        for name, record in resources.items()
    }
    parsed_input = {
        "schema_version": "1.0",
        "metadata": metadata,
        "region": region,
        "resources": parsed_resources,
        "tf_resources": [parsed_resources[name] for name in sorted(parsed_resources)],
        "collection_errors": errors,
    }
    metrics_payload = {
        "schema_version": "1.0",
        "metadata": metadata,
        "resources": metric_resources,
        "collection_errors": errors,
    }

    (output_path / "main.tf").write_text(_terraform_document(region, blocks), encoding="utf-8")
    _write_json(output_path / "metrics.json", metrics_payload)
    _write_json(output_path / "parsed_input.json", parsed_input)
    return output_path


__all__ = ["READ_ONLY_OPERATIONS", "collect_ministack"]
