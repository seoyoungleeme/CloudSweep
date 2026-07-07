"""LangGraph orchestration runtime for CloudSweep FinOps analysis.

The Claude skill files remain the source of analyst instructions. This module
turns the same workflow into an executable graph so scenarios can be analyzed
repeatably from the command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import operator
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from .ai_review import (
    build_ai_review_request,
    build_report_polish_request,
    load_ai_review,
    load_report_polish,
)
from .anomaly import analyze_cost_anomaly
from .cross_domain import build_cross_domain_review
from .domain_analyzers import (
    ANALYZER_REGISTRY,
    _analyze_single_domain,
    _load_analysis_resources,
    _load_cost_summary,
)
from .domain_detection import (
    _add_domain_resource,
    _detect_domains,
    _domains_from_cost_report,
    _domains_from_records,
    _resource_blocks,
    _validate_genai_evidence,
)
from .enrichment import EnrichmentProvider, FallbackEnrichmentProvider
from .reporting import _pricing_review_requests, _render_optimized_tf, _render_report, _skill_review_requests
from .rule_engine import RuleValidationError, stable_id
from .token_usage import clear_start_marker, compute_usage, record_start_marker, write_usage_snapshot


class CloudSweepState(TypedDict, total=False):
    schema_version: str
    run_id: str
    work_dir: str
    result_dir: str
    write: bool
    standard_output: bool
    evidence: dict[str, Any]
    intent: str
    execution_plan: list[str]
    domains: list[str]
    domain_resources: dict[str, list[str]]
    cost_summary: dict[str, Any]
    anomaly: dict[str, Any]
    findings: list[dict[str, Any]]
    cross_domain_notes: list[str]
    cross_domain_hypotheses: list[dict[str, Any]]
    optimized_tf: str
    report_markdown: str
    output_paths: dict[str, str]
    warnings: list[str]
    trace: list[str]
    analysis_domain: str
    domain_results: Annotated[list[dict[str, Any]], operator.add]
    enrichment_status: dict[str, Any]
    require_approval: bool
    approval_threshold_usd: float
    approval_status: str
    approval_decision: dict[str, Any]
    analyzer_coverage: list[dict[str, str]]
    dependency_facts: list[dict[str, Any]]
    skill_requests: dict[str, dict[str, Any]]
    pricing_requests: dict[str, dict[str, Any]]
    ai_review: dict[str, Any]
    ai_review_request: dict[str, Any]
    report_polish: dict[str, Any]
    report_polish_request: dict[str, Any]


def _append(state: CloudSweepState, key: str, values: list[str]) -> list[str]:
    return [*state.get(key, []), *values]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _load_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _existing(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _metric_path(work_dir: Path) -> Path | None:
    candidates = [work_dir / "metrics.json", work_dir / "metrics" / "metrics.json"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _inventory_evidence(work_dir: Path) -> dict[str, Any]:
    mock_dir = work_dir / "mock_responses"
    ce_files = sorted(str(path) for path in mock_dir.glob("get_cost_and_usage*.json"))
    cloudtrail_files = sorted(str(path) for path in mock_dir.glob("cloudtrail*.json"))
    if (work_dir / "cloudtrail.json").exists():
        cloudtrail_files.append(str(work_dir / "cloudtrail.json"))

    metric_path = _metric_path(work_dir)
    evidence = {
        "terraform": _existing(work_dir / "main.tf"),
        "genai_evidence": _existing(work_dir / "genai_evidence.json"),
        "metrics": str(metric_path) if metric_path else None,
        "cost_report": _existing(work_dir / "cost_report.json"),
        "parsed_input": _existing(work_dir / "parsed_input.json"),
        "existing_findings": _existing(work_dir / "findings.json"),
        "cost_explorer": ce_files,
        "anomalies": _existing(mock_dir / "get_anomalies.json"),
        "cloudtrail": cloudtrail_files,
    }
    evidence["available"] = sorted(key for key, value in evidence.items() if value and key != "available")
    return evidence


def _infer_intent(work_dir: Path, evidence: dict[str, Any]) -> str:
    readme = ""
    readme_path = work_dir / "README.md"
    if readme_path.exists():
        readme = _read_text(readme_path).lower()

    has_incident = bool(evidence.get("cost_explorer") or evidence.get("anomalies"))
    has_waste = bool(evidence.get("terraform") or evidence.get("metrics") or evidence.get("cost_report"))
    incident_words = ("spike", "anomaly", "cost explorer", "hourly", "cloudtrail")
    waste_words = ("rightsizing", "overprovision", "lifecycle", "unused", "waste", "terraform")

    if has_incident and has_waste:
        return "blended"
    if has_incident or any(word in readme for word in incident_words):
        return "cost_spike_incident"
    if has_waste or any(word in readme for word in waste_words):
        return "waste_optimization"
    return "unknown"


def _build_execution_plan(evidence: dict[str, Any], intent: str) -> list[str]:
    plan: list[str] = []
    if evidence.get("cost_explorer") or evidence.get("anomalies"):
        plan.append("anomaly_analysis")
    if any(evidence.get(key) for key in ("terraform", "genai_evidence", "metrics", "parsed_input", "cost_report")):
        plan.append("domain_analysis")
    if not plan and evidence.get("existing_findings"):
        plan.append("existing_findings_summary")
    plan.append("report")
    return plan


def inventory_node(state: CloudSweepState) -> dict[str, Any]:
    work_dir = Path(state["work_dir"]).resolve()
    result_dir = Path(state.get("result_dir") or work_dir / "result").resolve()
    record_start_marker(result_dir, state.get("run_id"))
    evidence = _inventory_evidence(work_dir)
    intent = _infer_intent(work_dir, evidence)
    return {
        "work_dir": str(work_dir),
        "result_dir": str(result_dir),
        "evidence": evidence,
        "intent": intent,
        "trace": _append(state, "trace", [f"inventory: {', '.join(evidence['available']) or 'no known evidence'}"]),
    }


def plan_node(state: CloudSweepState) -> dict[str, Any]:
    plan = _build_execution_plan(state["evidence"], state["intent"])
    return {
        "execution_plan": plan,
        "trace": _append(state, "trace", [f"plan: {' -> '.join(plan)}"]),
    }


def _route_from_plan(state: CloudSweepState) -> Literal["anomaly_analysis", "detect_domains", "render_outputs"]:
    plan = state.get("execution_plan", [])
    if "anomaly_analysis" in plan:
        return "anomaly_analysis"
    if "domain_analysis" in plan:
        return "detect_domains"
    return "render_outputs"


def _route_after_anomaly(state: CloudSweepState) -> Literal["detect_domains", "render_outputs"]:
    if "domain_analysis" in state.get("execution_plan", []):
        return "detect_domains"
    return "render_outputs"


def detect_domains_node(state: CloudSweepState) -> dict[str, Any]:
    tf_path = state["evidence"].get("terraform")
    domains: list[str] = []
    resources: dict[str, list[str]] = {}
    warnings: list[str] = []

    def merge(found_domains: list[str], found_resources: dict[str, list[str]]) -> None:
        for domain in found_domains:
            for resource_name in found_resources.get(domain, []):
                _add_domain_resource(domains, resources, domain, resource_name)

    if tf_path:
        merge(*_detect_domains(_read_text(Path(tf_path))))

    for evidence_key in ("genai_evidence", "metrics", "parsed_input"):
        evidence_path = state["evidence"].get(evidence_key)
        if not evidence_path:
            continue
        data = _load_json(Path(evidence_path))
        if evidence_key == "genai_evidence":
            warnings.extend(f"Invalid GenAI evidence: {error}" for error in _validate_genai_evidence(data))
        merge(*_domains_from_records(data))

    merge(*_domains_from_cost_report(state["evidence"].get("cost_report")))
    return {
        "domains": domains,
        "domain_resources": resources,
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", [f"domains: {', '.join(domains) or 'none'}"]),
    }

def analyze_domain_node(state: CloudSweepState) -> dict[str, Any]:
    domain = state["analysis_domain"]
    try:
        registration = ANALYZER_REGISTRY.get(domain)
        work_dir = Path(state["work_dir"]) if state.get("work_dir") else None
        result = _analyze_single_domain(domain, state["evidence"], work_dir)
        result["analyzer_version"] = registration.version
    except RuleValidationError as exc:
        result = {"domain": domain, "findings": [], "warnings": [str(exc)], "analyzer_version": ""}
    return {"domain_results": [result]}


def _dispatch_domain_analysis(state: CloudSweepState) -> list[Send] | str:
    domains = state.get("domains", [])
    if not domains:
        return "collect_domain_results"
    return [
        Send(
            "analyze_domain",
            {
                "analysis_domain": domain,
                "evidence": state["evidence"],
                "work_dir": state.get("work_dir", ""),
            },
        )
        for domain in domains
    ]


def collect_domain_results_node(state: CloudSweepState) -> dict[str, Any]:
    domain_order = {domain: index for index, domain in enumerate(state.get("domains", []))}
    results = sorted(
        state.get("domain_results", []),
        key=lambda item: domain_order.get(str(item.get("domain", "")), len(domain_order)),
    )
    findings = [finding for result in results for finding in result.get("findings", [])]
    versions = {str(result.get("domain")): str(result.get("analyzer_version", "")) for result in results}
    skill_requests = {
        str(result["domain"]): result["skill_request"]
        for result in results
        if result.get("skill_request")
    }
    pricing_requests = {
        str(result["domain"]): result["pricing_request"]
        for result in results
        if result.get("pricing_request")
    }
    tf_path = state.get("evidence", {}).get("terraform")
    tf_blocks = {block["name"]: block for block in _resource_blocks(_read_text(Path(tf_path)))} if tf_path else {}
    for finding in findings:
        domain = str(finding.get("domain", "unknown"))
        rule_id = str(finding.get("rule_id", "UNKNOWN"))
        resource = str(finding.get("resource", "unknown"))
        finding["finding_id"] = stable_id(state.get("run_id"), domain, rule_id, resource)
        finding["rule_version"] = "2.0.0"
        finding["analyzer_version"] = versions.get(domain, "")
        finding["evidence_facts"] = [
            {
                "fact_id": stable_id(state.get("run_id"), domain, resource, index, statement),
                "statement": statement,
            }
            for index, statement in enumerate(finding.get("evidence", []))
        ]
        replacement = finding.get("optimized_replacement")
        if replacement:
            original = tf_blocks.get(str(replacement.get("resource")))
            if original:
                finding["remediation_patch"] = {
                    "kind": "replace_resource",
                    "resource": replacement["resource"],
                    "source_hash": hashlib.sha256(original["text"].encode("utf-8")).hexdigest(),
                    "content": replacement["text"],
                }
        elif finding.get("optimized_append"):
            finding["remediation_patch"] = {
                "kind": "append_block",
                "source_hash": hashlib.sha256(_read_text(Path(tf_path)).encode("utf-8")).hexdigest() if tf_path else "",
                "content": finding["optimized_append"],
            }
    warnings = [warning for result in results for warning in result.get("warnings", [])]
    trace_items = [f"domain result: {result.get('domain')} ({len(result.get('findings', []))} finding(s))" for result in results]
    return {
        "cost_summary": _load_cost_summary(state["evidence"].get("cost_report")),
        "findings": findings,
        "skill_requests": skill_requests,
        "pricing_requests": pricing_requests,
        "analyzer_coverage": ANALYZER_REGISTRY.coverage(state.get("domains", [])),
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(
            state,
            "trace",
            [
                f"domain fan-out: {len(results)} branch(es)",
                *trace_items,
                f"domain findings: {len(findings)}",
                f"pricing requests: {', '.join(sorted(pricing_requests)) or 'none'}",
            ],
        ),
    }


def _pricing_enrichment_node(provider: EnrichmentProvider):
    fallback = FallbackEnrichmentProvider()

    def verify_pricing_node(state: CloudSweepState) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        failures: list[str] = []
        for finding in state.get("findings", []):
            enriched = dict(finding)
            try:
                enriched["pricing_verification"] = provider.verify_pricing(enriched)
            except Exception as exc:  # Provider failures must not stop deterministic analysis.
                enriched["pricing_verification"] = fallback.verify_pricing(enriched)
                failures.append(f"{finding.get('rule_id', 'unknown')}: {type(exc).__name__}: {exc}")
            findings.append(enriched)
        status = {
            **state.get("enrichment_status", {}),
            "pricing": {
                "provider": provider.name,
                "finding_count": len(findings),
                "failure_count": len(failures),
            },
        }
        warnings = [f"Pricing enrichment fallback used for {failure}" for failure in failures]
        return {
            "findings": findings,
            "enrichment_status": status,
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", [f"pricing enrichment: {provider.name}, failures={len(failures)}"]),
        }

    return verify_pricing_node


def _docs_enrichment_node(provider: EnrichmentProvider):
    fallback = FallbackEnrichmentProvider()

    def fetch_doc_refs_node(state: CloudSweepState) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        failures: list[str] = []
        for finding in state.get("findings", []):
            enriched = dict(finding)
            try:
                enriched["documentation"] = provider.fetch_doc_refs(enriched)
            except Exception as exc:  # Provider failures must not stop deterministic analysis.
                enriched["documentation"] = fallback.fetch_doc_refs(enriched)
                failures.append(f"{finding.get('rule_id', 'unknown')}: {type(exc).__name__}: {exc}")
            findings.append(enriched)
        status = {
            **state.get("enrichment_status", {}),
            "documentation": {
                "provider": provider.name,
                "finding_count": len(findings),
                "failure_count": len(failures),
            },
        }
        warnings = [f"Documentation enrichment fallback used for {failure}" for failure in failures]
        return {
            "findings": findings,
            "enrichment_status": status,
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", [f"documentation enrichment: {provider.name}, failures={len(failures)}"]),
        }

    return fetch_doc_refs_node


def approval_gate_node(state: CloudSweepState) -> dict[str, Any]:
    if not state.get("require_approval", False):
        return {
            "approval_status": "not_required",
            "trace": _append(state, "trace", ["approval gate: not required"]),
        }

    threshold = float(state.get("approval_threshold_usd", 500.0))
    candidates = [
        {
            "rule_id": finding.get("rule_id"),
            "resource": finding.get("resource"),
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "estimated_monthly_saving_usd": finding.get("estimated_monthly_saving_usd", 0.0),
        }
        for finding in state.get("findings", [])
        if float(finding.get("estimated_monthly_saving_usd", 0.0) or 0.0) >= threshold
        or finding.get("confidence") == "LOW"
    ]
    if not candidates:
        return {
            "approval_status": "not_required",
            "trace": _append(state, "trace", ["approval gate: no candidates"]),
        }

    decision = interrupt(
        {
            "kind": "cloudsweep_finops_approval",
            "scenario": Path(state["work_dir"]).name,
            "threshold_usd": threshold,
            "candidates": candidates,
            "question": "Approve these findings for final reporting and remediation planning?",
        }
    )
    if isinstance(decision, dict):
        approved = bool(decision.get("approved"))
        decision_payload = decision
    else:
        approved = bool(decision)
        decision_payload = {"approved": approved}
    status = "approved" if approved else "rejected"
    warnings = [] if approved else ["Human approval was rejected; findings remain advisory only."]
    return {
        "approval_status": status,
        "approval_decision": decision_payload,
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", [f"approval gate: {status}"]),
    }


def anomaly_node(state: CloudSweepState) -> dict[str, Any]:
    anomaly = analyze_cost_anomaly(state["evidence"], state.get("run_id"))
    spikes = anomaly.get("spikes", [])
    anomalies = anomaly.get("anomalies", [])
    return {
        "anomaly": anomaly,
        "trace": _append(state, "trace", [f"anomaly: {len(spikes)} spike(s), {len(anomalies)} anomaly record(s)"]),
    }


def cross_domain_node(state: CloudSweepState) -> dict[str, Any]:
    resources, _ = _load_analysis_resources(state.get("evidence", {}))
    review = build_cross_domain_review(
        run_id=state.get("run_id"),
        domains=state.get("domains", []),
        findings=state.get("findings", []),
        anomaly=state.get("anomaly", {}),
        terraform_path=state.get("evidence", {}).get("terraform"),
        resources=resources,
        read_text=_read_text,
    )
    annotated = [f for f in review["findings"] if f.get("cross_domain_refs")]
    return {
        "findings": review["findings"],
        "cross_domain_notes": review["notes"],
        "cross_domain_hypotheses": review.get("hypotheses", []),
        "dependency_facts": review["dependency_facts"],
        "trace": _append(state, "trace", [
            f"cross-domain notes: {len(review['notes'])}",
            f"cross-domain hypotheses: {len(review.get('hypotheses', []))}",
            f"cross-domain annotations: {len(annotated)} finding(s)",
        ]),
    }


def ai_review_node(state: CloudSweepState) -> dict[str, Any]:
    result_dir = Path(state["result_dir"])
    review, warnings = load_ai_review(result_dir, state.get("run_id"))
    if review:
        return {
            "ai_review": review,
            "ai_review_request": {},
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", ["ai review: loaded"]),
        }
    return {
        "ai_review": {},
        "ai_review_request": build_ai_review_request(state),
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", ["ai review: requested"]),
    }


def report_polish_node(state: CloudSweepState) -> dict[str, Any]:
    result_dir = Path(state["result_dir"])
    polish, warnings = load_report_polish(result_dir, state.get("run_id"))
    if polish:
        return {
            "report_polish": polish,
            "report_polish_request": {},
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", ["report polish: loaded"]),
        }
    if state.get("ai_review"):
        return {
            "report_polish": {},
            "report_polish_request": build_report_polish_request(state),
            "warnings": _append(state, "warnings", warnings),
            "trace": _append(state, "trace", ["report polish: requested"]),
        }
    return {
        "report_polish": {},
        "report_polish_request": {},
        "warnings": _append(state, "warnings", warnings),
        "trace": _append(state, "trace", ["report polish: waiting for ai review"]),
    }


def render_node(state: CloudSweepState) -> dict[str, Any]:
    result_dir = Path(state["result_dir"])
    machine_dir = result_dir / ".machine"
    standard = bool(state.get("standard_output", False))
    report_name = "finops_report.md" if standard else "cloudsweep_graph_report.md"
    tf_name = "main_optimized.tf" if standard else "cloudsweep_main_optimized.tf"
    output_paths = {
        "report": str(result_dir / report_name),
        "optimized_tf": str(result_dir / tf_name),
        "state": str(machine_dir / "cloudsweep_graph_state.json"),
    }
    skill_requests = _skill_review_requests(state)
    output_paths["skill_requests"] = {
        domain: str(machine_dir / f"{domain}_skill_request.json")
        for domain in skill_requests
    }
    pricing_requests = _pricing_review_requests(state)
    output_paths["pricing_requests"] = {
        domain: str(machine_dir / f"{domain}_pricing_request.json")
        for domain in pricing_requests
    }
    ai_review_request = state.get("ai_review_request") or {}
    if ai_review_request:
        output_paths["ai_review_request"] = str(machine_dir / "ai_review_request.json")
    report_polish_request = state.get("report_polish_request") or {}
    if report_polish_request:
        output_paths["report_polish_request"] = str(machine_dir / "report_polish_request.json")
    optimized_tf = _render_optimized_tf(state)
    report = _render_report({**state, "optimized_tf": optimized_tf, "output_paths": output_paths})

    if state.get("write", True):
        result_dir.mkdir(parents=True, exist_ok=True)
        machine_dir.mkdir(parents=True, exist_ok=True)
        Path(output_paths["report"]).write_text(report, encoding="utf-8")
        Path(output_paths["optimized_tf"]).write_text(optimized_tf, encoding="utf-8")
        for pattern, active in (
            ("*_skill_request.json", output_paths["skill_requests"].values()),
            ("*_pricing_request.json", output_paths["pricing_requests"].values()),
        ):
            active_paths = {Path(path).resolve() for path in active}
            for stale_path in machine_dir.glob(pattern):
                if stale_path.resolve() not in active_paths:
                    stale_path.unlink()
        for domain, request in skill_requests.items():
            Path(output_paths["skill_requests"][domain]).write_text(
                json.dumps(request, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        for domain, request in pricing_requests.items():
            Path(output_paths["pricing_requests"][domain]).write_text(
                json.dumps(request, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        for key, request in (
            ("ai_review_request", ai_review_request),
            ("report_polish_request", report_polish_request),
        ):
            request_path = machine_dir / f"{key}.json"
            if request:
                Path(output_paths[key]).write_text(
                    json.dumps(request, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            elif request_path.exists():
                request_path.unlink()
        state_payload = {
            "schema_version": state.get("schema_version"),
            "run_id": state.get("run_id"),
            "work_dir": state.get("work_dir"),
            "intent": state.get("intent"),
            "execution_plan": state.get("execution_plan"),
            "domains": state.get("domains"),
            "domain_resources": state.get("domain_resources"),
            "analyzer_coverage": state.get("analyzer_coverage"),
            "findings": state.get("findings"),
            "skill_requests": state.get("skill_requests"),
            "pricing_requests": state.get("pricing_requests"),
            "dependency_facts": state.get("dependency_facts"),
            "enrichment_status": state.get("enrichment_status"),
            "approval_status": state.get("approval_status"),
            "approval_decision": state.get("approval_decision"),
            "anomaly": state.get("anomaly"),
            "cross_domain_notes": state.get("cross_domain_notes"),
            "cross_domain_hypotheses": state.get("cross_domain_hypotheses"),
            "ai_review": state.get("ai_review"),
            "ai_review_request": state.get("ai_review_request"),
            "report_polish": state.get("report_polish"),
            "report_polish_request": state.get("report_polish_request"),
            "warnings": state.get("warnings"),
            "trace": state.get("trace"),
            "output_paths": output_paths,
        }
        Path(output_paths["state"]).write_text(json.dumps(state_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if not (
            skill_requests
            or pricing_requests
            or ai_review_request
            or report_polish_request
        ):
            usage = compute_usage(result_dir, run_id=state.get("run_id"))
            write_usage_snapshot(result_dir, usage, run_id=state.get("run_id"))
            clear_start_marker(result_dir)

    return {
        "optimized_tf": optimized_tf,
        "report_markdown": report,
        "output_paths": output_paths,
        "trace": _append(state, "trace", ["render: outputs prepared"]),
    }


def build_graph(
    *,
    enrichment_provider: EnrichmentProvider | None = None,
    checkpointer: Any = None,
):
    provider = enrichment_provider or FallbackEnrichmentProvider()
    builder = StateGraph(CloudSweepState)
    builder.add_node("inventory", inventory_node)
    builder.add_node("plan", plan_node)
    builder.add_node("anomaly_analysis", anomaly_node)
    builder.add_node("detect_domains", detect_domains_node)
    builder.add_node("analyze_domain", analyze_domain_node)
    builder.add_node("collect_domain_results", collect_domain_results_node)
    builder.add_node("verify_pricing", _pricing_enrichment_node(provider))
    builder.add_node("fetch_doc_refs", _docs_enrichment_node(provider))
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("cross_domain_review", cross_domain_node)
    builder.add_node("ai_review", ai_review_node)
    builder.add_node("report_polish", report_polish_node)
    builder.add_node("render_outputs", render_node)

    builder.add_edge(START, "inventory")
    builder.add_edge("inventory", "plan")
    builder.add_conditional_edges(
        "plan",
        _route_from_plan,
        {
            "anomaly_analysis": "anomaly_analysis",
            "detect_domains": "detect_domains",
            "render_outputs": "render_outputs",
        },
    )
    builder.add_conditional_edges(
        "anomaly_analysis",
        _route_after_anomaly,
        {
            "detect_domains": "detect_domains",
            "render_outputs": "render_outputs",
        },
    )
    builder.add_conditional_edges(
        "detect_domains",
        _dispatch_domain_analysis,
        ["analyze_domain", "collect_domain_results"],
    )
    builder.add_edge("analyze_domain", "collect_domain_results")
    builder.add_edge("collect_domain_results", "verify_pricing")
    builder.add_edge("verify_pricing", "fetch_doc_refs")
    builder.add_edge("fetch_doc_refs", "approval_gate")
    builder.add_edge("approval_gate", "cross_domain_review")
    builder.add_edge("cross_domain_review", "ai_review")
    builder.add_edge("ai_review", "report_polish")
    builder.add_edge("report_polish", "render_outputs")
    builder.add_edge("render_outputs", END)
    return builder.compile(checkpointer=checkpointer)


def _initial_state(
    work_dir: str | Path,
    *,
    write: bool,
    standard_output: bool,
    require_approval: bool,
    approval_threshold_usd: float,
) -> CloudSweepState:
    work_dir = Path(work_dir).resolve()
    run_id = stable_id(str(work_dir), date.today().isoformat())
    return {
        "schema_version": "2.0",
        "run_id": run_id,
        "work_dir": str(work_dir),
        "result_dir": str(work_dir / "result"),
        "write": write,
        "standard_output": standard_output,
        "warnings": [],
        "trace": [],
        "findings": [],
        "domain_results": [],
        "skill_requests": {},
        "pricing_requests": {},
        "cross_domain_hypotheses": [],
        "ai_review": {},
        "ai_review_request": {},
        "report_polish": {},
        "report_polish_request": {},
        "enrichment_status": {},
        "require_approval": require_approval,
        "approval_threshold_usd": approval_threshold_usd,
        "approval_status": "pending" if require_approval else "not_required",
    }


def run_graph(
    work_dir: str | Path,
    *,
    write: bool = True,
    standard_output: bool = False,
    enrichment_provider: EnrichmentProvider | None = None,
) -> CloudSweepState:
    app = build_graph(enrichment_provider=enrichment_provider)
    return app.invoke(
        _initial_state(
            work_dir,
            write=write,
            standard_output=standard_output,
            require_approval=False,
            approval_threshold_usd=500.0,
        )
    )


class CloudSweepRuntime:
    """Checkpointed runtime for interrupt and resume workflows."""

    def __init__(
        self,
        *,
        enrichment_provider: EnrichmentProvider | None = None,
        checkpointer: Any = None,
    ) -> None:
        self.checkpointer = checkpointer or InMemorySaver()
        self.app = build_graph(
            enrichment_provider=enrichment_provider,
            checkpointer=self.checkpointer,
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def run(
        self,
        work_dir: str | Path,
        *,
        thread_id: str,
        write: bool = True,
        standard_output: bool = False,
        require_approval: bool = True,
        approval_threshold_usd: float = 500.0,
    ) -> CloudSweepState:
        config = self._config(thread_id)
        if self.app.get_state(config).values:
            raise ValueError(f"Checkpoint thread '{thread_id}' already exists; resume it or use a new thread_id.")
        return self.app.invoke(
            _initial_state(
                work_dir,
                write=write,
                standard_output=standard_output,
                require_approval=require_approval,
                approval_threshold_usd=approval_threshold_usd,
            ),
            config=config,
        )

    def resume(self, thread_id: str, decision: dict[str, Any] | bool) -> CloudSweepState:
        return self.app.invoke(
            Command(resume=decision),
            config=self._config(thread_id),
        )

    def get_state(self, thread_id: str):
        return self.app.get_state(self._config(thread_id))


def main(argv: list[str] | None = None) -> None:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "finalize":
        from .finalizer import finalize

        final_parser = argparse.ArgumentParser(description="Finalize reviewed CloudSweep findings.")
        final_parser.add_argument("command")
        final_parser.add_argument("work_dir")
        final_parser.add_argument("--review", required=True)
        final_args = final_parser.parse_args(args_list)
        outputs = finalize(final_args.work_dir, final_args.review)
        print("Legacy finalize output is isolated under result/.machine and does not overwrite finops_report.md.")
        print(f"Legacy report: {outputs['report']}")
        print(f"Legacy optimized Terraform: {outputs['optimized_tf']}")
        return
    parser = argparse.ArgumentParser(description="Run the CloudSweep LangGraph FinOps workflow.")
    parser.add_argument("work_dir", nargs="?", default=".", help="Scenario/workload directory to analyze.")
    parser.add_argument("--dry-run", action="store_true", help="Run the graph without writing result files.")
    parser.add_argument(
        "--standard-output",
        action="store_true",
        help="Write result/finops_report.md and result/main_optimized.tf instead of graph-specific filenames.",
    )
    parser.add_argument(
        "--from-ministack",
        action="store_true",
        help="Collect read-only MiniStack evidence into work_dir before running the graph.",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Collect MiniStack evidence and exit before graph analysis; requires --from-ministack.",
    )
    args = parser.parse_args(args_list)
    if args.collect_only and not args.from_ministack:
        parser.error("--collect-only requires --from-ministack")

    work_dir: str | Path = args.work_dir
    if args.from_ministack:
        from .ministack_collector import collect_ministack

        work_dir = collect_ministack(work_dir)
        print(f"MiniStack evidence: {work_dir}")
        if args.collect_only:
            print("Collection complete: graph analysis not run.")
            return

    state = run_graph(work_dir, write=not args.dry_run, standard_output=args.standard_output)
    print(f"Intent: {state.get('intent')}")
    print(f"Plan: {' -> '.join(state.get('execution_plan', []))}")
    print(f"Domains: {', '.join(state.get('domains', [])) or 'none'}")
    print(f"Findings: {len(state.get('findings', []))}")
    pending_skills = sorted(state.get("skill_requests", {}))
    if pending_skills:
        print(f"Skill analysis required: {', '.join(pending_skills)}")
    pending_pricing = sorted(state.get("pricing_requests", {}))
    if pending_pricing:
        print(f"Pricing model requested (public-pricing lookup pending): {', '.join(pending_pricing)}")
    if state.get("ai_review_request"):
        print("AI review requested: result/.machine/ai_review_request.json")
    if state.get("report_polish_request"):
        print("Report polish requested: result/.machine/report_polish_request.json")
    if args.dry_run:
        if args.from_ministack:
            print("Dry run: evidence files written; graph result files not written.")
        else:
            print("Dry run: no files written.")
    else:
        print(f"Report: {state['output_paths']['report']}")
        print(f"Optimized Terraform: {state['output_paths']['optimized_tf']}")


if __name__ == "__main__":
    main()
