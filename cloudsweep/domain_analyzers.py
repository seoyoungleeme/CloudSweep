"""Domain analyzer implementations for CloudSweep."""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

from .complex_domains import (
    _COMPLEX_DOMAINS,
    _load_skill_analysis_with_warnings,
)
from .domain_detection import (
    DOMAIN_KEYWORDS,
    SERVICE_ALIASES,
    ResourceBlock,
    _domain_from_service,
    _resource_blocks,
    _resource_key,
    _resource_type_matches,
)
from .evidence_normalization import normalize_environment
from .pricing_models import PRICING_SOURCE_TAG, _build_pricing_request, _load_pricing_model_with_warnings
from .rule_engine import AnalyzerRegistration, AnalyzerRegistry, RuleEngine, RuleValidationError, load_rule


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


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
                if isinstance(record, dict) and not str(name).startswith("arn:"):
                    resources[str(name)] = _merge_record(resources.get(str(name), {}), record)
        tf_resources = data.get("tf_resources")
        if isinstance(tf_resources, list):
            for record in tf_resources:
                if isinstance(record, dict):
                    key = _resource_key(record)
                    if key:
                        resources[key] = _merge_record(resources.get(key, {}), record)
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


_COMPLEX_TF_CONTEXT_TYPES: dict[str, set[str]] = {
    "rds": {
        "aws_db_instance",
        "aws_db_subnet_group",
        "aws_db_parameter_group",
        "aws_db_option_group",
    },
    "elb": {
        "aws_lb",
        "aws_elb",
        "aws_alb",
        "aws_lb_listener",
        "aws_lb_target_group",
        "aws_lb_target_group_attachment",
        "aws_route53_record",
        "aws_wafv2_web_acl_association",
        "aws_waf_web_acl",
        "aws_acm_certificate",
    },
    "ecs": {
        "aws_ecs_service",
        "aws_ecs_task_definition",
        "aws_appautoscaling_target",
        "aws_appautoscaling_policy",
        "aws_appautoscaling_scheduled_action",
        "aws_cloudwatch_metric_alarm",
    },
    "elasticache": {
        "aws_elasticache_replication_group",
        "aws_elasticache_cluster",
        "aws_elasticache_subnet_group",
        "aws_elasticache_parameter_group",
    },
}


