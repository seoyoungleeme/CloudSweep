"""Deterministically render reviewed CloudSweep findings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ReviewValidationError(ValueError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_review(state: dict[str, Any], review: dict[str, Any]) -> None:
    if review.get("schema_version") != "1.0":
        raise ReviewValidationError("review schema_version must be '1.0'")
    if review.get("run_id") != state.get("run_id"):
        raise ReviewValidationError("review run_id does not match machine state")
    machine_ids = {finding.get("finding_id") for finding in state.get("findings", [])}
    rows = review.get("finding_reviews")
    if not isinstance(rows, list):
        raise ReviewValidationError("finding_reviews must be a list")
    review_ids = [row.get("finding_id") for row in rows if isinstance(row, dict)]
    if len(review_ids) != len(set(review_ids)):
        raise ReviewValidationError("finding_reviews contains duplicate finding_id")
    unknown = set(review_ids) - machine_ids
    missing = machine_ids - set(review_ids)
    if unknown:
        raise ReviewValidationError(f"review contains unknown finding IDs: {sorted(unknown)}")
    if missing:
        raise ReviewValidationError(f"review is missing finding IDs: {sorted(missing)}")
    for row in rows:
        if row.get("disposition") not in {"accepted", "rejected", "needs_evidence"}:
            raise ReviewValidationError(f"invalid disposition for {row.get('finding_id')}")
        if "estimated_monthly_saving_usd" in row:
            raise ReviewValidationError("review cannot override machine savings")
    known_facts = {
        fact.get("fact_id")
        for finding in state.get("findings", [])
        for fact in finding.get("evidence_facts", [])
    } | {fact.get("fact_id") for fact in state.get("dependency_facts", [])}
    for item in review.get("cross_domain_review", []):
        if item.get("status") == "observed" and not item.get("fact_ids"):
            raise ReviewValidationError("observed cross-domain statements require fact_ids")
        unknown_facts = set(item.get("fact_ids", [])) - known_facts
        if unknown_facts:
            raise ReviewValidationError(f"cross-domain review references unknown facts: {sorted(unknown_facts)}")


def _conservative_total(findings: list[dict[str, Any]]) -> float:
    groups: dict[str, float] = {}
    total = 0.0
    for finding in findings:
        value = float(finding.get("estimated_monthly_saving_usd", 0) or 0)
        group = finding.get("savings_group")
        if group:
            groups[str(group)] = max(groups.get(str(group), 0.0), value)
        else:
            total += value
    return round(total + sum(groups.values()), 2)


def _apply_patches(work_dir: Path, accepted: list[dict[str, Any]]) -> str:
    from .graph import _resource_blocks

    tf_path = work_dir / "main.tf"
    if not tf_path.exists():
        return "# CloudSweep: no Terraform input was available for this scenario.\n"
    text = tf_path.read_text(encoding="utf-8")
    append_blocks: list[str] = []
    for finding in accepted:
        patch = finding.get("remediation_patch")
        if not patch:
            continue
        if patch.get("kind") == "replace_resource":
            original = next((block for block in _resource_blocks(text) if block["name"] == patch.get("resource")), None)
            if not original:
                raise ReviewValidationError(f"Terraform resource missing for {finding['finding_id']}")
            digest = hashlib.sha256(original["text"].encode("utf-8")).hexdigest()
            if digest != patch.get("source_hash"):
                raise ReviewValidationError(f"Terraform source hash mismatch for {finding['finding_id']}")
            text = text.replace(original["text"], patch["content"], 1)
        elif patch.get("kind") == "append_block":
            append_blocks.append(str(patch.get("content", "")))
    if append_blocks:
        text = text.rstrip() + "\n\n# CloudSweep accepted remediation candidates\n" + "\n\n".join(append_blocks) + "\n"
    return text


def finalize(work_dir: str | Path, review_path: str | Path) -> dict[str, str]:
    work_dir = Path(work_dir).resolve()
    result_dir = work_dir / "result"
    state = load_json(result_dir / "cloudsweep_graph_state.json")
    review = load_json(review_path)
    validate_review(state, review)
    review_by_id = {row["finding_id"]: row for row in review["finding_reviews"]}
    accepted = [finding for finding in state.get("findings", []) if review_by_id[finding["finding_id"]]["disposition"] == "accepted"]
    total = _conservative_total(accepted)
    lines = [
        "# FinOps Analysis Report",
        "",
        f"- **Scenario**: {work_dir.name}",
        f"- **Run ID**: {state.get('run_id')}",
        f"- **Domains analyzed**: {', '.join(state.get('domains', [])) or 'none'}",
        f"- **Conservative accepted monthly savings**: ${total:.2f}",
        "",
        "## Executive Summary",
        "",
        review.get("final_summary", ""),
        "",
        "## Reviewed Findings",
        "",
        "| Domain | Resource | Rule | Disposition | Confidence | Monthly Savings |",
        "|--------|----------|------|-------------|------------|-----------------|",
    ]
    for finding in state.get("findings", []):
        row = review_by_id[finding["finding_id"]]
        lines.append(
            f"| {finding.get('domain')} | {finding.get('resource')} | {finding.get('rule_id')} | "
            f"{row['disposition']} | {row.get('review_confidence', finding.get('confidence'))} | "
            f"${float(finding.get('estimated_monthly_saving_usd', 0) or 0):.2f} |"
        )
        lines.append(f"\n- **{finding['finding_id']} review**: {row.get('rationale', '')}")
        if row.get("documentation_urls"):
            lines.append(f"- Docs: {', '.join(row['documentation_urls'])}")
    lines.extend(["", "## Cross-Domain Review", ""])
    for item in review.get("cross_domain_review", []):
        lines.append(f"- [{item['status']}] {item['statement']} (facts: {', '.join(item.get('fact_ids', [])) or 'none'})")
    report_path = result_dir / "finops_report.md"
    tf_path = result_dir / "main_optimized.tf"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tf_path.write_text(_apply_patches(work_dir, accepted), encoding="utf-8")
    return {"report": str(report_path), "optimized_tf": str(tf_path)}
