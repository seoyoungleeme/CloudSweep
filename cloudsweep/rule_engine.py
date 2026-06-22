"""Validated rule evaluation and analyzer registration for CloudSweep."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


RULE_SCHEMA_VERSION = "2.0"
SUPPORTED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "exists"}

# Rule classification types (severity_rules[].rule_type)
RULE_TYPES: frozenset[str] = frozenset({"finding", "blocker", "review"})

# What to do when required facts are absent (severity_rules[].missing_evidence_policy)
# skip             — omit the sub-rule result entirely
# report_unknown   — emit result with confidence=LOW and missing_evidence=True
# assume_triggered — treat as triggered (safe default for blockers)
MISSING_EVIDENCE_POLICIES: frozenset[str] = frozenset({"skip", "report_unknown", "assume_triggered"})


class RuleValidationError(ValueError):
    pass


class FactExtractor(Protocol):
    def __call__(self, source: dict[str, Any]) -> dict[str, Any]: ...


class SavingsCalculator(Protocol):
    def __call__(self, facts: dict[str, Any], rule: dict[str, Any]) -> float: ...


class RemediationPatchBuilder(Protocol):
    def __call__(self, facts: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any] | None: ...


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

    # Validate severity_rules entries that have structured predicates
    known_facts = set(document["facts"])
    known_thresholds = set(document.get("thresholds", {}))
    for sub_rule in document.get("severity_rules", []):
        if not isinstance(sub_rule, dict):
            raise RuleValidationError("Each severity_rules entry must be an object")
        if "id" not in sub_rule or "name" not in sub_rule:
            raise RuleValidationError("severity_rules entry missing required 'id' or 'name'")
        if "rule_type" in sub_rule and sub_rule["rule_type"] not in RULE_TYPES:
            raise RuleValidationError(
                f"Invalid rule_type '{sub_rule['rule_type']}' in severity_rule '{sub_rule['id']}'. "
                f"Must be one of {sorted(RULE_TYPES)}"
            )
        if "missing_evidence_policy" in sub_rule and sub_rule["missing_evidence_policy"] not in MISSING_EVIDENCE_POLICIES:
            raise RuleValidationError(
                f"Invalid missing_evidence_policy '{sub_rule['missing_evidence_policy']}' "
                f"in severity_rule '{sub_rule['id']}'"
            )
        if "predicate" in sub_rule:
            _validate_predicate(sub_rule["predicate"], known_facts, known_thresholds)


def load_rule(path: str | Path, handler_names: set[str] | None = None) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_rule_document(document, handler_names)
    return document


def _evaluate_single_severity_rule(
    rule: dict[str, Any],
    sub_rule: dict[str, Any],
    facts: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any] | None:
    """Evaluate one severity_rules entry against extracted facts.

    Returns None when the rule does not trigger.
    Returns a partial result dict (without savings/remediation) when triggered.

    New-format sub-rules have a structured `predicate` field.
    Legacy sub-rules have only a string `condition` field and cannot be
    evaluated programmatically — their behaviour is governed by
    `missing_evidence_policy`.
    """
    rule_type = sub_rule.get("rule_type", "finding")
    missing_policy = sub_rule.get("missing_evidence_policy", "skip")

    if "predicate" in sub_rule:
        triggered = evaluate_predicate(sub_rule["predicate"], facts, thresholds)
        missing_evidence = False
    else:
        # Legacy string condition — cannot evaluate yet
        missing_evidence = True
        if missing_policy == "assume_triggered":
            triggered = True
        elif missing_policy == "report_unknown":
            triggered = True
        else:
            return None  # skip (default for legacy rules)

    if not triggered:
        return None

    confidence = sub_rule.get("confidence", "MEDIUM")
    if missing_evidence:
        confidence = "LOW"

    result: dict[str, Any] = {
        "sub_rule_id": sub_rule["id"],
        "sub_rule_name": sub_rule.get("name", ""),
        "rule_type": rule_type,
        "severity": sub_rule.get("severity", "MEDIUM"),
        "action": sub_rule.get("action", ""),
        "confidence": confidence,
        "description": sub_rule.get("description", ""),
        "recommendation": sub_rule.get("recommendation", ""),
        "savings_fraction": float(sub_rule.get("savings_fraction", 0.0)),
        "missing_evidence": missing_evidence,
    }

    if rule_type == "blocker":
        result["blocked_by"] = list(sub_rule.get("blocked_by", []))
        result["review_requirements"] = list(sub_rule.get("review_requirements", []))
    elif rule_type == "review":
        result["review_requirements"] = list(sub_rule.get("review_requirements", []))

    return result


class RuleEngine:
    """Evaluate v2 rules through named, startup-validated handlers."""

    def __init__(
        self,
        extractors: dict[str, FactExtractor],
        savings_calculators: dict[str, SavingsCalculator],
        remediation_builders: dict[str, RemediationPatchBuilder],
    ) -> None:
        self.extractors = extractors
        self.savings_calculators = savings_calculators
        self.remediation_builders = remediation_builders

    @property
    def handler_names(self) -> set[str]:
        return set(self.extractors) | set(self.savings_calculators) | set(self.remediation_builders)

    def validate(self, rule: dict[str, Any]) -> None:
        validate_rule_document(rule, self.handler_names)
        handlers = rule["handlers"]
        if handlers["extractor"] not in self.extractors:
            raise RuleValidationError(f"Unknown extractor '{handlers['extractor']}'")
        if handlers["savings"] not in self.savings_calculators:
            raise RuleValidationError(f"Unknown savings handler '{handlers['savings']}'")
        if handlers["remediation"] not in self.remediation_builders:
            raise RuleValidationError(f"Unknown remediation handler '{handlers['remediation']}'")

    def evaluate(self, rule: dict[str, Any], source: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate the top-level rule predicate (gate check). Returns None if not triggered."""
        self.validate(rule)
        handlers = rule["handlers"]
        facts = self.extractors[handlers["extractor"]](source)
        if not evaluate_predicate(rule["predicate"], facts, rule.get("thresholds")):
            return None
        return {
            "rule_id": rule["rule_id"],
            "domain": rule["domain"],
            "rule_version": rule["version"],
            "facts": facts,
            "outcome": dict(rule["outcome"]),
            "estimated_monthly_saving_usd": round(
                float(self.savings_calculators[handlers["savings"]](facts, rule)), 2
            ),
            "remediation_patch": self.remediation_builders[handlers["remediation"]](facts, rule),
        }

    def evaluate_severity_rules(
        self,
        rule: dict[str, Any],
        source: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluate all severity_rules entries in a rule document.

        Returns a flat list of triggered sub-rule results. Each result contains:
        - sub_rule_id, sub_rule_name, rule_type, severity, action, confidence
        - rule_id, domain, rule_version (from the parent document)
        - facts (full extracted fact dict)
        - estimated_monthly_saving_usd, remediation_patch (findings only)
        - blocked_by, review_requirements (blockers and reviews)
        - missing_evidence (True when evaluated under missing_evidence_policy)

        Only sub-rules with a structured `predicate` field are fully evaluated.
        Legacy sub-rules with a string `condition` are handled per their
        `missing_evidence_policy` (default: skip).
        """
        self.validate(rule)
        handlers = rule["handlers"]
        facts = self.extractors[handlers["extractor"]](source)
        thresholds = rule.get("thresholds", {})

        results: list[dict[str, Any]] = []
        for sub_rule in rule.get("severity_rules", []):
            sub_result = _evaluate_single_severity_rule(rule, sub_rule, facts, thresholds)
            if sub_result is None:
                continue

            # Attach parent-document context
            sub_result["rule_id"] = rule["rule_id"]
            sub_result["domain"] = rule["domain"]
            sub_result["rule_version"] = rule["version"]
            sub_result["facts"] = facts

            # Savings and remediation only for findings
            if sub_result["rule_type"] == "finding":
                # Pass savings_fraction via facts so handlers can read it
                enriched = {**facts, "_sub_rule_id": sub_rule["id"], "_savings_fraction": sub_result["savings_fraction"]}
                sub_result["estimated_monthly_saving_usd"] = round(
                    float(self.savings_calculators[handlers["savings"]](enriched, rule)), 2
                )
                sub_result["remediation_patch"] = self.remediation_builders[handlers["remediation"]](enriched, rule)
            else:
                sub_result["estimated_monthly_saving_usd"] = 0.0
                sub_result["remediation_patch"] = None

            results.append(sub_result)

        return results


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
