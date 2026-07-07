import json
import shutil
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from cloudsweep.complex_domains import (
    _COMPLEX_DOMAINS,
    _load_skill_analysis,
    _load_skill_analysis_with_warnings,
)
from cloudsweep.graph import ANALYZER_REGISTRY, run_graph


ROOT = Path(__file__).resolve().parents[1]

_SIMPLE_SKILL_DIRS = {
    p.parent.name
    for p in (ROOT / ".claude" / "skills").glob("finops-*/SKILL.md")
    if p.parent.name not in {f"finops-{d}" for d in _COMPLEX_DOMAINS}
}
_COMPLEX_SKILL_DIRS = {f"finops-{d}" for d in _COMPLEX_DOMAINS}


class AllDomainCoverageTests(unittest.TestCase):
    def setUp(self):
        # The pricing model cache (cloudsweep/pricing_models.py) is shared
        # across scenarios by design, so it must not leak the real repo-level
        # pricing_cache/ into tests. Default every test in this class to an
        # empty, isolated cache dir; tests that need specific cached prices
        # override with their own `with patch(...)` block around run_graph.
        self._pricing_cache_tmp = tempfile.TemporaryDirectory()
        patcher = patch(
            "cloudsweep.pricing_models._pricing_cache_dir",
            return_value=Path(self._pricing_cache_tmp.name) / "pricing_cache",
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._pricing_cache_tmp.cleanup)

    def test_every_declared_domain_has_analyzer(self):
        expected = {
            "lambda", "s3", "dynamodb", "bedrock", "sagemaker", "ec2",
            "ebs", "elb", "rds", "cloudwatch", "cloudwatch-alarm", "sqs",
            "kinesis", "ecs", "elasticache", "nat", "tgw", "organizations",
        }
        self.assertEqual(expected, set(ANALYZER_REGISTRY.domains()))

    def test_all_season1_scenarios_have_implemented_coverage(self):
        scenarios = sorted((ROOT / "sample" / "season1").iterdir())
        for scenario in scenarios:
            if not scenario.is_dir() or not (scenario / "main.tf").exists():
                continue
            with self.subTest(scenario=scenario.name):
                state = run_graph(scenario, write=False)
                self.assertTrue(state["analyzer_coverage"])
                self.assertTrue(all(item["status"] == "implemented" for item in state["analyzer_coverage"]))
                self.assertTrue(all(finding.get("finding_id") for finding in state["findings"]))
                self.assertTrue(all(finding.get("evidence_facts") is not None for finding in state["findings"]))

    def test_simple_and_genai_skills_are_review_only(self):
        """Non-complex skills must not contain analysis logic; review only."""
        for skill_dir in sorted(_SIMPLE_SKILL_DIRS):
            skill_path = ROOT / ".claude" / "skills" / skill_dir / "SKILL.md"
            if not skill_path.exists():
                continue
            with self.subTest(skill=skill_dir):
                text = skill_path.read_text(encoding="utf-8")
                self.assertIn("Review-only authority", text, f"{skill_dir} should be review-only")
                self.assertIn("LangGraph owns", text)
                self.assertNotIn("## Detection Rules", text)

    def test_complex_skills_have_analysis_and_output_contract(self):
        """Complex domain skills must declare detection rules and an output contract."""
        for skill_dir in sorted(_COMPLEX_SKILL_DIRS):
            skill_path = ROOT / ".claude" / "skills" / skill_dir / "SKILL.md"
            with self.subTest(skill=skill_dir):
                self.assertTrue(skill_path.exists(), f"{skill_dir}/SKILL.md missing")
                text = skill_path.read_text(encoding="utf-8")
                self.assertIn("Detection Rules", text, f"{skill_dir} must have detection rules")
                self.assertIn("Modeled Savings And Pricing Source", text, f"{skill_dir} must define pricing waterfall")
                self.assertIn("Output Contract", text, f"{skill_dir} must declare output contract")
                self.assertIn("skill_analysis.json", text, f"{skill_dir} must reference skill_analysis.json")
                self.assertIn("pricing_source", text, f"{skill_dir} must emit pricing_source")
                self.assertNotIn("Review-only authority", text, f"{skill_dir} must not be review-only")

    def test_skill_analysis_schema_accepts_reasonable_estimate_metadata(self):
        schema = json.loads((ROOT / "schemas" / "skill-analysis.schema.json").read_text(encoding="utf-8"))
        finding_props = schema["properties"]["findings"]["items"]["properties"]
        self.assertIn("reasonable_estimate", finding_props["pricing_source"]["enum"])
        self.assertEqual(["HIGH", "MEDIUM", "LOW"], finding_props["pricing_confidence"]["enum"])
        self.assertIn("reasonable_estimate", finding_props["savings_status"]["enum"])
        self.assertIn("savings_reason", finding_props)
        self.assertIn("display_name", finding_props)

    def test_legacy_skill_scripts_are_removed(self):
        legacy_scripts = sorted((ROOT / ".claude" / "skills").glob("finops-*/scripts/*.py"))
        self.assertEqual([], legacy_scripts)

    def test_dependency_facts_are_deterministic_and_typed(self):
        scenario = ROOT / "sample" / "season2" / "MA-001"
        first = run_graph(scenario, write=False)["dependency_facts"]
        second = run_graph(scenario, write=False)["dependency_facts"]
        self.assertEqual(first, second)
        terraform_refs = [fact for fact in first if fact["kind"] == "terraform_reference"]
        self.assertTrue(terraform_refs)
        self.assertTrue(all(fact["source"].startswith("aws_") for fact in terraform_refs))

        cache_state = run_graph(ROOT / "sample" / "season1" / "L2-019", write=False)
        cache_facts = [fact for fact in cache_state["dependency_facts"] if fact["kind"] == "cache_hit_rate_pct"]
        self.assertTrue(cache_facts)

    def test_s3_lifecycle_candidate_expansion_uses_nonprod_and_name_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_s3_bucket" "deprecated_frontend_assets" {
  bucket = "deprecated-frontend-assets"
}

