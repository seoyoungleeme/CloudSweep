import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudsweep.graph import run_graph
from cloudsweep.pricing_models import (
    _build_pricing_request,
    _load_pricing_model_with_warnings,
)


class _IsolatedPricingCacheTestCase(unittest.TestCase):
    """Redirects the shared pricing cache to a throwaway tmp dir per test.

    The pricing model cache is intentionally shared across scenarios (see
    cloudsweep/pricing_models.py docstring), so tests must patch its location
    rather than reading/writing the real repo-level pricing_cache/ directory.
    """

    def setUp(self):
        self._cache_tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._cache_tmp.name) / "pricing_cache"
        patcher = patch("cloudsweep.pricing_models._pricing_cache_dir", return_value=self.cache_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._cache_tmp.cleanup)

    def _write_cache_model(self, domain: str, payload: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{domain}_pricing_model.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


class PricingModelLoaderTests(_IsolatedPricingCacheTestCase):
    def test_missing_file_returns_empty(self):
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({}, resolved)
        self.assertEqual([], warnings)

    def test_no_work_dir_returns_empty(self):
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({}, resolved)
        self.assertEqual([], warnings)

    def test_valid_model_resolves_by_sku_key(self):
        self._write_cache_model(
            "s3",
            {
                "schema_version": "1.0",
                "domain": "s3",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [
                    {"sku_key": "us-east-1|STANDARD", "unit": "GB-Mo", "price_usd": 0.023},
                ],
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual([], warnings)
        self.assertIn("us-east-1|STANDARD", resolved)
        self.assertEqual(0.023, resolved["us-east-1|STANDARD"]["price_usd"])
        self.assertEqual("GB-Mo", resolved["us-east-1|STANDARD"]["unit"])

    def test_wrong_domain_is_ignored(self):
        self._write_cache_model(
            "lambda",
            {
                "schema_version": "1.0",
                "domain": "s3",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [{"sku_key": "x", "unit": "y", "price_usd": 1.0}],
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "lambda")
        self.assertEqual({}, resolved)
        self.assertTrue(any("schema domain did not match" in warning for warning in warnings))

    def test_wrong_schema_version_is_ignored(self):
        self._write_cache_model(
            "s3",
            {
                "schema_version": "2.0",
                "domain": "s3",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [],
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({}, resolved)
        self.assertTrue(any("schema_version" in warning for warning in warnings))

    def test_wrong_pricing_source_is_ignored(self):
        self._write_cache_model(
            "s3",
            {
                "schema_version": "1.0",
                "domain": "s3",
                "pricing_source": "guessed",
                "unit_prices": [],
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({}, resolved)
        self.assertTrue(any("pricing_source" in warning for warning in warnings))

    def test_non_list_unit_prices_is_ignored(self):
        self._write_cache_model(
            "s3",
            {
                "schema_version": "1.0",
                "domain": "s3",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": "not-a-list",
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({}, resolved)
        self.assertTrue(any("unit_prices must be a list" in warning for warning in warnings))

    def test_invalid_entries_are_skipped_valid_entries_kept(self):
        self._write_cache_model(
            "s3",
            {
                "schema_version": "1.0",
                "domain": "s3",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [
                    {"sku_key": "", "unit": "GB-Mo", "price_usd": 0.023},
                    {"sku_key": "us-east-1|STANDARD", "unit": "", "price_usd": 0.023},
                    {"sku_key": "us-east-1|IA", "unit": "GB-Mo", "price_usd": -1.0},
                    {"sku_key": "us-east-1|VALID", "unit": "GB-Mo", "price_usd": 0.01},
                ],
            },
        )
        resolved, warnings = _load_pricing_model_with_warnings(None, "s3")
        self.assertEqual({"us-east-1|VALID": {"price_usd": 0.01, "unit": "GB-Mo"}}, resolved)
        self.assertEqual(3, len(warnings))

    def test_build_pricing_request_returns_none_for_empty_skus(self):
        self.assertIsNone(_build_pricing_request("s3", [], None))

    def test_build_pricing_request_shape(self):
        skus = [{"sku_key": "us-east-1|STANDARD", "service_code": "AmazonS3", "region": "us-east-1", "storage_class": "STANDARD", "unit": "GB-Mo"}]
        request = _build_pricing_request("s3", skus, None)
        self.assertEqual("1.0", request["schema_version"])
        self.assertEqual("s3", request["domain"])
        self.assertEqual("needs_pricing_model", request["status"])
        self.assertEqual("schemas/pricing-model.schema.json", request["output_contract"]["schema"])
        self.assertEqual(skus, request["skus"])

    def test_build_pricing_request_points_at_shared_cache_not_work_dir(self):
        skus = [{"sku_key": "us-east-1|STANDARD", "unit": "GB-Mo"}]
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            request = _build_pricing_request("s3", skus, work_dir)
        self.assertEqual(str(self.cache_dir / "s3_pricing_model.json"), request["required_output"])
        self.assertNotIn(str(work_dir), request["required_output"])


class PricingRequestIntegrationTests(_IsolatedPricingCacheTestCase):
    def test_pricing_request_not_emitted_when_quantity_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_s3_bucket" "orphan_dump" {
  bucket = "orphan-dump"
  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            state = run_graph(work_dir, write=False)
        self.assertNotIn("s3", state.get("pricing_requests", {}))
        s3_findings = [finding for finding in state["findings"] if finding["domain"] == "s3"]
        self.assertTrue(s3_findings)
        self.assertTrue(all(finding["pricing_source"] == "unmeasured" for finding in s3_findings))

    def test_pricing_request_emitted_when_quantity_exists_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_s3_bucket" "orphan_dump" {
  bucket = "orphan-dump"
  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            (work_dir / "parsed_input.json").write_text(
                json.dumps({"resources": {"orphan_dump": {"configuration": {"bucket_size_gb": 200}}}}),
                encoding="utf-8",
            )
            state = run_graph(work_dir, write=False)
        self.assertIn("s3", state.get("pricing_requests", {}))
        request = state["pricing_requests"]["s3"]
        self.assertEqual("us-east-1|STANDARD", request["skus"][0]["sku_key"])
        # required_output is the shared cache path, not scoped to this scenario's work_dir.
        self.assertEqual(str(self.cache_dir / "s3_pricing_model.json"), request["required_output"])
        self.assertNotIn(str(work_dir), request["required_output"])

    def test_pricing_request_not_emitted_once_model_resolves_every_sku(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_s3_bucket" "orphan_dump" {
  bucket = "orphan-dump"
  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            (work_dir / "parsed_input.json").write_text(
                json.dumps({"resources": {"orphan_dump": {"configuration": {"bucket_size_gb": 200}}}}),
                encoding="utf-8",
            )
            self._write_cache_model(
                "s3",
                {
                    "schema_version": "1.0",
                    "domain": "s3",
                    "pricing_source": "aws_public_pricing_model",
                    "unit_prices": [
                        {"sku_key": "us-east-1|STANDARD", "unit": "GB-Mo", "price_usd": 0.023},
                    ],
                },
            )
            state = run_graph(work_dir, write=False)
        self.assertNotIn("s3", state.get("pricing_requests", {}))
        s3_findings = [finding for finding in state["findings"] if finding["domain"] == "s3"]
        self.assertTrue(s3_findings)
        self.assertTrue(all(finding["pricing_source"] == "aws_public_pricing_model" for finding in s3_findings))
        self.assertTrue(all(finding["estimated_monthly_saving_usd"] > 0.0 for finding in s3_findings))

    def test_pricing_request_uses_provider_region_when_metadata_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''provider "aws" {
  region = "ap-northeast-2"
}

resource "aws_s3_bucket" "orphan_dump" {
  bucket = "orphan-dump"
  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            (work_dir / "parsed_input.json").write_text(
                json.dumps({"resources": {"orphan_dump": {"configuration": {"bucket_size_gb": 200}}}}),
                encoding="utf-8",
            )
            state = run_graph(work_dir, write=False)

        self.assertEqual("ap-northeast-2|STANDARD", state["pricing_requests"]["s3"]["skus"][0]["sku_key"])

    def test_arm64_lambda_without_arm_static_price_requests_model_instead_of_using_x86_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_lambda_function" "arm_worker" {
  function_name  = "arm-worker"
  role           = "arn:aws:iam::000000000000:role/lambda-role"
  handler        = "handler.handler"
  runtime        = "python3.12"
  memory_size    = 2048
  architectures  = ["arm64"]
}
''',
                encoding="utf-8",
            )
            (work_dir / "metrics.json").write_text(
                json.dumps(
                    {
                        "resources": {
                            "arm_worker": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {
                                    "memory_used_mb": {"datapoints": [400, 400]},
                                    "invocations": {"datapoints": [100000, 100000]},
                                    "duration": {"datapoints": [100, 100]},
                                },
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        finding = next(finding for finding in state["findings"] if finding["domain"] == "lambda")
        self.assertEqual("unmeasured", finding["pricing_source"])
        self.assertEqual(0.0, finding["estimated_monthly_saving_usd"])
        self.assertEqual("us-east-1|arm64", state["pricing_requests"]["lambda"]["skus"][0]["sku_key"])

    def test_complex_domains_emit_public_pricing_requests(self):
        scenarios = {
            "rds": (
                '''resource "aws_db_instance" "analytics" {
  identifier     = "analytics"
  engine         = "postgres"
  instance_class = "db.r5.xlarge"
  multi_az       = true
}
''',
                "us-east-1|postgres|db.r5.xlarge|multi_az",
            ),
            "elb": (
                '''resource "aws_lb" "app" {
  name               = "app"
  load_balancer_type = "application"
}
''',
                "us-east-1|application|load_balancer_hour",
            ),
            "ecs": (
                '''resource "aws_ecs_service" "api" {
  name         = "api"
  launch_type  = "FARGATE"
  desired_count = 2
}
''',
                "us-east-1|fargate|linux|x86_64|vcpu_hour",
            ),
            "elasticache": (
                '''resource "aws_elasticache_replication_group" "cache" {
  replication_group_id = "cache"
  engine               = "redis"
  node_type            = "cache.r6g.large"
  num_cache_clusters   = 3
}
''',
                "us-east-1|redis|cache.r6g.large|node_hour",
            ),
        }
        for domain, (terraform, expected_sku) in scenarios.items():
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as tmp:
                work_dir = Path(tmp)
                (work_dir / "main.tf").write_text(terraform, encoding="utf-8")

                state = run_graph(work_dir, write=False)

                self.assertIn(domain, state.get("pricing_requests", {}))
                self.assertIn(domain, state.get("skill_requests", {}))
                sku_keys = {sku["sku_key"] for sku in state["pricing_requests"][domain]["skus"]}
                self.assertIn(expected_sku, sku_keys)
                bundle_pricing = state["skill_requests"][domain]["evidence_bundle"]["pricing"]
                unresolved = {sku["sku_key"] for sku in bundle_pricing["unresolved_skus"]}
                self.assertEqual(sku_keys, unresolved)

    def test_complex_skill_request_embeds_public_pricing_model_when_resolved(self):
        self._write_cache_model(
            "rds",
            {
                "schema_version": "1.0",
                "domain": "rds",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [
                    {
                        "sku_key": "us-east-1|postgres|db.r5.xlarge|multi_az",
                        "unit": "InstanceHour",
                        "price_usd": 1.0,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.xlarge|single_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.5,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.large|multi_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.5,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.large|single_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.25,
                    },
                ],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "analytics" {
  identifier     = "analytics"
  engine         = "postgres"
  instance_class = "db.r5.xlarge"
  multi_az       = true
}
''',
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertNotIn("rds", state.get("pricing_requests", {}))
        pricing = state["skill_requests"]["rds"]["evidence_bundle"]["pricing"]
        self.assertEqual([], pricing["unresolved_skus"])
        self.assertEqual("aws_public_pricing_model", pricing["pricing_model"]["pricing_source"])
        resolved = {entry["sku_key"]: entry["price_usd"] for entry in pricing["pricing_model"]["unit_prices"]}
        self.assertEqual(1.0, resolved["us-east-1|postgres|db.r5.xlarge|multi_az"])
        self.assertEqual(0.25, resolved["us-east-1|postgres|db.r5.large|single_az"])

    def test_complex_public_pricing_model_triggers_skill_reanalysis_for_static_findings(self):
        self._write_cache_model(
            "rds",
            {
                "schema_version": "1.0",
                "domain": "rds",
                "pricing_source": "aws_public_pricing_model",
                "unit_prices": [
                    {
                        "sku_key": "us-east-1|postgres|db.r5.xlarge|multi_az",
                        "unit": "InstanceHour",
                        "price_usd": 1.0,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.xlarge|single_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.5,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.large|multi_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.5,
                    },
                    {
                        "sku_key": "us-east-1|postgres|db.r5.large|single_az",
                        "unit": "InstanceHour",
                        "price_usd": 0.25,
                    },
                ],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "analytics" {
  identifier     = "analytics"
  engine         = "postgres"
  instance_class = "db.r5.xlarge"
  multi_az       = true
}
''',
                encoding="utf-8",
            )
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / ".machine").mkdir()
            (result_dir / ".machine" / "rds_skill_analysis.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "domain": "rds",
                        "findings": [
                            {
                                "rule_id": "RDS_R1_NONPROD_MULTI_AZ",
                                "resource": "analytics",
                                "severity": "MEDIUM",
                                "confidence": "LOW",
                                "estimated_monthly_saving_usd": 365.0,
                                "pricing_source": "static_fallback_estimate",
                                "evidence": ["pricing_source=static_fallback_estimate"],
                                "recommendation": "Validate SLA before disabling Multi-AZ.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertEqual(1, len(state["findings"]))
        self.assertEqual("static_fallback_estimate", state["findings"][0]["pricing_source"])
        self.assertNotIn("rds", state.get("pricing_requests", {}))
        self.assertIn("rds", state.get("skill_requests", {}))
        self.assertEqual("needs_skill_reanalysis", state["skill_requests"]["rds"]["status"])
        pricing = state["skill_requests"]["rds"]["evidence_bundle"]["pricing"]
        self.assertTrue(pricing["pricing_model"]["unit_prices"])


if __name__ == "__main__":
    unittest.main()
