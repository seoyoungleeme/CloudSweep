"""Optional pricing and documentation enrichment providers.

The LangGraph runtime depends on this small interface instead of a specific MCP
transport. A CLI, service, or test harness can inject callable MCP adapters,
while local runs keep deterministic evidence as a fallback.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class EnrichmentProvider(Protocol):
    """Provide post-analysis pricing verification and documentation links."""

    name: str

    def verify_pricing(self, finding: dict[str, Any]) -> dict[str, Any]: ...

    def fetch_doc_refs(self, finding: dict[str, Any]) -> dict[str, Any]: ...


def _finding_pricing_source(finding: dict[str, Any]) -> str:
    for evidence in finding.get("evidence", []):
        if isinstance(evidence, str) and evidence.startswith("pricing_source="):
            return evidence.split("=", 1)[1]
    return "unavailable"


class FallbackEnrichmentProvider:
    """Keep scenario pricing and mark documentation as unavailable."""

    name = "local-fallback"

    def verify_pricing(self, finding: dict[str, Any]) -> dict[str, Any]:
        source = _finding_pricing_source(finding)
        return {
            "status": "evidence_only" if source != "unavailable" else "unavailable",
            "source": source,
            "note": "External AWS pricing verification was not performed.",
        }

    def fetch_doc_refs(self, finding: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "urls": [],
            "note": "AWS documentation MCP was not available.",
        }


class CallableMCPEnrichmentProvider:
    """Adapt MCP gateway callables without coupling the graph to its transport."""

    name = "aws-mcp"

    def __init__(
        self,
        pricing_lookup: Callable[[str, dict[str, Any]], dict[str, Any]],
        docs_search: Callable[[str, dict[str, Any]], list[str]],
    ) -> None:
        self._pricing_lookup = pricing_lookup
        self._docs_search = docs_search

    def verify_pricing(self, finding: dict[str, Any]) -> dict[str, Any]:
        result = self._pricing_lookup(str(finding.get("domain", "")), finding)
        return {
            "status": "verified",
            "source": "aws-pricing-mcp",
            **result,
        }

    def fetch_doc_refs(self, finding: dict[str, Any]) -> dict[str, Any]:
        query = f"AWS {finding.get('domain', '')} {finding.get('rule_id', '')} remediation"
        urls = self._docs_search(query, finding)
        return {
            "status": "available" if urls else "unavailable",
            "urls": urls,
            "source": "aws-docs-mcp",
        }