resource "aws_s3_bucket" "dev_scratch" {
  bucket = "dev-scratch"
  tags = {
    Environment = "development"
  }
}

resource "aws_s3_bucket" "prod_access_logs" {
  bucket = "prod-access-logs"
  tags = {
    Environment = "production"
  }
}

resource "aws_s3_bucket" "prod_application_logs" {
  bucket = "prod-application-logs"
  tags = {
    Environment = "production"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "prod_application_logs_lifecycle" {
  bucket = aws_s3_bucket.prod_application_logs.id
}
''',
                encoding="utf-8",
            )
            (work_dir / "parsed_input.json").write_text(
                json.dumps(
                    {
                        "resources": {
                            "deprecated_frontend_assets": {
                                "configuration": {"bucket_size_gb": 500},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        s3_findings = [finding for finding in state["findings"] if finding["domain"] == "s3"]
        by_resource = {finding["resource"]: finding for finding in s3_findings}
        self.assertIn("deprecated_frontend_assets", by_resource)
        self.assertIn("dev_scratch", by_resource)
        self.assertIn("prod_access_logs", by_resource)
        self.assertNotIn("prod_application_logs", by_resource)

        # No cost_report anywhere in this scenario. deprecated_frontend_assets has
        # bucket_size_gb evidence, so it prices via the static rule fallback tier
        # (non-zero, pricing confidence LOW) instead of locking to $0.
        priced = by_resource["deprecated_frontend_assets"]
        self.assertEqual("static_fallback_estimate", priced["pricing_source"])
        self.assertEqual("MEDIUM", priced["confidence"])
        self.assertEqual("LOW", priced["pricing_confidence"])
        self.assertEqual("priced", priced["savings_status"])
        self.assertGreater(priced["estimated_monthly_saving_usd"], 0.0)

        # dev_scratch and prod_access_logs have no quantity evidence at all, so
        # they stay unmeasured/$0.00 while candidate confidence remains based on
        # lifecycle signals.
        self.assertEqual("unmeasured", by_resource["dev_scratch"]["pricing_source"])
        self.assertEqual("MEDIUM", by_resource["dev_scratch"]["confidence"])
        self.assertEqual("LOW", by_resource["dev_scratch"]["pricing_confidence"])
        self.assertEqual("bucket_size_not_observed", by_resource["dev_scratch"]["savings_reason"])
        self.assertEqual(0.0, by_resource["dev_scratch"]["estimated_monthly_saving_usd"])
        self.assertEqual("unmeasured", by_resource["prod_access_logs"]["pricing_source"])
        self.assertEqual("LOW", by_resource["prod_access_logs"]["confidence"])
        self.assertEqual("bucket_size_not_observed", by_resource["prod_access_logs"]["savings_reason"])
        self.assertEqual(0.0, by_resource["prod_access_logs"]["estimated_monthly_saving_usd"])

    def test_lambda_rightsizing_thresholds_and_metric_inconsistency_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_lambda_function" "threshold_25" {
  function_name = "threshold-25"
  role          = "arn:aws:iam::000000000000:role/lambda-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 1024
}

resource "aws_lambda_function" "waste_relaxed" {
  function_name = "waste-relaxed"
  role          = "arn:aws:iam::000000000000:role/lambda-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 2048
}

resource "aws_lambda_function" "waste_log_forwarder" {
  function_name = "waste-log-forwarder"
  role          = "arn:aws:iam::000000000000:role/lambda-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 1024
}

resource "aws_lambda_function" "bad_metric" {
  function_name = "bad-metric"
  role          = "arn:aws:iam::000000000000:role/lambda-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 1024
}

resource "aws_lambda_function" "bad_small_metric" {
  function_name = "bad-small-metric"
  role          = "arn:aws:iam::000000000000:role/lambda-role"
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 256
}
''',
                encoding="utf-8",
            )
            (work_dir / "metrics.json").write_text(
                json.dumps(
                    {
                        "resources": {
                            "threshold_25": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {"memory_used_mb": {"datapoints": [256, 256]}},
                            },
                            "waste_relaxed": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {
                                    "memory_used_mb": {"datapoints": [700, 700]},
                                    "invocations": {"datapoints": [500000, 500000]},
                                    "duration": {"datapoints": [100, 100]},
                                },
                            },
                            "waste_log_forwarder": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {"memory_used_mb": {"datapoints": [400, 400]}},
                            },
                            "bad_metric": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {"memory_used_mb": {"datapoints": [1200, 1200]}},
                            },
                            "bad_small_metric": {
                                "service": "lambda",
                                "resource_type": "aws_lambda_function",
                                "metrics": {"memory_used_mb": {"datapoints": [512, 512]}},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        lambda_findings = [finding for finding in state["findings"] if finding["domain"] == "lambda"]
        by_resource = {finding["resource"]: finding for finding in lambda_findings}
        self.assertIn("threshold_25", by_resource)
        self.assertIn("waste_relaxed", by_resource)
        self.assertNotIn("waste_log_forwarder", by_resource)
        self.assertNotIn("bad_metric", by_resource)
        self.assertNotIn("bad_small_metric", by_resource)
        self.assertTrue(any("metric inconsistency" in warning for warning in state["warnings"]))
        self.assertTrue(any("bad_small_metric" in warning for warning in state["warnings"]))

        # No cost_report anywhere in this scenario. waste_relaxed has real
        # invocations/duration evidence, so it prices via the static rule
        # fallback tier (non-zero) instead of locking to $0.
        priced = by_resource["waste_relaxed"]
        self.assertEqual("static_fallback_estimate", priced["pricing_source"])
        self.assertEqual("LOW", priced["pricing_confidence"])
        self.assertEqual("priced", priced["savings_status"])
        self.assertGreater(priced["estimated_monthly_saving_usd"], 0.0)

        # threshold_25 has no invocations/duration evidence, so it stays
        # unmeasured/$0.00 while detection confidence remains MEDIUM.
        unpriced = by_resource["threshold_25"]
        self.assertEqual("unmeasured", unpriced["pricing_source"])
        self.assertEqual("MEDIUM", unpriced["confidence"])
        self.assertEqual("LOW", unpriced["pricing_confidence"])
        self.assertEqual("lambda_gb_seconds_not_observed", unpriced["savings_reason"])
        self.assertEqual(0.0, unpriced["estimated_monthly_saving_usd"])

    def test_rds_skill_unmeasured_downsize_can_be_reasonable_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "dev_analytics_db" {
  identifier     = "dev-analytics-db"
  engine         = "postgres"
  instance_class = "db.r5.xlarge"
  storage_type   = "gp2"
  multi_az       = true

  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / ".machine").mkdir()
            # The pricing model cache is shared across scenarios (see
            # cloudsweep/pricing_models.py), so it must be isolated to a tmp
            # dir here rather than written under this scenario's result/.
            cache_dir = work_dir / "pricing_cache"
            cache_dir.mkdir()
            (cache_dir / "rds_pricing_model.json").write_text(
                json.dumps(
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
                                "sku_key": "us-east-1|postgres|db.r5.large|multi_az",
                                "unit": "InstanceHour",
                                "price_usd": 0.5,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (result_dir / ".machine" / "rds_skill_analysis.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "domain": "rds",
                        "findings": [
                            {
                                "rule_id": "RDS_R2_LOW_UTILIZATION",
                                "resource": "dev_analytics_db",
                                "severity": "HIGH",
                                "confidence": "LOW",
                                "estimated_monthly_saving_usd": 0.0,
                                "pricing_source": "unmeasured",
                                "evidence": ["cpu_datapoints=4", "memory_iops_latency=not_available"],
                                "recommendation": "Needs evidence before downsizing.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch("cloudsweep.pricing_models._pricing_cache_dir", return_value=cache_dir):
                state = run_graph(work_dir, write=False)

        finding = state["findings"][0]
        self.assertEqual("reasonable_estimate", finding["pricing_source"])
        self.assertEqual("reasonable_estimate", finding["savings_status"])
        self.assertEqual("safety_or_target_pricing_evidence_missing", finding["savings_reason"])
        self.assertEqual("LOW", finding["pricing_confidence"])
        self.assertEqual(365.0, finding["estimated_monthly_saving_usd"])
        self.assertIn("Reasonable estimate upside: **$365.00**", state["report_markdown"])
        self.assertIn("Evidence-backed monthly savings: **$0.00**", state["report_markdown"])

    def test_complex_domain_skill_output_is_loaded_by_langgraph(self):
        """When skill_analysis.json exists, LangGraph loads authoritative Skill findings."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            skill_finding = {
                "rule_id": "RDS_R4_EXTENDED_SUPPORT",
                "resource": "my_db",
                "severity": "HIGH",
                "confidence": "HIGH",
                "estimated_monthly_saving_usd": 250.0,
                "pricing_source": "cost_report",
                "evidence": ["engine=mysql-5.7", "extended_support_active=true"],
                "recommendation": "Upgrade to mysql-8.0 to avoid Extended Support charges.",
                "optimized_replacement": None,
            }
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / ".machine").mkdir()
            (result_dir / ".machine" / "rds_skill_analysis.json").write_text(
                json.dumps({"schema_version": "1.0", "domain": "rds", "findings": [skill_finding]}),
                encoding="utf-8",
            )
            loaded = _load_skill_analysis(work_dir, "rds")
            self.assertEqual(1, len(loaded))
            self.assertEqual("RDS_R4_EXTENDED_SUPPORT", loaded[0]["rule_id"])
            self.assertEqual("rds", loaded[0]["domain"])
            self.assertEqual("claude_skill", loaded[0]["analysis_source"])
            self.assertEqual("skill_analyzed", loaded[0]["review_status"])
            self.assertEqual("cost_report", loaded[0]["pricing_source"])
            self.assertNotIn("optimized_replacement", loaded[0])

    def test_legacy_decisions_skill_schema_gets_specific_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / ".machine").mkdir()
            (result_dir / ".machine" / "rds_skill_analysis.json").write_text(
                json.dumps({"schema_version": "1.0", "domain": "rds", "decisions": []}),
                encoding="utf-8",
            )

            findings, warnings = _load_skill_analysis_with_warnings(work_dir, "rds")

        self.assertEqual([], findings)
        self.assertTrue(any("legacy decisions schema ignored" in warning for warning in warnings))

    def test_skill_analysis_domain_mismatch_is_ignored(self):
        """A skill_analysis.json with a wrong domain field must be silently skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / ".machine").mkdir()
            (result_dir / ".machine" / "elb_skill_analysis.json").write_text(
                json.dumps({"schema_version": "1.0", "domain": "rds", "findings": []}),
                encoding="utf-8",
            )
            loaded = _load_skill_analysis(work_dir, "elb")
            self.assertEqual([], loaded)

    def test_complex_domain_requires_skill_output_without_python_candidates(self):
        """Without Skill output, complex domains emit a request bundle but no findings."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "orders" {
  identifier     = "orders"
  engine         = "mysql"
  instance_class = "db.r5.large"
  storage_type   = "gp3"
  multi_az       = false
}
''',
                encoding="utf-8",
            )
            (work_dir / "cost_report.json").write_text(
                json.dumps(
                    {
                        "period_months": 1,
                        "monthly_data": [
                            {"services": [{"service": "RDS", "spend_usd": 1000.0}]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=True)
            request = json.loads(
                (work_dir / "result" / ".machine" / "rds_skill_request.json").read_text(encoding="utf-8")
            )
            report = (work_dir / "result" / "cloudsweep_graph_report.md").read_text(encoding="utf-8")

        self.assertEqual([], state["findings"])
        self.assertIn("rds", state["skill_requests"])
        self.assertEqual("needs_skill_analysis", request["status"])
        self.assertNotIn("candidates", request)
        self.assertIn("evidence_bundle", request)
        resources = request["evidence_bundle"]["terraform"]["resources"]
        self.assertEqual("db.r5.large", resources[0]["attributes"]["instance_class"])
        self.assertEqual(["metrics.json"], request["evidence_bundle"]["missing_evidence"])
        self.assertIn("Skill Analysis Required", report)

    def test_complex_domain_skill_output_is_authoritative_in_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "orders" {
  identifier     = "orders"
  engine         = "mysql"
  engine_version = "5.7"
  instance_class = "db.r5.large"
  storage_type   = "gp3"
  multi_az       = false

  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            (work_dir / "cost_report.json").write_text(
                json.dumps(
                    {
                        "period_months": 1,
                        "monthly_data": [
                            {"services": [{"service": "RDS", "spend_usd": 1000.0}]}
                        ],
                    }
                ),
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
                        "skill_version": "2.0",
                        "findings": [
                            {
                                "rule_id": "RDS_R4_EXTENDED_SUPPORT",
                                "resource": "orders",
                                "severity": "HIGH",
                                "confidence": "HIGH",
                                "estimated_monthly_saving_usd": 250.0,
                                "pricing_source": "static_fallback_estimate",
                                "evidence": ["engine_version requires Extended Support"],
                                "recommendation": "Upgrade during the confirmed maintenance window.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertEqual(1, len(state["findings"]))
        finding = state["findings"][0]
        self.assertEqual("claude_skill", finding["analysis_source"])
        self.assertEqual("skill_analyzed", finding["review_status"])
        self.assertEqual(250.0, finding["estimated_monthly_saving_usd"])
        self.assertEqual("static_fallback_estimate", finding["pricing_source"])
        self.assertEqual({}, state["skill_requests"])
        self.assertFalse(any("requires Skill analysis output" in warning for warning in state["warnings"]))


if __name__ == "__main__":
    unittest.main()
