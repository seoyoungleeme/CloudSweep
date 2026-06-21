from pathlib import Path
import unittest

from cloudsweep.graph import ANALYZER_REGISTRY, run_graph


ROOT = Path(__file__).resolve().parents[1]


class AllDomainCoverageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
