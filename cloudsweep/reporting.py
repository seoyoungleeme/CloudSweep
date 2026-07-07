"""Report and output rendering for CloudSweep graph runs."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .domain_detection import _resource_blocks
from .token_usage import compute_usage, render_markdown as _render_token_usage


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _render_optimized_tf(state: dict[str, Any]) -> str:
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
        "| Domain | Resource | Display Name | Rule | Source | Status | Severity | Confidence | Pricing Confidence | Savings Status | Pricing Source | Monthly Savings |",
        "|--------|----------|--------------|------|--------|--------|----------|------------|--------------------|----------------|----------------|-----------------|",
    ]
    for finding in findings:
        lines.append(
            "| {domain} | {resource} | {display_name} | {rule_id} | {source} | {status} | {severity} | {confidence} | {pricing_confidence} | {savings_status} | {pricing_source} | ${saving:.2f} |".format(
                domain=finding.get("domain", ""),
                resource=finding.get("resource", ""),
                display_name=finding.get("display_name", finding.get("resource", "")),
                rule_id=finding.get("rule_id", ""),
                source=finding.get("analysis_source", "unknown"),
                status=finding.get("review_status", "unknown"),
                severity=finding.get("severity", ""),
                confidence=finding.get("confidence", ""),
                pricing_confidence=finding.get("pricing_confidence", "n/a"),
                savings_status=_finding_savings_status(finding),
                pricing_source=finding.get("pricing_source", "n/a"),
                saving=float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0),
            )
        )
    return lines


def _finding_savings_status(finding: dict[str, Any]) -> str:
    status = finding.get("savings_status")
    if isinstance(status, str) and status:
        return status
    if finding.get("pricing_source") == "unmeasured":
        return "unmeasured"
    if finding.get("pricing_source") == "reasonable_estimate":
        return "reasonable_estimate"
    return "priced"


def _conservative_monthly_savings(
    findings: list[dict[str, Any]],
    statuses: set[str] | None = None,
) -> float:
    grouped: dict[str, float] = {}
    ungrouped = 0.0
    for finding in findings:
        if statuses is not None and _finding_savings_status(finding) not in statuses:
            continue
        savings = float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0)
        group = finding.get("savings_group")
        if group:
            grouped[str(group)] = max(grouped.get(str(group), 0.0), savings)
        else:
            ungrouped += savings
    return round(ungrouped + sum(grouped.values()), 2)


def _priority_summary(findings: list[dict[str, Any]]) -> list[str]:
    evidence_backed = _conservative_monthly_savings(findings, {"priced"})
    reasonable = _conservative_monthly_savings(findings, {"reasonable_estimate"})
    unmeasured = [f for f in findings if _finding_savings_status(f) == "unmeasured"]
    lines = [
        "## Priority Summary",
        "",
        f"- Evidence-backed monthly savings: **${evidence_backed:.2f}**",
        f"- Reasonable estimate upside: **${reasonable:.2f}**",
        f"- Unmeasured candidates: **{len(unmeasured)}**",
    ]
    candidates = [
        finding for finding in findings
        if float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0) > 0
    ]
    candidates.sort(
        key=lambda finding: (
            -float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0),
            0 if _finding_savings_status(finding) == "priced" else 1,
        )
    )
    if candidates:
        lines.extend([
            "",
            "| Status | Domain | Resource | Rule | Monthly Savings |",
            "|--------|--------|----------|------|-----------------|",
        ])
        for finding in candidates[:8]:
            lines.append(
                "| {status} | {domain} | {resource} | {rule} | ${saving:.2f} |".format(
                    status=_finding_savings_status(finding),
                    domain=finding.get("domain", ""),
                    resource=finding.get("display_name", finding.get("resource", "")),
                    rule=finding.get("rule_id", ""),
                    saving=float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0),
                )
            )
    if reasonable:
        lines.extend([
            "",
            "_Reasonable estimates are review upside, not additive guaranteed savings._",
        ])
    return lines


def _savings_notes(findings: list[dict[str, Any]]) -> list[str]:
    rows = [
        finding for finding in findings
        if finding.get("savings_reason") or _finding_savings_status(finding) != "priced"
    ]
    if not rows:
        return []
    lines = ["## Savings Notes", ""]
    for finding in rows:
        reason = finding.get("savings_reason", "n/a")
        lines.append(
            "- {domain}/{resource}: {status}; {reason}".format(
                domain=finding.get("domain", ""),
                resource=finding.get("display_name", finding.get("resource", "")),
                status=_finding_savings_status(finding),
                reason=reason,
            )
        )
    return lines


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ai_report_sections(state: dict[str, Any]) -> list[str]:
    ai_review = state.get("ai_review") if isinstance(state.get("ai_review"), dict) else {}
    polish = state.get("report_polish") if isinstance(state.get("report_polish"), dict) else {}
    output_paths = state.get("output_paths", {})
    lines: list[str] = []

    if polish:
        summary = str(polish.get("executive_summary") or "").strip()
        key_points = [str(item) for item in _as_list(polish.get("key_points")) if item]
        caveats = [str(item) for item in _as_list(polish.get("caveats")) if item]
        if summary or key_points or caveats:
            lines.extend(["## Executive Summary", ""])
            if summary:
                lines.extend([summary, ""])
            for item in key_points:
                lines.append(f"- {item}")
            if caveats:
                lines.extend(["", "Key caveats:"])
                for item in caveats:
                    lines.append(f"- {item}")
            lines.append("")
    elif output_paths.get("report_polish_request"):
        lines.extend([
            "## Report Polish Required",
            "",
            f"Pending request: {output_paths['report_polish_request']}",
            "",
        ])

    if ai_review:
        summary = str(ai_review.get("summary") or "").strip()
        notes = [str(item) for item in _as_list(ai_review.get("review_notes")) if item]
        quality_flags = [str(item) for item in _as_list(ai_review.get("quality_flags")) if item]
        missed = [str(item) for item in _as_list(ai_review.get("missed_candidate_hypotheses")) if item]
        lines.extend(["## AI Review", ""])
        if summary:
            lines.extend([summary, ""])
        for label, rows in (
            ("Review notes", notes),
            ("Quality flags", quality_flags),
            ("Missed-candidate hypotheses", missed),
        ):
            if not rows:
                continue
            lines.append(f"{label}:")
            for item in rows:
                lines.append(f"- {item}")
            lines.append("")
    elif output_paths.get("ai_review_request"):
        lines.extend([
            "## AI Review Required",
            "",
            f"Pending request: {output_paths['ai_review_request']}",
            "",
        ])
    return lines


def _render_report(state: dict[str, Any]) -> str:
    evidence = state.get("evidence", {})
    findings = state.get("findings", [])
    anomaly = state.get("anomaly", {})
    total_savings = _conservative_monthly_savings(findings, {"priced"})
    reasonable_savings = _conservative_monthly_savings(findings, {"reasonable_estimate"})
    lines = [
        "# CloudSweep LangGraph Report",
        "",
        f"**Scenario**: {Path(state['work_dir']).name}",
        f"**Run date**: {date.today().isoformat()}",
        f"**Intent**: {state.get('intent', 'unknown')}",
        f"**Execution plan**: {' -> '.join(state.get('execution_plan', []))}",
        "",
        *_render_token_usage(compute_usage(Path(state["result_dir"]), run_id=state.get("run_id"))),
        "",
        *_ai_report_sections(state),
        *_priority_summary(findings),
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
            f"Estimated monthly savings: **${total_savings:.2f}**",
            f"Reasonable estimate upside: **${reasonable_savings:.2f}**",
            "",
            *_savings_notes(findings),
            "",
            "## Enrichment",
            "",
        ]
    )
    pending_domains = sorted(state.get("skill_requests", {}))
    if pending_domains:
        lines.extend(
            [
                "",
                "## Skill Analysis Required",
                "",
                f"Pending complex domains: {', '.join(pending_domains)}",
                "",
                "These domains require Skill analysis or re-analysis before complex-domain "
                "findings and public-pricing savings are fully up to date.",
            ]
        )
    pending_pricing = sorted(state.get("pricing_requests", {}))
    if pending_pricing:
        lines.extend(
            [
                "",
                "## Pricing Model Requested",
                "",
                f"Domains awaiting AWS public pricing lookup: {', '.join(pending_pricing)}",
                "",
                "Findings are not withheld -- they are already priced via cost_report, a static "
                "fallback estimate, or reported as unmeasured. Supplying "
                "pricing_cache/{domain}_pricing_model.json (shared across scenarios) lets simple "
                "analyzers upgrade directly and lets complex-domain Skill requests include public "
                "pricing for re-analysis.",
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
    hypotheses = state.get("cross_domain_hypotheses", [])
    if hypotheses:
        lines.extend(["", "## Cross-Domain Hypotheses", ""])
        for item in hypotheses:
            lines.append(f"- [{item.get('status', 'hypothesis')}] {item.get('statement', '')}")
    if state.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in state["warnings"]:
            lines.append(f"- {warning}")
    lines.extend(["", "## Graph Trace", ""])
    for item in state.get("trace", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _skill_review_requests(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    existing = state.get("skill_requests")
    if isinstance(existing, dict):
        return existing
    return {}


def _pricing_review_requests(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    existing = state.get("pricing_requests")
    if isinstance(existing, dict):
        return existing
    return {}
