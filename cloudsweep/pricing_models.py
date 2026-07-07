"""Public-pricing waterfall support for domains lacking cost_report evidence.

When a scenario lacks usable cost_report.json pricing, analyzers and complex
domain Skills can still model savings using AWS public list pricing instead of
locking estimated_monthly_saving_usd to $0. Claude supplies only a raw unit
price per SKU (via mcp__aws-pricing__get_pricing), written to a SHARED cache
file at pricing_cache/{domain}_pricing_model.json (repo root, not scoped to
any one scenario). Simple-domain analyzers perform their own quantity x price
arithmetic; complex-domain Skills receive the resolved unit prices in their
evidence bundle and remain authoritative for findings.

The cache is shared because AWS public list pricing for a given region+SKU is
identical regardless of which scenario is being analyzed -- unlike
{domain}_skill_analysis.json (genuinely scenario-specific findings), a unit
price fetched once should be reused by every scenario in that region rather
than re-fetched and duplicated per scenario. Claude should merge new sku_key
entries into the existing cache file rather than overwriting it.

The pricing_request/pricing_model exchange is asynchronous, best-effort enrichment:
a missing or unresolved pricing_model.json must never push a resolvable finding down
to $0 -- callers fall back to the domain rule's static per-unit price first.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRICING_MODEL_DOMAINS = frozenset({"s3", "lambda", "rds", "elb", "ecs", "elasticache"})
PRICING_PILOT_DOMAINS = PRICING_MODEL_DOMAINS
PRICING_SOURCE_TAG = "aws_public_pricing_model"


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig", errors="replace"))


def _pricing_cache_dir() -> Path:
    """Shared, cross-scenario cache directory for AWS public pricing models.

    A plain function (not a precomputed constant) so tests can monkeypatch it
    (e.g. ``unittest.mock.patch("cloudsweep.pricing_models._pricing_cache_dir")``)
    to redirect reads/writes to an isolated tmp directory instead of the real
    repo-level cache.
    """
    return Path(__file__).resolve().parents[1] / "pricing_cache"


def _pricing_cache_path(domain: str) -> Path:
    return _pricing_cache_dir() / f"{domain}_pricing_model.json"


def _load_pricing_model_with_warnings(work_dir: Path | None, domain: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load Claude-supplied unit prices for a domain, keyed by sku_key.

    Reads from the shared cross-scenario cache (see module docstring), not
    from ``work_dir``. ``work_dir`` is accepted for call-site compatibility
    with the per-scenario request/skill-analysis loaders but is not used to
    resolve the pricing model's location.
    """
    path = _pricing_cache_path(domain)
    if not path.exists():
        return {}, []
    try:
        data = _load_json(path)
    except Exception as exc:
        return {}, [f"Could not read {path.name}: {type(exc).__name__}: {exc}"]
    if not isinstance(data, dict) or data.get("domain") != domain:
        return {}, [f"Ignored {path.name}: schema domain did not match '{domain}'"]
    if data.get("schema_version") != "1.0":
        return {}, [f"Ignored {path.name}: schema_version must be '1.0'"]
    if data.get("pricing_source") != PRICING_SOURCE_TAG:
        return {}, [f"Ignored {path.name}: pricing_source must be '{PRICING_SOURCE_TAG}'"]
    unit_prices = data.get("unit_prices")
    if not isinstance(unit_prices, list):
        return {}, [f"Ignored {path.name}: unit_prices must be a list"]

    resolved: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for entry in unit_prices:
        if not isinstance(entry, dict):
            warnings.append(f"Ignored non-object unit_prices entry in {path.name}")
            continue
        sku_key = str(entry.get("sku_key") or "").strip()
        unit = str(entry.get("unit") or "").strip()
        price = entry.get("price_usd")
        if not sku_key or not unit or not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
            warnings.append(f"Ignored invalid unit_prices entry in {path.name}: sku_key={sku_key!r}")
            continue
        resolved[sku_key] = {"price_usd": float(price), "unit": unit}
    return resolved, warnings


def _build_pricing_request(domain: str, skus: list[dict[str, Any]], work_dir: Path | None) -> dict[str, Any] | None:
    """Build the minimal SKU-identifying request for a public-pricing lookup.

    ``work_dir`` is accepted for call-site compatibility but is not used --
    the required output is always the shared cross-scenario cache path (see
    module docstring), not a per-scenario file.
    """
    if not skus:
        return None
    required_output = _pricing_cache_path(domain)
    return {
        "schema_version": "1.0",
        "domain": domain,
        "status": "needs_pricing_model",
        "required_output": str(required_output),
        "output_contract": {
            "schema": "schemas/pricing-model.schema.json",
            "required_top_level": ["schema_version", "domain", "pricing_source", "unit_prices"],
            "note": (
                "Supply a raw AWS public on-demand unit price per sku_key using "
                "mcp__aws-pricing__get_pricing. This file is a SHARED cache across "
                "every scenario for this domain -- if it already exists, read it "
                "and merge new sku_key entries into its unit_prices list rather "
                "than overwriting existing ones. Do not compute savings in this "
                "artifact; the domain analyzer or complex-domain Skill performs "
                "the arithmetic. See references/pricing-policy.md."
            ),
        },
        "skus": skus,
    }
