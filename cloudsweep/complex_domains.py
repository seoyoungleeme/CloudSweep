"""Skill-owned analysis helpers for contextual CloudSweep domains."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_COMPLEX_DOMAINS = frozenset({"rds", "elb", "ecs", "elasticache"})
_SKILL_ANALYZED_STATUS = "skill_analyzed"

_VALID_SEVERITIES = {"HIGH", "MEDIUM", "LOW", "INFO"}
_VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
_VALID_PRICING_SOURCES = {
    "cost_report",
    "aws_public_pricing_model",
    "static_fallback_estimate",
    "reasonable_estimate",
    "unmeasured",
}
_VALID_SAVINGS_STATUS = {"priced", "reasonable_estimate", "unmeasured"}


def _pricing_confidence(pricing_source: str | None) -> str:
    if pricing_source == "cost_report":
        return "HIGH"
    if pricing_source == "aws_public_pricing_model":
        return "MEDIUM"
    return "LOW"


def _savings_status(pricing_source: str | None) -> str:
    if pricing_source == "reasonable_estimate":
        return "reasonable_estimate"
    if pricing_source == "unmeasured":
        return "unmeasured"
    return "priced"


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def _normalize_skill_finding(domain: str, raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    rule_id = str(raw.get("rule_id") or "").strip()
    resource = str(raw.get("resource") or "").strip()
    if not rule_id or not resource:
        return None, [f"Skill finding missing rule_id/resource for domain '{domain}'"]

    severity = str(raw.get("severity") or "LOW").upper()
    if severity not in _VALID_SEVERITIES:
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} had invalid severity; defaulted to LOW")
        severity = "LOW"

    confidence = str(raw.get("confidence") or "LOW").upper()
    if confidence not in _VALID_CONFIDENCE:
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} had invalid confidence; defaulted to LOW")
        confidence = "LOW"

    try:
        savings = float(raw.get("estimated_monthly_saving_usd", 0.0) or 0.0)
        if savings < 0:
            raise ValueError
    except (TypeError, ValueError):
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} had invalid savings; defaulted to $0")
        savings = 0.0

    pricing_source = raw.get("pricing_source")
    if pricing_source is not None:
        pricing_source = str(pricing_source).strip()
        if pricing_source not in _VALID_PRICING_SOURCES:
            warnings.append(
                f"Skill finding {domain}/{rule_id}/{resource} had invalid pricing_source; defaulted to unmeasured"
            )
            pricing_source = "unmeasured"

    pricing_confidence = str(raw.get("pricing_confidence") or _pricing_confidence(pricing_source)).upper()
    if pricing_confidence not in _VALID_CONFIDENCE:
        warnings.append(
            f"Skill finding {domain}/{rule_id}/{resource} had invalid pricing_confidence; defaulted to LOW"
        )
        pricing_confidence = "LOW"

    savings_status = str(raw.get("savings_status") or _savings_status(pricing_source)).strip()
    if savings_status not in _VALID_SAVINGS_STATUS:
        warnings.append(
            f"Skill finding {domain}/{rule_id}/{resource} had invalid savings_status; defaulted to unmeasured"
        )
        savings_status = "unmeasured"

    savings_reason = str(raw.get("savings_reason") or "").strip()
    display_name = str(raw.get("display_name") or "").strip()

    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} evidence was not a list")
    evidence = [str(item) for item in evidence if item]
    if not evidence:
        evidence = ["Not available in the provided data; verify in the real environment."]
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} had no evidence; inserted missing-evidence statement")

    recommendation = str(raw.get("recommendation") or "").strip()
    if not recommendation:
        recommendation = "Not available in the provided data; verify in the real environment."
        warnings.append(f"Skill finding {domain}/{rule_id}/{resource} had no recommendation; inserted missing-evidence recommendation")

    finding = {
        "domain": domain,
        "resource": resource,
        "rule_id": rule_id,
        "severity": severity,
        "confidence": confidence,
        "estimated_monthly_saving_usd": round(savings, 2),
        "evidence": evidence,
        "recommendation": recommendation,
        "analysis_source": "claude_skill",
        "review_status": _SKILL_ANALYZED_STATUS,
    }
    if pricing_source is not None:
        finding["pricing_source"] = pricing_source
    finding["pricing_confidence"] = pricing_confidence
    finding["savings_status"] = savings_status
    if savings_reason:
        finding["savings_reason"] = savings_reason
    if display_name:
        finding["display_name"] = display_name
    return finding, warnings


def _load_skill_analysis_with_warnings(work_dir: Path, domain: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Load authoritative Claude Skill findings for a complex domain."""
    path = work_dir / "result" / ".machine" / f"{domain}_skill_analysis.json"
    if not path.exists():
        return [], []
    try:
        data = _load_json(path)
    except Exception as exc:
        return [], [f"Could not read {path.name}: {type(exc).__name__}: {exc}"]
    if not isinstance(data, dict) or data.get("domain") != domain:
        return [], [f"Ignored {path.name}: schema domain did not match '{domain}'"]
    if data.get("schema_version") != "1.0":
        return [], [f"Ignored {path.name}: schema_version must be '1.0'"]
    if "findings" not in data and isinstance(data.get("decisions"), list):
        return [], [f"Ignored {path.name}: legacy decisions schema ignored; regenerate findings schema"]
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        return [], [f"Ignored {path.name}: findings must be a list"]

    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            warnings.append(f"Ignored non-object Skill finding in {path.name}")
            continue
        item, item_warnings = _normalize_skill_finding(domain, finding)
        warnings.extend(item_warnings)
        if item:
            normalized.append(item)
    return normalized, warnings


def _load_skill_analysis(work_dir: Path, domain: str) -> list[dict[str, Any]]:
    findings, _ = _load_skill_analysis_with_warnings(work_dir, domain)
    return findings
