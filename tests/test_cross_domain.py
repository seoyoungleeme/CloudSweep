import unittest

from cloudsweep.cross_domain import _build_dependency_facts, _cross_domain_analysis


class CrossDomainReviewTests(unittest.TestCase):
    def test_llm_tco_note_requires_findings_on_both_platforms(self):
        notes, _, _ = _cross_domain_analysis(
            {"bedrock", "ec2"},
            [
                {
                    "domain": "bedrock",
                    "resource": "model",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": 100.0,
                }
            ],
            {},
            [],
        )

        self.assertNotIn("both have findings", "\n".join(notes))

        notes, _, _ = _cross_domain_analysis(
            {"bedrock", "ec2"},
            [
                {
                    "domain": "bedrock",
                    "resource": "model",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": 100.0,
                },
                {
                    "domain": "ec2",
                    "resource": "gpu",
                    "confidence": "HIGH",
                    "estimated_monthly_saving_usd": 250.0,
                },
            ],
            {},
            [],
        )

        self.assertIn("both have findings", "\n".join(notes))

    def test_amplification_notes_require_matching_resource_findings(self):
        facts = [
            {
                "kind": "retry_amplification_ratio",
                "resource": "worker",
                "value": 2.0,
            },
            {
                "kind": "request_invocation_ratio",
                "resource": "worker",
                "value": 4.0,
            },
        ]

        notes, annotated, hypotheses = _cross_domain_analysis({"lambda"}, [], {}, facts)
        self.assertEqual(["No cross-domain risk pattern detected from available evidence."], notes)
        self.assertEqual([], annotated)
        self.assertEqual([], hypotheses)

        notes, annotated, hypotheses = _cross_domain_analysis(
            {"lambda"},
            [{"domain": "lambda", "resource": "worker", "confidence": "HIGH"}],
            {},
            facts,
        )

        joined = "\n".join(notes)
        self.assertIn("retry_amplification_ratio=2.0", joined)
        self.assertIn("request_invocation_ratio=4.0", joined)
        refs = annotated[0]["cross_domain_refs"]
        self.assertEqual({"retry_amplification", "request_amplification"}, {ref["kind"] for ref in refs})
        self.assertEqual([], hypotheses)

    def test_cache_hit_rate_accepts_percent_and_fraction_units(self):
        finding = {"domain": "rds", "resource": "db", "confidence": "HIGH"}
        for value in (75, 0.75):
            with self.subTest(value=value):
                notes, annotated, _ = _cross_domain_analysis(
                    {"elasticache", "rds"},
                    [finding],
                    {},
                    [{"kind": "cache_hit_rate_pct", "resource": "cache", "value": value}],
                )
                self.assertIn("ElastiCache hit rate < 80%", "\n".join(notes))
                self.assertEqual("cache_miss_amplification", annotated[0]["cross_domain_refs"][0]["kind"])

        notes, annotated, _ = _cross_domain_analysis(
            {"elasticache", "rds"},
            [finding],
            {},
            [{"kind": "cache_hit_rate_pct", "resource": "cache", "value": 91}],
        )
        self.assertNotIn("ElastiCache hit rate < 80%", "\n".join(notes))
        self.assertNotIn("cross_domain_refs", annotated[0])

    def test_cache_hit_rate_dependency_fact_is_normalized_to_percent(self):
        facts = _build_dependency_facts(
            run_id="run",
            terraform_path=None,
            resources={
                "cache": {
                    "metrics": {
                        "cache_hit_rate": {
                            "datapoints": [0.7, 0.8],
                        }
                    }
                }
            },
            read_text=lambda path: "",
        )

        self.assertEqual(75.0, facts[0]["value"])

    def test_cost_spike_service_names_use_domain_aliases(self):
        notes, _, _ = _cross_domain_analysis(
            {"ec2"},
            [{"domain": "ec2", "resource": "gpu", "confidence": "HIGH"}],
            {
                "spikes": [{"timestamp": "2026-06-25T00:00:00Z"}],
                "drilldown": [
                    {"services": [{"service": "Amazon Elastic Compute Cloud"}]},
                ],
            },
            [],
        )

        self.assertIn("overlap in ec2", "\n".join(notes))

    def test_log_group_association_fact_drives_cloudwatch_cross_domain_note(self):
        facts = _build_dependency_facts(
            run_id="run",
            terraform_path=None,
            resources={
                "worker": {
                    "service": "lambda",
                    "resource_type": "aws_lambda_function",
                    "configuration": {"function_name": "orders-worker"},
                    "metrics": {},
                },
                "worker_log_group": {
                    "service": "cloudwatch",
                    "resource_type": "aws_cloudwatch_log_group",
                    "configuration": {"name": "/aws/lambda/orders-worker"},
                    "metrics": {},
                },
            },
            read_text=lambda path: "",
        )

        association = [fact for fact in facts if fact["kind"] == "log_group_association"]
        self.assertEqual(1, len(association))
        self.assertEqual("worker_log_group", association[0]["source"])
        self.assertEqual("worker", association[0]["target"])

        notes, annotated, hypotheses = _cross_domain_analysis(
            {"lambda", "cloudwatch"},
            [
                {"finding_id": "cw1", "domain": "cloudwatch", "resource": "worker_log_group"},
                {"finding_id": "lambda1", "domain": "lambda", "resource": "worker"},
            ],
            {},
            facts,
        )

        joined = "\n".join(notes)
        self.assertIn("associated with Lambda", joined)
        self.assertEqual([], hypotheses)
        by_resource = {finding["resource"]: finding for finding in annotated}
        self.assertEqual(
            "log_group_association",
            by_resource["worker_log_group"]["cross_domain_refs"][0]["kind"],
        )
        self.assertEqual(
            "log_group_association",
            by_resource["worker"]["cross_domain_refs"][0]["kind"],
        )

    def test_cloudwatch_and_compute_copresence_without_association_does_not_assert_verbosity(self):
        notes, annotated, hypotheses = _cross_domain_analysis(
            {"lambda", "cloudwatch"},
            [
                {"finding_id": "cw1", "domain": "cloudwatch", "resource": "unrelated_log_group"},
                {"finding_id": "lambda1", "domain": "lambda", "resource": "worker"},
            ],
            {},
            [],
        )

        self.assertEqual(["No cross-domain risk pattern detected from available evidence."], notes)
        self.assertFalse(any("cross_domain_refs" in finding for finding in annotated))
        self.assertEqual(1, len(hypotheses))
        self.assertEqual("hypothesis", hypotheses[0]["status"])


if __name__ == "__main__":
    unittest.main()