def _coerce_tf_value(value: str) -> Any:
    value = value.split("#", 1)[0].strip().rstrip(",")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _tf_attributes(block: ResourceBlock) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for match in re.finditer(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$", block["text"], re.MULTILINE):
        name = match.group(1)
        if name in {"tags"}:
            continue
        attributes[name] = _coerce_tf_value(match.group(2))
    tags: dict[str, str] = {}
    tag_block = re.search(r"tags\s*=\s*\{(?P<body>.*?)\n\s*\}", block["text"], re.DOTALL)
    if tag_block:
        for tag in re.finditer(r"^\s*([A-Za-z0-9_-]+)\s*=\s*\"([^\"]+)\"", tag_block.group("body"), re.MULTILINE):
            tags[tag.group(1)] = tag.group(2)
    if tags:
        attributes["tags"] = tags
    return attributes


def _series_summary(metric: Any) -> dict[str, Any] | None:
    if not isinstance(metric, dict):
        return None
    datapoints = _series(metric)
    if not datapoints:
        return {
            "unit": metric.get("unit"),
            "datapoint_count": 0,
            "datapoints": [],
        }
    return {
        "unit": metric.get("unit"),
        "datapoint_count": len(datapoints),
        "avg": _avg(datapoints),
        "min": round(min(datapoints), 4),
        "max": round(max(datapoints), 4),
        "p95": _pctl(datapoints, 0.95),
        "p99": _pctl(datapoints, 0.99),
        "latest": round(datapoints[-1], 4),
        "datapoints": datapoints,
    }


def _metrics_bundle(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    return {
        str(name): summary
        for name, metric in sorted(metrics.items())
        if (summary := _series_summary(metric)) is not None
    }


def _domain_resource_records(
    domain: str,
    resources: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        name: record
        for name, record in sorted(resources.items())
        if _record_domain(record) == domain
    }


def _complex_tf_blocks(domain: str, blocks: list[ResourceBlock]) -> list[ResourceBlock]:
    context_types = _COMPLEX_TF_CONTEXT_TYPES.get(domain, set())
    return [block for block in blocks if block["type"] in context_types]


def _build_complex_skill_request(
    *,
    domain: str,
    evidence: dict[str, Any],
    work_dir: Path | None,
    blocks: list[ResourceBlock],
    metrics: dict[str, dict[str, Any]],
    analysis_resources: dict[str, dict[str, Any]],
    analysis_metadata: dict[str, Any],
    cost_summary: dict[str, Any],
    pricing_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tf_blocks = _complex_tf_blocks(domain, blocks)
    resource_records = _domain_resource_records(domain, analysis_resources)
    metric_resources: dict[str, Any] = {}
    for block in tf_blocks:
        record = _metric_record(metrics, block)
        if record:
            metric_resources[block["name"]] = {
                "resource_type": block["type"],
                "metrics": _metrics_bundle(record),
            }
    for name, record in resource_records.items():
        if record.get("metrics"):
            metric_resources.setdefault(name, {
                "resource_type": record.get("resource_type") or record.get("type") or "unknown",
                "metrics": _metrics_bundle(record),
            })

    missing: list[str] = []
    if not evidence.get("terraform"):
        missing.append("main.tf")
    if not evidence.get("metrics"):
        missing.append("metrics.json")
    if not evidence.get("cost_report"):
        missing.append("cost_report.json")

    required_output = (
        work_dir / "result" / ".machine" / f"{domain}_skill_analysis.json"
        if work_dir
        else Path("result") / ".machine" / f"{domain}_skill_analysis.json"
    )
    return {
        "schema_version": "1.0",
        "domain": domain,
        "status": "needs_skill_analysis",
        "evidence_files": evidence,
        "required_output": str(required_output),
        "output_contract": {
            "schema": "schemas/skill-analysis.schema.json",
            "required_top_level": ["schema_version", "domain", "findings"],
            "finding_shape": "graph_finding",
            "safe_defaults": {
                "estimated_monthly_saving_usd": 0.0,
                "confidence": "LOW",
            },
            "note": (
                "Skill owns complex-domain findings. Use pricing evidence in "
                "evidence_bundle.pricing before static fallback; use $0 and LOW "
                "confidence only when quantity or price is unavailable."
            ),
        },
        "evidence_bundle": {
            "schema_version": "1.0",
            "domain": domain,
            "metadata": analysis_metadata,
            "missing_evidence": missing,
            "terraform": {
                "resources": [
                    {
                        "address": f"{block['type']}.{block['name']}",
                        "type": block["type"],
                        "name": block["name"],
                        "attributes": _tf_attributes(block),
                        "text": block["text"],
                    }
                    for block in tf_blocks
                ],
            },
            "metrics": {
                "resources": metric_resources,
            },
            "cost": {
                "period_months": cost_summary.get("period_months"),
                "pricing_note": cost_summary.get("pricing_note", ""),
                "domain": cost_summary.get("domains", {}).get(domain, {}),
            },
            "pricing": pricing_context or {},
            "resource_records": resource_records,
        },
    }


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


_CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _cap_confidence(confidence: str, cap: str) -> str:
    return confidence if _CONFIDENCE_RANK[confidence] <= _CONFIDENCE_RANK[cap] else cap


def _pricing_confidence(pricing_source: str | None) -> str:
    if pricing_source == "cost_report":
        return "HIGH"
    if pricing_source == "aws_public_pricing_model":
        return "MEDIUM"
    return "LOW"


def _default_savings_status(pricing_source: str | None) -> str:
    if pricing_source == "unmeasured":
        return "unmeasured"
    if pricing_source == "reasonable_estimate":
        return "reasonable_estimate"
    return "priced"


def _add_savings_metadata(
    finding: dict[str, Any],
    *,
    pricing_source: str | None = None,
    savings_status: str | None = None,
    savings_reason: str | None = None,
    display_name: str | None = None,
    pricing_confidence: str | None = None,
) -> dict[str, Any]:
    source = pricing_source if pricing_source is not None else finding.get("pricing_source")
    if source is not None:
        finding.setdefault("pricing_source", source)
    finding.setdefault("pricing_confidence", pricing_confidence or _pricing_confidence(source))
    finding.setdefault("savings_status", savings_status or _default_savings_status(source))
    if savings_reason:
        finding.setdefault("savings_reason", savings_reason)
    if display_name:
        finding.setdefault("display_name", display_name)
    return finding


def _provider_region(analysis_metadata: dict[str, Any], tf_text: str | None = None) -> str:
    region = (analysis_metadata or {}).get("region")
    if isinstance(region, str) and region:
        return region
    if tf_text:
        match = re.search(r'provider\s+"aws"\s*\{[^}]*?region\s*=\s*"([^"]+)"', tf_text, re.DOTALL)
        if match:
            return match.group(1)
    return "us-east-1"


def _sku_entry(sku_key: str, service_code: str, region: str, unit: str, **attributes: Any) -> dict[str, Any]:
    entry = {
        "sku_key": sku_key,
        "service_code": service_code,
        "region": region,
        "unit": unit,
    }
    for key, value in attributes.items():
        if value is not None:
            entry[key] = value
    return entry


def _unique_skus(skus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for sku in skus:
        sku_key = str(sku.get("sku_key") or "").strip()
        if sku_key:
            unique[sku_key] = sku
    return [unique[key] for key in sorted(unique)]


def _normalize_rds_engine(engine: str | None) -> str:
    value = (engine or "").strip().lower()
    if "postgres" in value:
        return "postgres"
    if "mysql" in value and "aurora" not in value:
        return "mysql"
    if "mariadb" in value:
        return "mariadb"
    if "oracle" in value:
        return "oracle"
    if "sqlserver" in value or "sql_server" in value:
        return "sqlserver"
    return value or "unknown"


def _rds_pricing_skus(tf_blocks: list[ResourceBlock], region: str) -> list[dict[str, Any]]:
    rule_doc = _get_rule_doc("rds", "overprovisioned_rds.json")
    downsize = rule_doc.get("downsize_recommendations", {})
    skus: list[dict[str, Any]] = []
    for block in tf_blocks:
        if block["type"] != "aws_db_instance":
            continue
        attributes = _tf_attributes(block)
        instance_class = str(attributes.get("instance_class") or "").strip()
        if not instance_class:
            continue
        engine = _normalize_rds_engine(str(attributes.get("engine") or ""))
        current_deployment = "multi_az" if attributes.get("multi_az") is True else "single_az"
        deployments = {current_deployment}
        if current_deployment == "multi_az":
            deployments.add("single_az")
        classes = {instance_class}
        target_class = downsize.get(instance_class)
        if isinstance(target_class, str) and target_class:
            classes.add(target_class)
        for class_name in classes:
            for deployment in deployments:
                skus.append(
                    _sku_entry(
                        f"{region}|{engine}|{class_name}|{deployment}",
                        "AmazonRDS",
                        region,
                        "InstanceHour",
                        engine=engine,
                        instance_class=class_name,
                        deployment=deployment,
                    )
                )
    return _unique_skus(skus)


def _elb_pricing_skus(tf_blocks: list[ResourceBlock], region: str) -> list[dict[str, Any]]:
    skus: list[dict[str, Any]] = []
    capacity_units = {
        "application": "LCU-Hour",
        "network": "NLCU-Hour",
        "gateway": "GLCU-Hour",
    }
    for block in tf_blocks:
        if block["type"] not in {"aws_lb", "aws_alb", "aws_elb"}:
            continue
        if block["type"] == "aws_elb":
            lb_type = "classic"
        elif block["type"] == "aws_alb":
            lb_type = "application"
        else:
            lb_type = str(_tf_attributes(block).get("load_balancer_type") or "application").lower()
        skus.append(
            _sku_entry(
                f"{region}|{lb_type}|load_balancer_hour",
                "AWSELB",
                region,
                "LoadBalancer-Hour",
                load_balancer_type=lb_type,
                charge_type="load_balancer_hour",
            )
        )
        unit = capacity_units.get(lb_type)
        if unit:
            skus.append(
                _sku_entry(
                    f"{region}|{lb_type}|capacity_unit_hour",
                    "AWSELB",
                    region,
                    unit,
                    load_balancer_type=lb_type,
                    charge_type="capacity_unit_hour",
                )
            )
    return _unique_skus(skus)


def _ecs_architecture(tf_blocks: list[ResourceBlock]) -> str:
    for block in tf_blocks:
        if block["type"] != "aws_ecs_task_definition":
            continue
        match = re.search(r'cpu_architecture\s*=\s*"([^"]+)"', block["text"], re.IGNORECASE)
        if match:
            architecture = match.group(1).lower()
            return "arm64" if architecture == "arm64" else "x86_64"
    return "x86_64"


def _ecs_pricing_skus(tf_blocks: list[ResourceBlock], region: str) -> list[dict[str, Any]]:
    has_fargate = any(
        block["type"] == "aws_ecs_service"
        and (_attr(block["text"], "launch_type") or "FARGATE").upper() == "FARGATE"
        for block in tf_blocks
    )
    if not has_fargate:
        return []
    architecture = _ecs_architecture(tf_blocks)
    common = {
        "launch_type": "Fargate",
        "operating_system": "Linux",
        "architecture": architecture,
    }
    return [
        _sku_entry(
            f"{region}|fargate|linux|{architecture}|vcpu_hour",
            "AmazonECS",
            region,
            "vCPU-Hour",
            **common,
            charge_type="vcpu_hour",
        ),
        _sku_entry(
            f"{region}|fargate|linux|{architecture}|gb_hour",
            "AmazonECS",
            region,
            "GB-Hour",
            **common,
            charge_type="gb_hour",
        ),
    ]


def _elasticache_pricing_skus(tf_blocks: list[ResourceBlock], region: str) -> list[dict[str, Any]]:
    resource_blocks = [
        block
        for block in tf_blocks
        if block["type"] in {"aws_elasticache_replication_group", "aws_elasticache_cluster"}
    ]
    if not resource_blocks:
        return []
    engines = {
        str(_tf_attributes(block).get("engine") or "redis").lower()
        for block in resource_blocks
    }
    rule_doc = _get_rule_doc("elasticache", "overprovisioned_elasticache.json")
    static_node_types = rule_doc.get("cost", {}).get("node_types", {})
    node_types = {
        str(_tf_attributes(block).get("node_type") or "").strip()
        for block in resource_blocks
        if _tf_attributes(block).get("node_type")
    }
    if isinstance(static_node_types, dict):
        node_types.update(str(node_type) for node_type in static_node_types)
    skus: list[dict[str, Any]] = []
    for engine in engines:
        for node_type in sorted(node_types):
            skus.append(
                _sku_entry(
                    f"{region}|{engine}|{node_type}|node_hour",
                    "AmazonElastiCache",
                    region,
                    "NodeHour",
                    engine=engine,
                    node_type=node_type,
                    charge_type="node_hour",
                )
            )
    return _unique_skus(skus)


def _complex_pricing_skus(
    domain: str,
    blocks: list[ResourceBlock],
    analysis_metadata: dict[str, Any],
    tf_text: str | None,
) -> list[dict[str, Any]]:
    tf_blocks = _complex_tf_blocks(domain, blocks)
    region = _provider_region(analysis_metadata, tf_text)
    if domain == "rds":
        return _rds_pricing_skus(tf_blocks, region)
    if domain == "elb":
        return _elb_pricing_skus(tf_blocks, region)
    if domain == "ecs":
        return _ecs_pricing_skus(tf_blocks, region)
    if domain == "elasticache":
        return _elasticache_pricing_skus(tf_blocks, region)
    return []


def _complex_pricing_context_and_request(
    *,
    domain: str,
    work_dir: Path | None,
    blocks: list[ResourceBlock],
    analysis_metadata: dict[str, Any],
    pricing_models: dict[str, dict[str, Any]],
    tf_text: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    skus = _complex_pricing_skus(domain, blocks, analysis_metadata, tf_text)
    resolved_unit_prices: list[dict[str, Any]] = []
    unresolved_skus: list[dict[str, Any]] = []
    for sku in skus:
        sku_key = sku["sku_key"]
        model = pricing_models.get(sku_key)
        if model:
            resolved_unit_prices.append(
                {
                    "sku_key": sku_key,
                    "unit": model["unit"],
                    "price_usd": model["price_usd"],
                }
            )
        else:
            unresolved_skus.append(sku)
    context = {
        "schema_version": "1.0",
        "pricing_source_priority": [
            "cost_report",
            "aws_public_pricing_model",
            "static_fallback_estimate",
            "reasonable_estimate",
            "unmeasured",
        ],
        "pricing_model": {
            "schema_version": "1.0",
            "domain": domain,
            "pricing_source": PRICING_SOURCE_TAG,
            "unit_prices": resolved_unit_prices,
        },
        "unresolved_skus": unresolved_skus,
        "static_fallback": {
            "source": f".claude/skills/finops-{domain}/rules/*.json",
            "pricing_source": "static_fallback_estimate",
        },
    }
    return context, _build_pricing_request(domain, unresolved_skus, work_dir)


def _skill_findings_need_pricing_reanalysis(
    skill_findings: list[dict[str, Any]],
    pricing_context: dict[str, Any],
) -> bool:
    unit_prices = pricing_context.get("pricing_model", {}).get("unit_prices", [])
    if not unit_prices:
        return False
    return any(
        finding.get("pricing_source") == "static_fallback_estimate"
        for finding in skill_findings
    )


def _pricing_model_unit_price(pricing_context: dict[str, Any], sku_key: str) -> float | None:
    for entry in pricing_context.get("pricing_model", {}).get("unit_prices", []):
        if entry.get("sku_key") == sku_key and isinstance(entry.get("price_usd"), (int, float)):
            return float(entry["price_usd"])
    return None


def _rds_static_hourly_price(engine: str, instance_class: str, deployment: str) -> float | None:
    rule_doc = _get_rule_doc("rds", "overprovisioned_rds.json")
    static_prices = rule_doc.get("cost", {}).get("static_instance_hourly_usd", {})
    if not isinstance(static_prices, dict):
        return None
    value = static_prices.get(f"{engine}|{instance_class}|{deployment}")
    return float(value) if isinstance(value, (int, float)) else None


def _rds_hourly_price(
    *,
    engine: str,
    instance_class: str,
    deployment: str,
    region: str,
    pricing_context: dict[str, Any],
) -> tuple[float | None, str | None]:
    sku_key = f"{region}|{engine}|{instance_class}|{deployment}"
    model_price = _pricing_model_unit_price(pricing_context, sku_key)
    if model_price is not None:
        return model_price, "aws_public_pricing_model"
    static_price = _rds_static_hourly_price(engine, instance_class, deployment)
    if static_price is not None:
        return static_price, "static_fallback_estimate"
    return None, None


def _append_evidence_once(finding: dict[str, Any], *items: str) -> None:
    evidence = finding.setdefault("evidence", [])
    for item in items:
        if item and item not in evidence:
            evidence.append(item)


def _enrich_rds_skill_findings(
    skill_findings: list[dict[str, Any]],
    blocks: list[ResourceBlock],
    pricing_context: dict[str, Any],
    analysis_metadata: dict[str, Any],
    tf_text: str | None,
) -> list[dict[str, Any]]:
    rds_blocks = {block["name"]: block for block in blocks if block["type"] == "aws_db_instance"}
    rule_doc = _get_rule_doc("rds", "overprovisioned_rds.json")
    recommendations = rule_doc.get("downsize_recommendations", {})
    hours = _number(rule_doc.get("cost", {}), "hours_per_month") or 730.0
    region = _provider_region(analysis_metadata or {}, tf_text)
    enriched: list[dict[str, Any]] = []

    for original in skill_findings:
        finding = dict(original)
        evidence = finding.get("evidence", [])
        finding["evidence"] = list(evidence) if isinstance(evidence, list) else [str(evidence)]
        block = rds_blocks.get(str(finding.get("resource", "")))
        identifier = _attr(block["text"], "identifier") if block else None
        if identifier:
            finding.setdefault("display_name", identifier)

        pricing_source = str(finding.get("pricing_source") or "unmeasured")
        rule_id = str(finding.get("rule_id") or "")
        if pricing_source != "unmeasured":
            _add_savings_metadata(
                finding,
                savings_reason=(
                    "priced_from_public_rds_instance_hours"
                    if pricing_source == "aws_public_pricing_model"
                    else "priced_from_rds_cost_evidence"
                    if pricing_source == "cost_report"
                    else "static_rule_estimate"
                ),
                display_name=identifier,
            )
            enriched.append(finding)
            continue

        if rule_id == "RDS_R2_LOW_UTILIZATION" and block:
            attrs = _tf_attributes(block)
            engine = _normalize_rds_engine(str(attrs.get("engine") or ""))
            current_class = str(attrs.get("instance_class") or "")
            target_class = recommendations.get(current_class) if isinstance(recommendations, dict) else None
            deployment = "multi_az" if bool(attrs.get("multi_az")) else "single_az"
            current_price, current_source = _rds_hourly_price(
                engine=engine,
                instance_class=current_class,
                deployment=deployment,
                region=region,
                pricing_context=pricing_context,
            )
            target_price, target_source = (
                _rds_hourly_price(
                    engine=engine,
                    instance_class=str(target_class),
                    deployment=deployment,
                    region=region,
                    pricing_context=pricing_context,
                )
                if target_class
                else (None, None)
            )
            if current_price is not None and target_price is not None and current_price > target_price:
                finding["estimated_monthly_saving_usd"] = round((current_price - target_price) * hours, 2)
                finding["pricing_source"] = "reasonable_estimate"
                finding["pricing_confidence"] = "LOW"
                finding["savings_status"] = "reasonable_estimate"
                finding["savings_reason"] = "safety_or_target_pricing_evidence_missing"
                _append_evidence_once(
                    finding,
                    f"target_instance_class={target_class}",
                    f"current_hourly_usd={current_price}",
                    f"target_hourly_usd={target_price}",
                    f"hours_per_month={hours:g}",
                    f"pricing_model_source={current_source if current_source == target_source else 'mixed'}",
                    "savings_reason=safety_or_target_pricing_evidence_missing",
                )
                _add_savings_metadata(
                    finding,
                    pricing_source="reasonable_estimate",
                    savings_status="reasonable_estimate",
                    savings_reason="safety_or_target_pricing_evidence_missing",
                    display_name=identifier,
                    pricing_confidence="LOW",
                )
                enriched.append(finding)
                continue

            _append_evidence_once(finding, "savings_reason=safety_or_target_pricing_evidence_missing")
            _add_savings_metadata(
                finding,
                pricing_source="unmeasured",
                savings_status="unmeasured",
                savings_reason="safety_or_target_pricing_evidence_missing",
                display_name=identifier,
            )
            enriched.append(finding)
            continue

        if rule_id == "RDS_R5_GP2_STORAGE":
            _append_evidence_once(finding, "savings_reason=storage_price_or_iops_evidence_missing")
            _add_savings_metadata(
                finding,
                pricing_source="unmeasured",
                savings_status="unmeasured",
                savings_reason="storage_price_or_iops_evidence_missing",
                display_name=identifier,
            )
            enriched.append(finding)
            continue

        _append_evidence_once(finding, "savings_reason=quantity_or_price_unavailable")
        _add_savings_metadata(
            finding,
            pricing_source="unmeasured",
            savings_status="unmeasured",
            savings_reason="quantity_or_price_unavailable",
            display_name=identifier,
        )
        enriched.append(finding)

    return enriched


def _lambda_architecture(block_text: str) -> str:
    match = re.search(r'architectures\s*=\s*\[\s*"([^"]+)"', block_text)
    return match.group(1) if match else "x86_64"


def _lambda_static_price(rule_doc: dict[str, Any], architecture: str) -> float | None:
    cost = rule_doc.get("cost", {})
    if architecture == "arm64":
        return _number(cost, "price_per_gb_second_usd_arm64")
    return _number(cost, "price_per_gb_second_usd_x86")


def _resolve_unit_price(
    sku_key: str,
    pricing_models: dict[str, dict[str, Any]],
    static_price: float | None,
) -> tuple[float | None, str, str]:
    """Resolve a per-unit price for sku_key, returning (price, pricing_source, confidence_cap).

    Tries the Claude-supplied public pricing model first, then the domain rule's
    static fallback price. Never blocks on the pricing model being absent -- a
    static price alone is sufficient to produce a non-zero, LOW-confidence estimate.
    """
    model = (pricing_models or {}).get(sku_key)
    if model and isinstance(model.get("price_usd"), (int, float)):
        return float(model["price_usd"]), "aws_public_pricing_model", "MEDIUM"
    if static_price is not None:
        return static_price, "static_fallback_estimate", "LOW"
    return None, "unmeasured", "LOW"


def _s3_bucket_quantity_gb(record: dict[str, Any] | None, metric_record: dict[str, Any] | None) -> float | None:
    for source in (record, metric_record):
        if not isinstance(source, dict):
            continue
        configuration = source.get("configuration", {})
        if isinstance(configuration, dict):
            for key in ("bucket_size_gb", "size_gb", "average_size_gb", "storage_gb"):
                value = _number(configuration, key)
                if value is not None:
                    return value
            stored_bytes = _number(configuration, "stored_bytes") or _number(configuration, "bucket_size_bytes")
            if stored_bytes is not None:
                return stored_bytes / (1024 ** 3)
        metrics_map = source.get("metrics", {})
        if isinstance(metrics_map, dict):
            size_series = _series(metrics_map.get("bucket_size_bytes", {}))
            if size_series:
                avg_bytes = _avg(size_series)
                if avg_bytes is not None:
                    return avg_bytes / (1024 ** 3)
    return None


def _lambda_monthly_gb_seconds(
    record: dict[str, Any] | None,
    metadata: dict[str, Any],
    allocated_mb: int,
) -> float | None:
    if not isinstance(record, dict):
        return None
    invocations = _monthly_metric_total(record, "invocations", metadata or {})
    if invocations is None:
        return None
    duration_avg_ms = _metric_avg(record, "duration")
    if duration_avg_ms is None:
        return None
    return invocations * (duration_avg_ms / 1000.0) * (allocated_mb / 1024.0)


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


def _analyze_lambda(
    blocks: list[ResourceBlock],
    metrics: dict[str, dict[str, Any]],
    cost_summary: dict[str, Any],
    analysis_metadata: dict[str, Any] | None = None,
    pricing_models: dict[str, dict[str, Any]] | None = None,
    work_dir: Path | None = None,
    tf_text: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any] | None]:
    lambda_blocks = [block for block in blocks if block["type"] == "aws_lambda_function"]
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    flagged: list[tuple[ResourceBlock, dict[str, Any], int, int, str]] = []
    for block in lambda_blocks:
        allocated = _attr_int(block["text"], "memory_size")
        record = _metric_record(metrics, block)
        metric_values = _series((record or {}).get("metrics", {}).get("memory_used_mb", {}))
        p99 = _pctl(metric_values, 0.99)
        avg = _avg(metric_values)
        is_problem = bool((record or {}).get("is_problem"))
        function_name = _attr(block["text"], "function_name") or block["name"]

        if allocated and p99 is not None and p99 > allocated:
            warnings.append(
                f"Lambda metric inconsistency for {block['name']} ({function_name}): "
                f"p99_memory_used_mb={p99} exceeds allocated_memory_mb={allocated}; "
                "excluded from rightsizing."
            )
            continue

        utilization = p99 / allocated if allocated and p99 is not None else None
        waste_named = "waste" in function_name.lower() or "waste" in block["name"].lower()
        standard_candidate = utilization is not None and utilization <= 0.25
        waste_relaxed_candidate = (
            waste_named
            and allocated is not None
            and allocated >= 1024
            and utilization is not None
            and utilization <= 0.35
        )

        if allocated and allocated >= 1024 and (standard_candidate or waste_relaxed_candidate or is_problem):
            recommended = min(allocated, _next_lambda_memory(p99))
            confidence = "MEDIUM" if (standard_candidate or is_problem) else "LOW"
            flagged.append((
                block,
                {
                    "avg": avg,
                    "p99": p99,
                    "points": len(metric_values),
                    "utilization": utilization,
                    "trigger": (
                        "p99_memory_lte_25_pct"
                        if standard_candidate
                        else "waste_name_lte_35_pct"
                        if waste_relaxed_candidate
                        else "metric_problem_flag"
                    ),
                },
                allocated,
                recommended,
                confidence,
            ))

    monthly = _domain_cost(cost_summary, "lambda")
    rule_doc = _get_rule_doc("lambda", "overprovisioned_lambda.json")
    region = _provider_region(analysis_metadata or {}, tf_text)
    needed_skus: dict[str, dict[str, Any]] = {}
    for block, metric_summary, allocated, recommended, confidence in flagged:
        waste_fraction = max(0.0, 1 - recommended / allocated)
        if monthly:
            per_resource = round((monthly * waste_fraction) / max(len(flagged), 1), 2)
            pricing_source = "cost_report"
            savings_reason = "cost_report_available"
        else:
            architecture = _lambda_architecture(block["text"])
            sku_key = f"{region}|{architecture}"
            record = _metric_record(metrics, block)
            gb_seconds = _lambda_monthly_gb_seconds(record, analysis_metadata or {}, allocated)
            static_price = _lambda_static_price(rule_doc, architecture)
            price, price_tier, _cap = _resolve_unit_price(sku_key, pricing_models or {}, static_price)
            if gb_seconds is not None and price is not None:
                per_resource = round(gb_seconds * price * waste_fraction, 2)
                pricing_source = price_tier
                savings_reason = "priced_from_lambda_gb_seconds"
            else:
                per_resource = 0.0
                pricing_source = "unmeasured"
                savings_reason = "lambda_gb_seconds_not_observed" if gb_seconds is None else "unit_price_unavailable"
            if gb_seconds is not None and price_tier != "aws_public_pricing_model":
                needed_skus[sku_key] = {
                    "sku_key": sku_key,
                    "service_code": "AWSLambda",
                    "region": region,
                    "architecture": architecture,
                    "unit": "Lambda-GB-Second",
                }
        new_block = _replace_attr(block["text"], "memory_size", recommended)
        findings.append(
            {
                "domain": "lambda",
                "resource": block["name"],
                "rule_id": "LAMBDA_RIGHTSIZE_POLICY:L1",
                "severity": "HIGH",
                "confidence": confidence,
                "estimated_monthly_saving_usd": per_resource,
                "pricing_source": pricing_source,
                "evidence": [
                    f"allocated_memory_mb={allocated}",
                    f"p99_memory_used_mb={metric_summary['p99']}",
                    f"memory_utilization_ratio={round(metric_summary['utilization'], 4) if metric_summary['utilization'] is not None else None}",
                    f"datapoints={metric_summary['points']}",
                    f"trigger={metric_summary['trigger']}",
                    f"pricing_source={pricing_source}",
                    f"savings_reason={savings_reason}",
                ],
                "recommendation": f"Set memory_size to {recommended} MB, then validate p95/p99 duration and errors.",
                "optimized_replacement": {"resource": block["name"], "text": new_block},
            }
        )
        _add_savings_metadata(
            findings[-1],
            savings_reason=savings_reason,
            display_name=_attr(block["text"], "function_name") or block["name"],
        )
    pricing_request = _build_pricing_request("lambda", list(needed_skus.values()), work_dir)
    return findings, warnings, pricing_request


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


_S3_NONPROD_ENVIRONMENTS = {"dev", "test", "staging", "sandbox"}
_S3_STRONG_LIFECYCLE_KEYWORDS = {
    "deprecated",
    "old",
    "temp",
    "scratch",
    "poc",
    "raw",
    "archive",
    "unused",
    "dump",
    "migration",
}
_S3_WEAK_LIFECYCLE_KEYWORDS = {"logs", "backup"}


def _bucket_lifecycle_signals(bucket_name: str, env: str | None) -> tuple[bool, list[str], bool]:
    normalized_name = bucket_name.lower().replace("_", "-")
    keyword_hits = sorted(
        keyword
        for keyword in _S3_STRONG_LIFECYCLE_KEYWORDS | _S3_WEAK_LIFECYCLE_KEYWORDS
        if keyword in normalized_name
    )
    strong_keyword = any(keyword in _S3_STRONG_LIFECYCLE_KEYWORDS for keyword in keyword_hits)
    nonprod = env in _S3_NONPROD_ENVIRONMENTS
    return nonprod, keyword_hits, strong_keyword


def _analyze_s3(
    blocks: list[ResourceBlock],
    metrics: dict[str, dict[str, Any]],
    cost_summary: dict[str, Any],
    analysis_resources: dict[str, dict[str, Any]] | None = None,
    analysis_metadata: dict[str, Any] | None = None,
    pricing_models: dict[str, dict[str, Any]] | None = None,
    work_dir: Path | None = None,
    tf_text: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    bucket_blocks = [block for block in blocks if block["type"] == "aws_s3_bucket"]
    lifecycle_targets = _lifecycle_targets(blocks)
    flagged: list[tuple[ResourceBlock, str, list[str], str]] = []
    for block in bucket_blocks:
        bucket_name = _attr(block["text"], "bucket") or block["name"]
        record = _metric_record(metrics, block)
        is_problem = bool((record or {}).get("is_problem"))
        has_lifecycle = block["name"] in lifecycle_targets or bucket_name in lifecycle_targets
        env = normalize_environment(_tag_value(block["text"], "Environment") or "")
        nonprod, keyword_hits, strong_keyword = _bucket_lifecycle_signals(bucket_name, env)
        has_cost_signal = bool(_domain_cost(cost_summary, "s3"))
        if not has_lifecycle and (is_problem or has_cost_signal or nonprod or keyword_hits):
            confidence = "MEDIUM" if (is_problem or has_cost_signal or nonprod or strong_keyword) else "LOW"
            flagged.append((block, confidence, keyword_hits, env))

    monthly = _domain_cost(cost_summary, "s3")
    rule_doc = _get_rule_doc("s3", "missing_lifecycle_policy.json")
    static_price = _number(rule_doc.get("cost", {}), "s3_standard_per_gb_month_usd")
    region = _provider_region(analysis_metadata or {}, tf_text)
    needed_skus: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for block, confidence, keyword_hits, env in flagged:
        bucket_name = _attr(block["text"], "bucket") or block["name"]
        evidence = [f"bucket={bucket_name}", "no aws_s3_bucket_lifecycle_configuration reference found"]
        if env:
            evidence.append(f"environment={env}")
        if keyword_hits:
            evidence.append(f"name_keywords={','.join(keyword_hits)}")

        if monthly:
            per_resource = round((monthly * 0.75) / max(len(flagged), 1), 2)
            pricing_source = "cost_report"
            savings_reason = "cost_report_available"
        else:
            sku_key = f"{region}|STANDARD"
            record = (analysis_resources or {}).get(block["name"])
            quantity_gb = _s3_bucket_quantity_gb(record, _metric_record(metrics, block))
            price, price_tier, _cap = _resolve_unit_price(sku_key, pricing_models or {}, static_price)
            if quantity_gb is not None and price is not None:
                per_resource = round(quantity_gb * price * 0.75, 2)
                pricing_source = price_tier
                savings_reason = "priced_from_bucket_size_and_unit_price"
                evidence.append(f"bucket_size_gb={round(quantity_gb, 2)}")
                evidence.append(f"unit_price_usd_per_gb_month={price}")
            else:
                per_resource = 0.0
                pricing_source = "unmeasured"
                if quantity_gb is None:
                    evidence.append("quantity_unavailable=bucket_size_not_observed")
                    savings_reason = "bucket_size_not_observed"
                else:
                    savings_reason = "unit_price_unavailable"
            if quantity_gb is not None and price_tier != "aws_public_pricing_model":
                needed_skus[sku_key] = {
                    "sku_key": sku_key,
                    "service_code": "AmazonS3",
                    "region": region,
                    "storage_class": "STANDARD",
                    "unit": "GB-Mo",
                }
        evidence.append(f"pricing_source={pricing_source}")
        evidence.append(f"savings_reason={savings_reason}")

        findings.append(
            {
                "domain": "s3",
                "resource": block["name"],
                "rule_id": "S3_LIFECYCLE_POLICY:V1",
                "severity": "MEDIUM",
                "confidence": confidence,
                "estimated_monthly_saving_usd": per_resource,
                "pricing_source": pricing_source,
                "evidence": evidence,
                "recommendation": "Add lifecycle transitions only after validating restore, compliance, and access patterns.",
                "optimized_append": _lifecycle_block(block),
            }
        )
        _add_savings_metadata(
            findings[-1],
            savings_reason=savings_reason,
            display_name=bucket_name,
        )
    pricing_request = _build_pricing_request("s3", list(needed_skus.values()), work_dir)
    return findings, pricing_request


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
                "rule_id": "DYNAMODB_CAPACITY_POLICY:D1",
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
    snapshots = [b for b in blocks if b["type"] == "aws_ebs_snapshot"]
    sources = [{"block": b, "all_blocks": blocks} for b in snapshots]
    return _findings_from_engine(
        "ebs", _get_rule_doc("ebs", "orphaned_snapshot.json"),
        _EBS_ENGINE, sources, cost_summary,
        frozenset({"has_deleted_source_volume", "has_ami_reference", "has_backup_reference"}),
    )


def _analyze_elb(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    lbs = [block for block in blocks if block["type"] in {"aws_lb", "aws_elb", "aws_alb"}]
    listeners = [block for block in blocks if block["type"] == "aws_lb_listener"]
    tg_blocks = [block for block in blocks if block["type"] == "aws_lb_target_group"]
    tg_attachments = [block for block in blocks if block["type"] == "aws_lb_target_group_attachment"]
    waf_assocs = [block for block in blocks if block["type"] in {"aws_wafv2_web_acl_association", "aws_waf_web_acl"}]
    findings: list[dict[str, Any]] = []
    lb_cost = _split_domain_cost(cost_summary, "elb", len(lbs))

    for block in lbs:
        is_clb = block["type"] == "aws_elb"
        lb_type = (_attr(block["text"], "load_balancer_type") or "application").lower()
        is_alb = lb_type == "application" and not is_clb
        env = (_tag_value(block["text"], "Environment") or "").lower()
        purpose = (_tag_value(block["text"], "Purpose") or "").lower()
        is_dr = env in {"dr", "disaster-recovery"} or "dr" in env or purpose in {"standby", "dr"}

        record = _metric_record(metrics, block) or {}
        requests = (
            _series(record.get("metrics", {}).get("request_count", {}))
            or _series(record.get("metrics", {}).get("request_count_sum", {}))
        )
        connections = (
            _series(record.get("metrics", {}).get("active_connection_count", {}))
            or _series(record.get("metrics", {}).get("active_flow_count", {}))
        )
        is_problem = bool(record.get("is_problem"))

        # LB4: Classic Load Balancer: always flag for migration
        if is_clb:
            findings.append(_finding(
                "elb", block["name"], "ELB_LB4_MIGRATE_CLB", "MEDIUM", "HIGH", lb_cost,
                ["load_balancer_type=classic (aws_elb)"],
                "Migrate from Classic Load Balancer to ALB for advanced routing, gRPC, WebSockets, and WAF support.",
            ))
            continue

        # LB1: Completely idle: zero requests and zero active connections
        zero_requests = bool(requests) and sum(requests) == 0
        zero_connections = not connections or max(connections) == 0
        if not is_dr and ((zero_requests and zero_connections) or is_problem):
            findings.append(_finding(
                "elb", block["name"], "ELB_LB1_UNUSED", "HIGH",
                "HIGH" if requests else "MEDIUM", lb_cost,
                [
                    f"request_count_sum={sum(requests) if requests else 'not_available'}",
                    f"active_connection_count_max={max(connections) if connections else 'not_available'}",
                ],
                "Verify DNS, certificates, WAF, blue/green, and DR dependencies before deletion.",
            ))
            continue

        # LB2: Very low request rate but not zero
        if requests and not zero_requests:
            req_avg = _avg(requests) or 0.0
            if req_avg < 100 and not is_dr:
                findings.append(_finding(
                    "elb", block["name"], "ELB_LB2_LOW_UTILIZATION", "MEDIUM", "MEDIUM",
                    lb_cost * 0.5,
                    [f"request_count_avg={round(req_avg, 1)}", "target_health=all_healthy_assumed"],
                    "Review consolidation opportunities. Validate blue/green, canary, and weighted routing dependencies.",
                ))

        # LB3: ALB that may not need ALB features (no WAF, no TLS offload in slice)
        if is_alb:
            lb_name = _attr(block["text"], "name") or block["name"]
            has_waf = any(
                block["name"] in a["text"] or lb_name in a["text"]
                for a in waf_assocs
            )
            has_tls = any(
                (block["name"] in lst["text"] or lb_name in lst["text"])
                and "ssl_policy" in lst["text"]
                for lst in listeners
            )
            if not has_waf and not has_tls:
                findings.append(_finding(
                    "elb", block["name"], "ELB_LB3_REVIEW_NLB_DOWNGRADE", "LOW", "LOW",
                    lb_cost * 0.2,
                    [f"load_balancer_type={lb_type}", "waf_association=not_found_in_slice",
                     "ssl_policy=not_found_in_slice"],
                    "Evaluate NLB if only TCP/UDP forwarding is needed; confirm no WAF, TLS offload, or host/path routing requirements.",
                ))

    # LB5: Listeners present but no target group attachments found in slice
    if listeners and tg_blocks and not tg_attachments:
        for lst in listeners:
            findings.append(_finding(
                "elb", lst["name"], "ELB_LB5_STALE_LISTENER", "HIGH", "MEDIUM", 0.0,
                ["aws_lb_listener present", "aws_lb_target_group present",
                 "no aws_lb_target_group_attachment found in Terraform slice"],
                "Verify target group membership. Delete or re-register targets after confirming no blue/green deployment dependency.",
            ))

    return findings


_RDS_EXTENDED_SUPPORT_ENGINES: dict[str, set[str]] = {
    "mysql": {"5.7"},
    "mariadb": {"10.3", "10.4", "10.5"},
    "postgres": {"11", "12"},
}


def _rds_in_extended_support(engine: str, engine_version: str) -> bool:
    engine_lc = (engine or "").lower().replace("aurora-", "")
    major = (engine_version or "").split(".")[0]
    major_minor = ".".join((engine_version or "").split(".")[:2])
    versions = _RDS_EXTENDED_SUPPORT_ENGINES.get(engine_lc, set())
    return major in versions or major_minor in versions


def _analyze_rds(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    dbs = [block for block in blocks if block["type"] == "aws_db_instance"]
    findings: list[dict[str, Any]] = []
    domain_monthly = _domain_cost(cost_summary, "rds")
    monthly = _split_domain_cost(cost_summary, "rds", len(dbs))

    for block in dbs:
        env = normalize_environment(_tag_value(block["text"], "Environment")) or "unknown"
        multi_az = _attr_bool(block["text"], "multi_az")
        instance_class = _attr(block["text"], "instance_class") or ""
        engine = _attr(block["text"], "engine") or ""
        engine_version = _attr(block["text"], "engine_version") or ""
        storage_type = _attr(block["text"], "storage_type") or "gp2"
        is_replica = bool(_attr(block["text"], "replicate_source_db"))
        is_prod = env in {"prod", "production", "prd"}
        is_nonprod = env in {"dev", "test", "staging", "sandbox", "nonprod"}
        in_extended_support = _rds_in_extended_support(engine, engine_version)

        record = _metric_record(metrics, block) or {}
        metric_map = record.get("metrics", {})
        cpu = _series(metric_map.get("cpu_utilization", {})) or _series(metric_map.get("cpuutilization", {}))
        connections = _series(record.get("metrics", {}).get("database_connections", {}))

        # R1: Non-production with Multi-AZ
        if multi_az and is_nonprod:
            findings.append(_finding(
                "rds", block["name"], "RDS_R1_NONPROD_MULTI_AZ", "MEDIUM", "MEDIUM",
                monthly * 0.5,
                ["multi_az=true", f"environment={env}", "SLA/DR/compliance requirement not available"],
                "Review SLA, DR, and compliance requirements before changing non-production Multi-AZ.",
                optimized_replacement={"resource": block["name"], "text": _replace_attr(block["text"], "multi_az", "false")},
            ))

        # R2: Low CPU utilization: rightsize instance class
        if cpu and (_avg(cpu) or 100) < 20 and (_pctl(cpu, 0.95) or 100) < 40:
            findings.append(_finding(
                "rds", block["name"], "RDS_R2_LOW_UTILIZATION", "HIGH", "MEDIUM",
                monthly * 0.25,
                [f"cpu_avg_pct={_avg(cpu)}", f"cpu_p95_pct={_pctl(cpu, 0.95)}"],
                "Benchmark a smaller supported DB class after checking memory, IOPS, connections, and latency.",
            ))

        # R3: No Reserved Instance for steady production workload
        if (
            is_prod
            and not is_replica
            and not in_extended_support
            and domain_monthly > 100
            and "micro" not in instance_class
            and "small" not in instance_class
        ):
            cpu_avg = _avg(cpu)
            if cpu_avg is None or cpu_avg > 5:
                findings.append(_finding(
                    "rds", block["name"], "RDS_R3_NO_RESERVED_INSTANCE", "LOW", "MEDIUM",
                    monthly * 0.30,
                    [f"environment={env}", f"instance_class={instance_class}",
                     f"avg_monthly_rds_spend_usd={round(domain_monthly, 2)}",
                     "reserved_instance_coverage=not_evidenced_in_terraform"],
                    "Model 1-year Reserved Instance savings (~30% off on-demand) after confirming stable instance class for 60+ days.",
                ))

        # R4: Extended Support charges: engine version past mainstream support
        if in_extended_support:
            findings.append(_finding(
                "rds", block["name"], "RDS_R4_EXTENDED_SUPPORT", "HIGH", "HIGH",
                monthly * 0.20,
                [f"engine={engine}", f"engine_version={engine_version}",
                 "extended_support_charges=active"],
                f"Upgrade to a supported major version to eliminate Extended Support charges. Validate application compatibility before migrating.",
            ))

        # R5: gp2 storage to gp3 provides better baseline performance at lower cost
        if storage_type == "gp2":
            findings.append(_finding(
                "rds", block["name"], "RDS_R5_GP2_STORAGE", "MEDIUM", "HIGH",
                monthly * 0.10,
                [f"storage_type={storage_type}", "gp3 offers higher baseline IOPS and 20% lower cost than gp2"],
                "Migrate to gp3 storage and explicitly set iops and throughput to match or exceed current gp2 performance.",
                optimized_replacement={"resource": block["name"], "text": _replace_attr(block["text"], "storage_type", '"gp3"')},
            ))

        # R6: Read replica with very low connection count: possibly unused
        if is_replica:
            conn_avg = _avg(connections)
            if conn_avg is not None and conn_avg < 5:
                findings.append(_finding(
                    "rds", block["name"], "RDS_R6_UNDERUSED_READ_REPLICA", "MEDIUM", "LOW",
                    monthly,
                    [f"replicate_source_db=set", f"database_connections_avg={round(conn_avg, 1)}"],
                    "Verify application read traffic is routed to this replica. Delete if unused after confirming no DR or reporting dependency.",
                ))

    return findings


# ── CloudWatch / CloudWatch-Alarm: RuleEngine-driven analyzers ───────────────

def _cw_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    tf_retention = _attr_int(block["text"], "retention_in_days")
    observed_retention = source.get("retention_in_days")
    stored_bytes = source.get("stored_bytes")
    return {
        "analyzable": True,
        "log_group_name": _attr(block["text"], "name"),
        "retention_in_days": tf_retention if tf_retention is not None else observed_retention,
        "retention_days_scenario_attr": _attr(block["text"], "retention_days") is not None,
        "stored_bytes": stored_bytes if stored_bytes is not None else _attr_int(block["text"], "stored_bytes"),
        "_block": block,
    }


def _cw_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    # The rule document contains a per-GB price, not a saving amount. Without
    # observed stored volume or a cost report, reporting that unit price as a
    # monthly saving is dimensionally incorrect.
    return 0.0


def _cw_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    block = facts.get("_block")
    if block is None:
        return None
    attr = "retention_days" if facts.get("retention_days_scenario_attr") else "retention_in_days"
    return {"resource": block["name"], "text": _replace_attr(block["text"], attr, 30)}


def _cwalarm_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    return {
        "analyzable": True,
        "resolution_seconds": _attr_int(block["text"], "resolution_seconds"),
        "actual_required_resolution_seconds": _attr_int(block["text"], "actual_required_resolution_seconds"),
        "metric_type": _attr(block["text"], "metric_type"),
        "evaluation_period_minutes": _attr_int(block["text"], "evaluation_period_minutes"),
        "_block": block,
    }


def _cwalarm_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return rule.get("cost", {}).get("savings_per_metric_per_month_usd", 0.60)


def _cwalarm_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    block = facts.get("_block")
    if block is None:
        return None
    return {"resource": block["name"], "text": _replace_attr(block["text"], "resolution_seconds", 60)}


_CW_ENGINE = RuleEngine(
    extractors={"cloudwatch.extract": _cw_extractor},
    savings_calculators={"cloudwatch.savings": _cw_savings},
    remediation_builders={"cloudwatch.remediation": _cw_remediation},
)

_CWALARM_ENGINE = RuleEngine(
    extractors={"cloudwatch-alarm.extract": _cwalarm_extractor},
    savings_calculators={"cloudwatch-alarm.savings": _cwalarm_savings},
    remediation_builders={"cloudwatch-alarm.remediation": _cwalarm_remediation},
)


# ── SQS ──────────────────────────────────────────────────────────────

def _sqs_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    wait = _attr_int(block["text"], "receive_wait_time_seconds")
    return {
        "analyzable": True,
        "receive_wait_time_seconds": wait if wait is not None else 0,
        "empty_receives_per_day": _attr_int(block["text"], "empty_receives_per_day") or 0,
        "_block": block,
    }


def _sqs_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0  # computed from savings_fraction by _findings_from_engine


def _sqs_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    block = facts.get("_block")
    if block is None:
        return None
    return {"resource": block["name"], "text": _replace_attr(block["text"], "receive_wait_time_seconds", 20)}


_SQS_ENGINE = RuleEngine(
    extractors={"sqs.extract": _sqs_extractor},
    savings_calculators={"sqs.savings": _sqs_savings},
    remediation_builders={"sqs.remediation": _sqs_remediation},
)


# ── Kinesis ───────────────────────────────────────────────────────────

def _kinesis_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    throttles = (
        bool(_attr_bool(block["text"], "write_throttles"))
        or bool(_attr_bool(block["text"], "read_throttles"))
        or bool(_attr_bool(block["text"], "has_throttles"))
    )
    return {
        "analyzable": True,
        "enhanced_fan_out": bool(_attr_bool(block["text"], "enhanced_fan_out")),
        "processing_interval_minutes": _attr_int(block["text"], "processing_interval_minutes") or 0,
        "has_throttles": throttles,
        "_block": block,
    }


def _kinesis_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0


def _kinesis_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    return None  # EFO disable requires consumer-level change, no simple attribute patch


_KINESIS_ENGINE = RuleEngine(
    extractors={"kinesis.extract": _kinesis_extractor},
    savings_calculators={"kinesis.savings": _kinesis_savings},
    remediation_builders={"kinesis.remediation": _kinesis_remediation},
)


# ── EBS ───────────────────────────────────────────────────────────────

def _ebs_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    all_blocks: list[Any] = source.get("all_blocks", [])
    text_lower = block["text"].lower()
    snapshot_ref = f"aws_ebs_snapshot.{block['name']}"
    has_deleted = "sourcevolumestatus" in text_lower and "deleted" in text_lower
    has_ami = any(
        b["type"] in {"aws_ami", "aws_launch_template"} and snapshot_ref in b["text"]
        for b in all_blocks
    )
    has_backup = any(
        b["type"] in {"aws_backup_plan", "aws_backup_selection", "aws_dlm_lifecycle_policy"}
        and block["name"] in b["text"]
        for b in all_blocks
    )
    return {
        "analyzable": True,
        "has_deleted_source_volume": has_deleted,
        "has_ami_reference": has_ami,
        "has_backup_reference": has_backup,
        "_block": block,
    }


def _ebs_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0


def _ebs_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    return None  # snapshot deletion has no Terraform replacement block


_EBS_ENGINE = RuleEngine(
    extractors={"ebs.extract": _ebs_extractor},
    savings_calculators={"ebs.savings": _ebs_savings},
    remediation_builders={"ebs.remediation": _ebs_remediation},
)


# ── NAT ───────────────────────────────────────────────────────────────

def _nat_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    return {
        "analyzable": True,
        "nat_gateway_present": True,
        "has_s3_endpoint": source.get("has_s3_endpoint", False),
        "has_dynamodb_endpoint": source.get("has_dynamodb_endpoint", False),
        "_block": block,
    }


def _nat_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0


def _nat_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    block = facts.get("_block")
    if block is None:
        return None
    return {
        "resource": block["name"],
        "action": "add_s3_gateway_endpoint",
        "append": 'resource "aws_vpc_endpoint" "s3" {\n  vpc_id       = aws_vpc.<vpc>.id\n  service_name = "com.amazonaws.<region>.s3"\n}',
    }


_NAT_ENGINE = RuleEngine(
    extractors={"nat.extract": _nat_extractor},
    savings_calculators={"nat.savings": _nat_savings},
    remediation_builders={"nat.remediation": _nat_remediation},
)


# ── TGW ───────────────────────────────────────────────────────────────

def _tgw_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    return {
        "analyzable": True,
        "attachment_count": source.get("attachment_count", 0),
        "has_peering": source.get("has_peering", False),
        "_block": block,
    }


def _tgw_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0


def _tgw_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    return None


_TGW_ENGINE = RuleEngine(
    extractors={"tgw.extract": _tgw_extractor},
    savings_calculators={"tgw.savings": _tgw_savings},
    remediation_builders={"tgw.remediation": _tgw_remediation},
)


# ── Organizations ─────────────────────────────────────────────────────

def _orgs_extractor(source: dict[str, Any]) -> dict[str, Any]:
    block = source["block"]
    cb = _attr_bool(block["text"], "consolidated_billing")
    spend = _attr_float(block["text"], "monthly_spend_usd") or 0.0
    return {
        "analyzable": True,
        "consolidated_billing": cb,
        "monthly_spend_usd": spend,
        "_block": block,
    }


def _orgs_savings(facts: dict[str, Any], rule: dict[str, Any]) -> float:
    return 0.0


def _orgs_remediation(facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None:
    return None


_ORGS_ENGINE = RuleEngine(
    extractors={"organizations.extract": _orgs_extractor},
    savings_calculators={"organizations.savings": _orgs_savings},
    remediation_builders={"organizations.remediation": _orgs_remediation},
)


_ENGINE_RULE_DOCS: dict[str, dict[str, Any]] = {}


def _get_rule_doc(domain: str, filename: str) -> dict[str, Any]:
    key = f"{domain}/{filename}"
    if key not in _ENGINE_RULE_DOCS:
        repo_root = Path(__file__).resolve().parents[1]
        _ENGINE_RULE_DOCS[key] = json.loads(
            (repo_root / ".claude" / "skills" / f"finops-{domain}" / "rules" / filename)
            .read_text(encoding="utf-8")
        )
    return _ENGINE_RULE_DOCS[key]


def _engine_pricing_metadata(
    domain: str,
    facts: dict[str, Any],
    savings: float,
    domain_monthly: float,
) -> tuple[str, str, str]:
    if savings > 0 and domain_monthly > 0:
        return "cost_report", "priced", "cost_report_available"
    if savings > 0:
        return "static_fallback_estimate", "priced", "static_rule_estimate"
    if domain == "cloudwatch":
        stored_bytes = facts.get("stored_bytes")
        if stored_bytes in (None, 0):
            return "unmeasured", "unmeasured", "stored_bytes_zero_or_missing"
        return "unmeasured", "unmeasured", "cloudwatch_storage_price_unavailable"
    return "unmeasured", "unmeasured", "quantity_or_price_unavailable"


def _findings_from_engine(
    domain: str,
    rule_doc: dict[str, Any],
    engine: RuleEngine,
    sources: list[dict[str, Any]],
    cost_summary: dict[str, Any],
    evidence_keys: frozenset[str],
    include_missing_evidence_keys: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Run evaluate_severity_rules per source; split domain cost across triggered sub-rules.

    Each source is a dict containing at least {"block": ResourceBlock} plus any
    cross-block context (e.g. has_s3_endpoint, attachment_count) the extractor needs.
    Per-source blockers suppress findings listed in their blocked_by list.
    If a fact named _savings_ratio is present it overrides the savings_fraction formula.
    """
    all_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for src in sources:
        src_results = engine.evaluate_severity_rules(rule_doc, src)
        src_blocked: set[str] = set()
        for sr in src_results:
            if sr["rule_type"] == "blocker":
                src_blocked.update(sr.get("blocked_by", []))
        for sr in src_results:
            if sr["rule_type"] != "finding":
                continue
            if sr["sub_rule_id"] in src_blocked:
                continue
            all_pairs.append((src, sr))
    if not all_pairs:
        return []

    domain_monthly = cost_summary.get(domain, {}).get("monthly_usd", 0.0)
    counts: dict[str, int] = {}
    for _, sr in all_pairs:
        counts[sr["sub_rule_id"]] = counts.get(sr["sub_rule_id"], 0) + 1

    findings = []
    for src, sr in all_pairs:
        block = src.get("block") or {}
        n = counts[sr["sub_rule_id"]]
        facts = sr["facts"]
        per_resource_ratio = facts.get("_savings_ratio")
        if domain_monthly > 0 and n > 0:
            if per_resource_ratio is not None:
                savings = round(domain_monthly * per_resource_ratio / n, 2)
            elif sr["savings_fraction"] > 0:
                savings = round(domain_monthly * sr["savings_fraction"] / n, 2)
            else:
                savings = sr["estimated_monthly_saving_usd"]
        else:
            savings = sr["estimated_monthly_saving_usd"]
        evidence = []
        for key, value in facts.items():
            if key not in evidence_keys:
                continue
            if value is None and key not in include_missing_evidence_keys:
                continue
            evidence.append(f"{key}={value if value is not None else 'missing'}")
        pricing_source, savings_status, savings_reason = _engine_pricing_metadata(
            domain, facts, float(savings or 0.0), float(domain_monthly or 0.0)
        )
        evidence.append(f"pricing_source={pricing_source}")
        evidence.append(f"savings_reason={savings_reason}")
        resource_name = block.get("name", "") if isinstance(block, dict) else ""
        findings.append(
            _add_savings_metadata(
                {
                    "domain": domain,
                    "resource": resource_name,
                    "rule_id": f"{rule_doc['rule_id']}:{sr['sub_rule_id']}",
                    "severity": sr["severity"],
                    "confidence": sr["confidence"],
                    "estimated_monthly_saving_usd": savings,
                    "pricing_source": pricing_source,
                    "evidence": evidence,
                    "recommendation": sr.get("recommendation") or sr.get("description", ""),
                    "optimized_replacement": sr.get("remediation_patch"),
                },
                savings_status=savings_status,
                savings_reason=savings_reason,
                display_name=str(facts.get("log_group_name") or resource_name),
            )
        )
    return findings


def _cloudwatch_observed_context(resources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    context_by_key: dict[str, dict[str, Any]] = {}
    for resource_name, record in resources.items():
        resource_type = str(record.get("resource_type") or record.get("type") or "")
        if _record_domain(record) != "cloudwatch" and resource_type != "aws_cloudwatch_log_group":
            continue
        configuration = record.get("configuration", {})
        if not isinstance(configuration, dict):
            configuration = {}
        context = {
            key: value
            for key, value in {
                "retention_in_days": configuration.get("retention_in_days"),
                "stored_bytes": configuration.get("stored_bytes"),
            }.items()
            if isinstance(value, (int, float))
        }
        if not context:
            continue
        keys = [
            resource_name,
            configuration.get("name"),
            record.get("resource_id"),
        ]
        for key in keys:
            if isinstance(key, str) and key:
                context_by_key[key] = context
    return context_by_key


def _analyze_cloudwatch(
    blocks: list[ResourceBlock],
    cost_summary: dict[str, Any],
    analysis_resources: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    groups = [b for b in blocks if b["type"] == "aws_cloudwatch_log_group"]
    observed = _cloudwatch_observed_context(analysis_resources or {})
    sources: list[dict[str, Any]] = []
    for block in groups:
        log_group_name = _attr(block["text"], "name")
        context = observed.get(block["name"]) or (observed.get(log_group_name) if log_group_name else {}) or {}
        sources.append({"block": block, **context})
    return _findings_from_engine(
        "cloudwatch",
        _get_rule_doc("cloudwatch", "missing_retention_policy.json"),
        _CW_ENGINE,
        sources,
        cost_summary,
        frozenset({"log_group_name", "retention_in_days", "retention_days_scenario_attr", "stored_bytes"}),
        frozenset({"retention_in_days"}),
    )


def _analyze_cloudwatch_alarm(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    alarms = [b for b in blocks if b["type"] == "aws_cloudwatch_metric_alarm"]
    return _findings_from_engine(
        "cloudwatch-alarm",
        _get_rule_doc("cloudwatch-alarm", "high_resolution_alarm.json"),
        _CWALARM_ENGINE,
        [{"block": b} for b in alarms],
        cost_summary,
        frozenset({"resolution_seconds", "actual_required_resolution_seconds", "metric_type", "evaluation_period_minutes"}),
    )


def _analyze_sqs(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    queues = [b for b in blocks if b["type"] == "aws_sqs_queue"]
    return _findings_from_engine(
        "sqs", _get_rule_doc("sqs", "short_polling_sqs.json"),
        _SQS_ENGINE, [{"block": b} for b in queues], cost_summary,
        frozenset({"receive_wait_time_seconds", "empty_receives_per_day"}),
    )


def _analyze_kinesis(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    streams = [b for b in blocks if b["type"] == "aws_kinesis_stream"]
    return _findings_from_engine(
        "kinesis", _get_rule_doc("kinesis", "efo_waste.json"),
        _KINESIS_ENGINE, [{"block": b} for b in streams], cost_summary,
        frozenset({"enhanced_fan_out", "processing_interval_minutes", "has_throttles"}),
    )


def _analyze_ecs(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    services = [block for block in blocks if block["type"] == "aws_ecs_service"]
    task_defs = {block["name"]: block for block in blocks if block["type"] == "aws_ecs_task_definition"}
    scaling_blocks = [
        block for block in blocks
        if block["type"] in {"aws_appautoscaling_target", "aws_appautoscaling_policy", "aws_appautoscaling_scheduled_action"}
    ]
    findings: list[dict[str, Any]] = []
    ecs_cost = _split_domain_cost(cost_summary, "ecs", len(services))

    for block in services:
        launch_type = (_attr(block["text"], "launch_type") or "FARGATE").upper()
        desired_count = _attr_int(block["text"], "desired_count") or 1
        service_name = _attr(block["text"], "name") or block["name"]

        task_def_block = task_defs.get(block["name"])
        task_cpu = _attr_int(task_def_block["text"], "cpu") if task_def_block else None

        service_scaling = "\n".join(
            sb["text"] for sb in scaling_blocks
            if block["name"] in sb["text"] or service_name in sb["text"]
        )
        has_scaling_target = "aws_appautoscaling_target" in service_scaling
        has_scaling_policy = "aws_appautoscaling_policy" in service_scaling

        record = _metric_record(metrics, block) or {}
        cpu = (
            _series(record.get("metrics", {}).get("cpu_utilization_pct", {}))
            or _series(record.get("metrics", {}).get("cpu_utilization", {}))
            or _series(record.get("metrics", {}).get("cpu_percent", {}))
        )
        errors = _series(record.get("metrics", {}).get("errors", {}))
        throttles = _series(record.get("metrics", {}).get("throttles", {}))
        is_problem = bool(record.get("is_problem"))
        cpu_avg = _avg(cpu)
        cpu_p95 = _pctl(cpu, 0.95)
        has_errors = bool(errors and sum(errors) > 0)
        has_throttles = bool(throttles and sum(throttles) > 0)

        # E1: Fargate task overprovisioned: low CPU with no error/throttle signal
        if launch_type == "FARGATE":
            if is_problem or (
                cpu_avg is not None
                and cpu_avg < 20
                and (cpu_p95 is None or cpu_p95 < 50)
                and not has_errors
                and not has_throttles
            ):
                findings.append(_finding(
                    "ecs", block["name"], "ECS_E1_FARGATE_RIGHTSIZE", "HIGH", "MEDIUM",
                    ecs_cost * 0.4,
                    [
                        f"cpu_avg_pct={round(cpu_avg, 1) if cpu_avg is not None else 'not_available'}",
                        f"cpu_p95_pct={round(cpu_p95, 1) if cpu_p95 is not None else 'not_available'}",
                        f"desired_count={desired_count}",
                        f"task_cpu={task_cpu}",
                    ],
                    "Select a valid smaller Fargate CPU/memory shape and canary while monitoring p95/p99 latency and errors.",
                ))

        # E2: EC2 launch type with low CPU and no capacity provider strategy
        elif launch_type == "EC2":
            has_capacity_provider = "capacity_provider_strategy" in block["text"]
            if cpu_avg is not None and cpu_avg < 15 and not has_capacity_provider and not has_errors:
                findings.append(_finding(
                    "ecs", block["name"], "ECS_E2_EC2_UNDERUTILIZED", "MEDIUM", "MEDIUM",
                    ecs_cost * 0.3,
                    [f"launch_type=EC2", f"cpu_avg_pct={round(cpu_avg, 1)}", "capacity_provider_strategy=not_set"],
                    "Add a Capacity Provider strategy or migrate to Fargate to reduce EC2 instance waste.",
                ))

        # E3: Multi-instance service with no autoscaling configured
        if desired_count >= 2 and not (has_scaling_target and has_scaling_policy):
            findings.append(_finding(
                "ecs", block["name"], "ECS_E3_MISSING_AUTOSCALING", "MEDIUM", "HIGH",
                ecs_cost * 0.2,
                [
                    f"desired_count={desired_count}",
                    f"autoscaling_target={has_scaling_target}",
                    f"autoscaling_policy={has_scaling_policy}",
                ],
                "Add Application Auto Scaling target and target-tracking policy (CPUUtilization or RequestCountPerTarget).",
            ))

    return findings


_ELASTICACHE_EOL_VERSIONS: dict[str, set[str]] = {
    "redis": {"2.6", "2.8", "3.2", "4.0", "5.0", "6.0"},
    "memcached": {"1.4", "1.5"},
}


def _elasticache_is_eol(engine: str, engine_version: str) -> bool:
    engine_lc = (engine or "").lower()
    major_minor = ".".join((engine_version or "").split(".")[:2])
    return major_minor in _ELASTICACHE_EOL_VERSIONS.get(engine_lc, set())


def _analyze_elasticache(blocks: list[ResourceBlock], metrics: dict[str, dict[str, Any]], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [block for block in blocks if block["type"] == "aws_elasticache_replication_group"]
    findings: list[dict[str, Any]] = []
    domain_monthly = _domain_cost(cost_summary, "elasticache")
    per_group = domain_monthly / max(len(groups), 1)

    for block in groups:
        count = _attr_int(block["text"], "num_cache_clusters") or 1
        node_type = _attr(block["text"], "node_type") or ""
        engine = _attr(block["text"], "engine") or "redis"
        engine_version = _attr(block["text"], "engine_version") or ""
        auto_failover = _attr_bool(block["text"], "automatic_failover_enabled")
        multi_az = _attr_bool(block["text"], "multi_az_enabled") or auto_failover
        env = (_tag_value(block["text"], "Environment") or "").lower()
        is_prod = env in {"prod", "production", "prd"}

        record = _metric_record(metrics, block) or {}
        hit_rate = _series(record.get("metrics", {}).get("cache_hit_rate_pct", {}))
        cpu = _series(record.get("metrics", {}).get("cpu_percent", {}))
        is_problem = bool(record.get("is_problem"))
        cpu_avg = _avg(cpu)
        hit_rate_min = min(hit_rate) if hit_rate else None

        # EC1: Too many replicas with demonstrably low load
        if count > 2:
            low_load = cpu_avg is not None and cpu_avg < 20
            if low_load or is_problem:
                replica_savings = per_group * (count - 2) / count
                findings.append(_finding(
                    "elasticache", block["name"], "ELASTICACHE_EC1_REDUCE_REPLICAS", "HIGH", "MEDIUM",
                    replica_savings,
                    [f"num_cache_clusters={count}", f"cpu_avg_pct={round(cpu_avg, 1) if cpu_avg is not None else 'not_available'}",
                     f"node_type={node_type}"],
                    "Reduce to 2 replicas only after confirming evictions=0, replication lag <100ms, and cache hit rate >95%.",
                ))

        # EC2: Node type overprovisioned: low CPU and high hit rate (no memory pressure)
        if (
            cpu_avg is not None and cpu_avg < 20
            and hit_rate_min is not None and hit_rate_min >= 95
            and not is_problem
        ):
            findings.append(_finding(
                "elasticache", block["name"], "ELASTICACHE_EC2_DOWNSIZE_NODE", "HIGH", "MEDIUM",
                per_group * 0.35,
                [f"cpu_avg_pct={round(cpu_avg, 1)}", f"cache_hit_rate_min_pct={round(hit_rate_min, 1)}",
                 f"node_type={node_type}"],
                "Test the next smaller node type in a non-production replica; promote after confirming evictions=0 and hit rate stable.",
            ))

        # EC3: No Reserved Node for steady-state cache with meaningful spend
        if per_group > 200:
            is_steady = cpu_avg is None or cpu_avg > 5
            if is_steady:
                findings.append(_finding(
                    "elasticache", block["name"], "ELASTICACHE_EC3_NO_RESERVED_NODE", "LOW", "MEDIUM",
                    per_group * 0.30,
                    [f"node_type={node_type}", f"avg_monthly_spend_usd={round(per_group, 2)}",
                     "reserved_node_coverage=not_evidenced_in_terraform"],
                    "Evaluate 1-year Reserved Node purchase (~30% savings) after confirming stable node type and count for 60+ days.",
                ))

        # EC4: Single-node production cluster with no HA (informational)
        if count == 1 and not multi_az and is_prod:
            findings.append(_finding(
                "elasticache", block["name"], "ELASTICACHE_EC4_NO_HA", "INFO", "HIGH",
                0.0,
                [f"num_cache_clusters={count}", "automatic_failover_enabled=false", f"environment={env}"],
                "Add at least one replica and enable automatic_failover_enabled for production clusters to support failover.",
            ))

        # EC5: Engine version at or past end-of-life
        if _elasticache_is_eol(engine, engine_version):
            findings.append(_finding(
                "elasticache", block["name"], "ELASTICACHE_EC5_ENGINE_UPGRADE", "MEDIUM", "HIGH",
                0.0,
                [f"engine={engine}", f"engine_version={engine_version}", "version_status=EOL"],
                f"Upgrade {engine} to the latest supported version. Test with a replica cluster before promoting to production.",
            ))

    return findings


def _analyze_nat(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    gateways = [b for b in blocks if b["type"] == "aws_nat_gateway"]
    endpoints = [b for b in blocks if b["type"] == "aws_vpc_endpoint"]
    has_s3 = any("s3" in b["text"].lower() for b in endpoints)
    has_dynamodb = any("dynamodb" in b["text"].lower() for b in endpoints)
    sources = [{"block": g, "has_s3_endpoint": has_s3, "has_dynamodb_endpoint": has_dynamodb} for g in gateways]
    return _findings_from_engine(
        "nat", _get_rule_doc("nat", "s3_nat_bypass.json"),
        _NAT_ENGINE, sources, cost_summary,
        frozenset({"nat_gateway_present", "has_s3_endpoint"}),
    )


def _analyze_tgw(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    gateways = [b for b in blocks if b["type"] == "aws_ec2_transit_gateway"]
    attachments = [b for b in blocks if b["type"] == "aws_ec2_transit_gateway_vpc_attachment"]
    peering = [b for b in blocks if b["type"] == "aws_vpc_peering_connection"]
    if not gateways:
        return []
    sources = [{"block": gateways[0], "attachment_count": len(attachments), "has_peering": bool(peering)}]
    return _findings_from_engine(
        "tgw", _get_rule_doc("tgw", "tgw_rightsizing.json"),
        _TGW_ENGINE, sources, cost_summary,
        frozenset({"attachment_count", "has_peering"}),
    )


def _analyze_organizations(blocks: list[ResourceBlock], cost_summary: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = [b for b in blocks if b["type"] == "aws_account"]
    return _findings_from_engine(
        "organizations", _get_rule_doc("organizations", "consolidated_billing.json"),
        _ORGS_ENGINE, [{"block": b} for b in accounts], cost_summary,
        frozenset({"consolidated_billing", "monthly_spend_usd"}),
    )


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


def _analyze_single_domain(domain: str, evidence: dict[str, Any], work_dir: Path | None = None) -> dict[str, Any]:
    tf_path = evidence.get("terraform")
    tf_text = _read_text(Path(tf_path)) if tf_path else ""
    blocks = _resource_blocks(tf_text) if tf_path else []
    metrics = _load_metric_resources(evidence.get("metrics"))
    analysis_resources, analysis_metadata = _load_analysis_resources(evidence)
    cost_summary = _load_cost_summary(evidence.get("cost_report"))
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    skill_request: dict[str, Any] | None = None
    pricing_request: dict[str, Any] | None = None

    if domain == "lambda":
        pricing_models, pricing_warnings = _load_pricing_model_with_warnings(work_dir, "lambda")
        warnings.extend(pricing_warnings)
        lambda_findings, lambda_warnings, lambda_pricing_request = _analyze_lambda(
            blocks, metrics, cost_summary, analysis_metadata, pricing_models, work_dir, tf_text
        )
        findings.extend(lambda_findings)
        warnings.extend(lambda_warnings)
        pricing_request = lambda_pricing_request
    elif domain == "s3":
        pricing_models, pricing_warnings = _load_pricing_model_with_warnings(work_dir, "s3")
        warnings.extend(pricing_warnings)
        s3_findings, s3_pricing_request = _analyze_s3(
            blocks, metrics, cost_summary, analysis_resources, analysis_metadata, pricing_models, work_dir, tf_text
        )
        findings.extend(s3_findings)
        pricing_request = s3_pricing_request
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
    elif domain == "cloudwatch":
        findings.extend(_analyze_cloudwatch(blocks, cost_summary, analysis_resources))
    elif domain == "cloudwatch-alarm":
        findings.extend(_analyze_cloudwatch_alarm(blocks, cost_summary))
    elif domain == "sqs":
        findings.extend(_analyze_sqs(blocks, cost_summary))
    elif domain == "kinesis":
        findings.extend(_analyze_kinesis(blocks, cost_summary))
    elif domain == "nat":
        findings.extend(_analyze_nat(blocks, cost_summary))
    elif domain == "tgw":
        findings.extend(_analyze_tgw(blocks, cost_summary))
    elif domain == "organizations":
        findings.extend(_analyze_organizations(blocks, cost_summary))
    elif domain in _COMPLEX_DOMAINS:
        pricing_models, pricing_warnings = _load_pricing_model_with_warnings(work_dir, domain)
        warnings.extend(pricing_warnings)
        pricing_context, pricing_request = _complex_pricing_context_and_request(
            domain=domain,
            work_dir=work_dir,
            blocks=blocks,
            analysis_metadata=analysis_metadata,
            pricing_models=pricing_models,
            tf_text=tf_text,
        )
        skill_findings, skill_warnings = (
            _load_skill_analysis_with_warnings(work_dir, domain)
            if work_dir
            else ([], [])
        )
        warnings.extend(skill_warnings)
        if skill_findings:
            if domain == "rds":
                skill_findings = _enrich_rds_skill_findings(
                    skill_findings,
                    blocks,
                    pricing_context,
                    analysis_metadata,
                    tf_text,
                )
            findings.extend(skill_findings)
            if _skill_findings_need_pricing_reanalysis(skill_findings, pricing_context):
                skill_request = _build_complex_skill_request(
                    domain=domain,
                    evidence=evidence,
                    work_dir=work_dir,
                    blocks=blocks,
                    metrics=metrics,
                    analysis_resources=analysis_resources,
                    analysis_metadata=analysis_metadata,
                    cost_summary=cost_summary,
                    pricing_context=pricing_context,
                )
                skill_request["status"] = "needs_skill_reanalysis"
                skill_request["reason"] = (
                    "A public pricing model is available, but existing Skill findings "
                    "still use static_fallback_estimate pricing."
                )
        else:
            warnings.append(
                f"Complex domain '{domain}' requires Skill analysis output at result/.machine/{domain}_skill_analysis.json."
            )
            skill_request = _build_complex_skill_request(
                domain=domain,
                evidence=evidence,
                work_dir=work_dir,
                blocks=blocks,
                metrics=metrics,
                analysis_resources=analysis_resources,
                analysis_metadata=analysis_metadata,
                cost_summary=cost_summary,
                pricing_context=pricing_context,
            )
    else:
        warnings.append(
            f"No built-in graph analyzer yet for domain '{domain}'; load existing findings or service skill output."
        )

    for finding in findings:
        finding.setdefault("analysis_source", "langgraph")
        finding.setdefault("review_status", "machine_analyzed")

    return {
        "domain": domain,
        "findings": findings,
        "warnings": warnings,
        **({"skill_request": skill_request} if skill_request else {}),
        **({"pricing_request": pricing_request} if pricing_request else {}),
    }


def _registry_handler(domain: str):
    def analyze(context: dict[str, Any]) -> list[dict[str, Any]]:
        work_dir = Path(context["work_dir"]) if context.get("work_dir") else None
        return _analyze_single_domain(domain, context["evidence"], work_dir)["findings"]

    return analyze


def _build_analyzer_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    repo_root = Path(__file__).resolve().parents[1]
    domains = (
        "lambda", "s3", "dynamodb", "bedrock", "sagemaker", "ec2",
        "ebs", "elb", "rds", "cloudwatch", "cloudwatch-alarm", "sqs",
        "kinesis", "ecs", "elasticache", "nat", "tgw", "organizations",
    )
    handler_names = {
        f"{domain}.{kind}"
        for domain in domains
        for kind in ("extract", "savings", "remediation")
    }
    for domain in domains:
        rule_dir = repo_root / ".claude" / "skills" / f"finops-{domain}" / "rules"
        rule_files = tuple(str(path) for path in sorted(rule_dir.glob("*.json")))
        for rule_file in rule_files:
            document = load_rule(rule_file, handler_names)
            if document["domain"] != domain:
                raise RuleValidationError(f"Rule domain mismatch in {rule_file}")
        registry.register(
            AnalyzerRegistration(
                domain=domain,
                version="2.0.0",
                analyzer=_registry_handler(domain),
                rule_files=rule_files,
            )
        )
    return registry


ANALYZER_REGISTRY = _build_analyzer_registry()

