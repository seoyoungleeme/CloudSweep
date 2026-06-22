"""Deterministic normalization for external evidence contracts."""
from __future__ import annotations

import re
from typing import Any


# Explicit mappings cover AWS names that differ from CloudSweep's internal
# contract. Legacy aliases keep evidence from older collector versions usable.
METRIC_NAME_ALIASES: dict[str, str] = {
    "CPUUtilization": "cpu_utilization",
    "cpuutilization": "cpu_utilization",
    "DatabaseConnections": "database_connections",
    "MaxMemoryUsed": "memory_used_mb",
    "MemoryUsed": "memory_used_mb",
}

ENVIRONMENT_ALIASES: dict[str, str] = {
    "dev": "dev",
    "development": "dev",
    "prod": "prod",
    "prd": "prod",
    "production": "prod",
    "stage": "staging",
    "staging": "staging",
    "test": "test",
    "testing": "test",
    "sandbox": "sandbox",
    "nonprod": "nonprod",
    "non-production": "nonprod",
}


def normalize_metric_name(name: Any) -> str:
    """Return CloudSweep's stable metric key without inference or API calls."""
    raw = str(name or "").strip()
    if raw in METRIC_NAME_ALIASES:
        return METRIC_NAME_ALIASES[raw]
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", raw)
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass)
    snake_case = snake_case.replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", snake_case).strip("_").lower()


def normalize_environment(value: Any) -> str | None:
    """Normalize known aliases while leaving unknown environment values intact."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lowered = raw.lower()
    return ENVIRONMENT_ALIASES.get(lowered, lowered)


def environment_fields(tags: dict[str, str]) -> dict[str, str]:
    """Build auditable raw and normalized environment fields from tags."""
    raw = next(
        (value for key, value in tags.items() if key.strip().lower() in {"environment", "env"}),
        None,
    )
    normalized = normalize_environment(raw)
    if raw is None or normalized is None:
        return {}
    return {"environment_raw": str(raw), "environment_normalized": normalized}


__all__ = [
    "ENVIRONMENT_ALIASES",
    "METRIC_NAME_ALIASES",
    "environment_fields",
    "normalize_environment",
    "normalize_metric_name",
]
