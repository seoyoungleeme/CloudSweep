"""AI review and report-polish request/response helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AI_REVIEW_RESPONSE = "ai_review.json"
REPORT_POLISH_RESPONSE = "report_polish.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))


def _compact_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": finding.get("finding_id"),
        "domain": finding.get("domain"),
        "resource": finding.get("resource"),
        "display_name": finding.get("display_name"),
        "rule_id": finding.get("rule_id"),
        "severity": finding.get("severity"),
        "confidence": finding.get("confidence"),
        "pricing_confidence": finding.get("pricing_confidence"),
        "savings_status": finding.get("savings_status"),
        "savings_reason": finding.get("savings_reason"),
        "pricing_source": finding.get("pricing_source"),
        "estimated_monthly_saving_usd": finding.get("estimated_monthly_saving_usd", 0.0),
        "evidence": finding.get("evidence", []),
        "recommendation": finding.get("recommendation", ""),
        "cross_domain_refs": finding.get("cross_domain_refs", []),
    }


def _require_run_id(data: dict[str, Any], run_id: str | None, filename: str) -> list[str]:
    if data.get("schema_version") != "1.0":
        return [f"Ignored {filename}: schema_version must be '1.0'"]
    if run_id and data.get("run_id") != run_id:
        return [f"Ignored {filename}: run_id did not match current run"]
    return []


def build_ai_review_request(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "cloudsweep_ai_review_request",
        "run_id": state.get("run_id"),
        "scenario": Path(state.get("work_dir", "")).name,
        "instructions": [
            "Review machine findings for missed candidates, overreach, weak evidence, and cross-domain hypotheses.",
            "Do not change estimated_monthly_saving_usd, pricing_source, Terraform patches, or finding IDs.",
            "Use observed only with fact_ids; otherwise mark statements as hypothesis.",
            "Write result/.machine/ai_review.json using schema_version=1.0 and the same run_id.",
        ],
        "findings": [_compact_finding(finding) for finding in state.get("findings", [])],
        "warnings": state.get("warnings", []),
        "dependency_facts": state.get("dependency_facts", []),
        "cross_domain_notes": state.get("cross_domain_notes", []),
        "cross_domain_hypotheses": state.get("cross_domain_hypotheses", []),
    }


def load_ai_review(result_dir: Path, run_id: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    path = Path(result_dir) / ".machine" / AI_REVIEW_RESPONSE
    if not path.exists():
        return None, []
    try:
        data = _read_json(path)
    except Exception as exc:
        return None, [f"Could not read {AI_REVIEW_RESPONSE}: {type(exc).__name__}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"Ignored {AI_REVIEW_RESPONSE}: expected object"]
    warnings = _require_run_id(data, run_id, AI_REVIEW_RESPONSE)
    if warnings:
        return None, warnings
    return data, []


def build_report_polish_request(state: dict[str, Any]) -> dict[str, Any]:
    ai_review = state.get("ai_review") or {}
    return {
        "schema_version": "1.0",
        "kind": "cloudsweep_report_polish_request",
        "run_id": state.get("run_id"),
        "scenario": Path(state.get("work_dir", "")).name,
        "instructions": [
            "Write concise executive prose for the single final finops_report.md.",
            "Do not alter findings, savings, statuses, pricing sources, or remediation patches.",
            "Preserve evidence-backed savings and reasonable_estimate upside as separate numbers.",
            "Write result/.machine/report_polish.json using schema_version=1.0 and the same run_id.",
        ],
        "machine_summary": {
            "domains": state.get("domains", []),
            "finding_count": len(state.get("findings", [])),
            "warnings": state.get("warnings", []),
            "cross_domain_notes": state.get("cross_domain_notes", []),
            "cross_domain_hypotheses": state.get("cross_domain_hypotheses", []),
        },
        "findings": [_compact_finding(finding) for finding in state.get("findings", [])],
        "ai_review": ai_review,
    }


def load_report_polish(result_dir: Path, run_id: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    path = Path(result_dir) / ".machine" / REPORT_POLISH_RESPONSE
    if not path.exists():
        return None, []
    try:
        data = _read_json(path)
    except Exception as exc:
        return None, [f"Could not read {REPORT_POLISH_RESPONSE}: {type(exc).__name__}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"Ignored {REPORT_POLISH_RESPONSE}: expected object"]
    warnings = _require_run_id(data, run_id, REPORT_POLISH_RESPONSE)
    if warnings:
        return None, warnings
    return data, []
