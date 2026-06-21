"""Validated rule evaluation and analyzer registration for CloudSweep."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


RULE_SCHEMA_VERSION = "2.0"
SUPPORTED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "exists"}


class RuleValidationError(ValueError):
    pass


def stable_id(*parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"cs-{digest}"


def _fact_value(facts: dict[str, Any], dotted: str) -> Any:
    current: Any = facts
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def evaluate_predicate(predicate: dict[str, Any], facts: dict[str, Any], thresholds: dict[str, Any] | None = None) -> bool:
    thresholds = thresholds or {}
    if "all" in predicate:
        return all(evaluate_predicate(item, facts, thresholds) for item in predicate["all"])
    if "any" in predicate:
        return any(evaluate_predicate(item, facts, thresholds) for item in predicate["any"])
    if "not" in predicate:
        return not evaluate_predicate(predicate["not"], facts, thresholds)

    fact_name = predicate.get("fact")
    op = predicate.get("op")
    if not isinstance(fact_name, str) or op not in SUPPORTED_OPERATORS:
        raise RuleValidationError(f"Invalid predicate leaf: {predicate}")
    left = _fact_value(facts, fact_name)
    if op == "exists":
        return left is not None
    right = thresholds.get(predicate["threshold"]) if "threshold" in predicate else predicate.get("value")
    if left is None or right is None:
        return False
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "in":
        return left in right
    raise RuleValidationError(f"Unsupported predicate operator: {op}")


def _validate_predicate(predicate: Any, facts: set[str], thresholds: set[str]) -> None:
    if not isinstance(predicate, dict):
        raise RuleValidationError("predicate must be an object")
    branches = [key for key in ("all", "any", "not") if key in predicate]
    if branches:
        if len(branches) != 1:
            raise RuleValidationError("predicate must contain exactly one boolean operator")
        value = predicate[branches[0]]
        children = [value] if branches[0] == "not" else value
        if not isinstance(children, list) or not children:
            raise RuleValidationError(f"{branches[0]} predicate must not be empty")
        for child in children:
            _validate_predicate(child, facts, thresholds)
        return
    fact = predicate.get("fact")
    op = predicate.get("op")
    if fact not in facts:
        raise RuleValidationError(f"Unknown fact '{fact}'")
    if op not in SUPPORTED_OPERATORS:
        raise RuleValidationError(f"Unknown operator '{op}'")
    if "threshold" in predicate and predicate["threshold"] not in thresholds:
        raise RuleValidationError(f"Unknown threshold '{predicate['threshold']}'")
    if op != "exists" and "value" not in predicate and "threshold" not in predicate:
        raise RuleValidationError("predicate leaf requires value or threshold")


def validate_rule_document(document: dict[str, Any], handler_names: set[str] | None = None) -> None:
    required = {"schema_version", "rule_id", "domain", "version", "facts", "predicate", "outcome", "handlers"}
    missing = sorted(required - document.keys())
    if missing:
        raise RuleValidationError(f"Missing rule fields: {', '.join(missing)}")
    if document["schema_version"] != RULE_SCHEMA_VERSION:
        raise RuleValidationError(f"Unsupported rule schema version: {document['schema_version']}")
    if not isinstance(document["facts"], dict):
        raise RuleValidationError("facts must be an object")
    _validate_predicate(document["predicate"], set(document["facts"]), set(document.get("thresholds", {})))
    handlers = document["handlers"]
    for key in ("extractor", "savings", "remediation"):
        if not isinstance(handlers.get(key), str) or not handlers[key]:
            raise RuleValidationError(f"Missing handler '{key}'")
        if handler_names is not None and handlers[key] not in handler_names:
            raise RuleValidationError(f"Unknown handler '{handlers[key]}'")


def load_rule(path: str | Path, handler_names: set[str] | None = None) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_rule_document(document, handler_names)
    return document


@dataclass(frozen=True)
class AnalyzerRegistration:
    domain: str
    version: str
    analyzer: Callable[[dict[str, Any]], list[dict[str, Any]]]
    rule_files: tuple[str, ...] = ()


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._items: dict[str, AnalyzerRegistration] = {}

    def register(self, registration: AnalyzerRegistration) -> None:
        if registration.domain in self._items:
            raise RuleValidationError(f"Analyzer already registered for domain '{registration.domain}'")
        self._items[registration.domain] = registration

    def get(self, domain: str) -> AnalyzerRegistration:
        if domain not in self._items:
            raise RuleValidationError(f"No analyzer registered for domain '{domain}'")
        return self._items[domain]

    def domains(self) -> tuple[str, ...]:
        return tuple(self._items)

    def coverage(self, detected: list[str]) -> list[dict[str, str]]:
        return [
            {
                "domain": domain,
                "status": "implemented" if domain in self._items else "unsupported",
                "analyzer_version": self._items[domain].version if domain in self._items else "",
            }
            for domain in detected
        ]
