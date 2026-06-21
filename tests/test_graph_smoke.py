import json
from pathlib import Path
import tempfile
import unittest

from cloudsweep.graph import _validate_genai_evidence, run_graph


ROOT = Path(__file__).resolve().parents[1]


class GraphSmokeTests(unittest.TestCase):
    def test_multi_domain_scenario_routes_and_finds_waste(self):
        state = run_graph(ROOT / "sample" / "season2" / "MA-001", write=False)

        self.assertIn("domain_analysis", state["execution_plan"])
        self.assertEqual({"lambda", "s3", "dynamodb"}, set(state["domains"]))
        self.assertGreaterEqual(len(state["findings"]), 3)

    def test_anomaly_scenario_routes_to_anomaly_node(self):
        state = run_graph(ROOT / "sample" / "season2" / "LV-001", write=False)

        self.assertIn("anomaly_analysis", state["execution_plan"])
        self.assertGreaterEqual(len(state["anomaly"]["spikes"]), 1)

    def test_genai_domains_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                """
resource "aws_bedrock_provisioned_model_throughput" "claude_commit" {
  provisioned_model_name = "orders-chat"
}

resource "aws_sagemaker_endpoint" "realtime_gpu" {
  name = "orders-realtime"
}

resource "aws_instance" "trainer" {
  ami           = "ami-12345678"
  instance_type = "g5.xlarge"
}
""",
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertIn("domain_analysis", state["execution_plan"])
        self.assertEqual({"bedrock", "sagemaker", "ec2"}, set(state["domains"]))
        self.assertFalse(any("No built-in graph analyzer" in warning for warning in state["warnings"]))

    def test_genai_evidence_routes_without_terraform(self):
        work_dir = ROOT / "sample" / "season2" / "GENAI-001"
        evidence = json.loads((work_dir / "genai_evidence.json").read_text(encoding="utf-8"))
        state = run_graph(work_dir, write=False)

        self.assertEqual([], _validate_genai_evidence(evidence))
        self.assertIsNone(state["evidence"]["terraform"])
        self.assertIn("domain_analysis", state["execution_plan"])
        self.assertEqual({"bedrock", "sagemaker", "ec2"}, set(state["domains"]))
        self.assertIn("orders-assistant", state["domain_resources"]["bedrock"])
        self.assertIn("orders-realtime", state["domain_resources"]["sagemaker"])
        self.assertIn("training-gpu", state["domain_resources"]["ec2"])
        rules = {finding["rule_id"] for finding in state["findings"]}
        self.assertIn("BEDROCK_B3_MISSING_PROMPT_CACHE", rules)
        self.assertIn("BEDROCK_B4_MISSING_SEMANTIC_CACHE", rules)
        self.assertIn("SAGEMAKER_SM1_MISSING_TARGET_TRACKING", rules)
        self.assertIn("SAGEMAKER_SM2_MISSING_SCHEDULED_SCALING", rules)
        self.assertIn("SAGEMAKER_SM3_GPU_UNDERUTILIZED", rules)
        self.assertIn("SAGEMAKER_SM4_BURSTY_ALWAYS_ON_ENDPOINT", rules)
        self.assertIn("EC2G2_IDLE_DEV_TRAINING_ACCELERATOR", rules)
        for finding in state["findings"]:
            if finding["rule_id"] != "SAGEMAKER_SM4_BURSTY_ALWAYS_ON_ENDPOINT":
                self.assertGreater(finding["estimated_monthly_saving_usd"], 0)
        self.assertIn("Conservative estimated monthly savings: **$1786.19**", state["report_markdown"])

    def test_invalid_genai_evidence_is_reported_without_stopping_the_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "genai_evidence.json").write_text(
                """
{
  "schema_version": "0.9",
  "metadata": {},
  "resources": {
    "chat": {
      "service": "bedrock",
      "resource_type": "aws_bedrock_model_usage",
      "configuration": {},
      "metrics": {"input_tokens": {"unit": "Count", "datapoints": [true]}}
    }
  }
}
""",
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertIn("bedrock", state["domains"])
        self.assertTrue(any("Invalid GenAI evidence" in warning for warning in state["warnings"]))

    def test_metrics_and_cost_report_route_without_terraform(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "metrics.json").write_text(
                """
{
  "resources": {
    "chat": {
      "service": "bedrock",
      "resource_type": "aws_bedrock_model_usage",
      "metrics": {}
    }
  }
}
""",
                encoding="utf-8",
            )
            (work_dir / "cost_report.json").write_text(
                """
{
  "period_months": 1,
  "monthly_data": [
    {"services": [{"service": "Amazon SageMaker AI", "spend_usd": 100.0}]}
  ]
}
""",
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertIn("domain_analysis", state["execution_plan"])
        self.assertEqual({"bedrock", "sagemaker"}, set(state["domains"]))

    def test_parsed_input_routes_without_terraform(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "parsed_input.json").write_text(
                """
{
  "tf_resources": [
    {
      "resource_id": "training-host",
      "resource_type": "aws_instance",
      "service": "ec2",
      "instance_type": "g5.xlarge"
    }
  ]
}
""",
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=False)

        self.assertIn("domain_analysis", state["execution_plan"])
        self.assertEqual(["ec2"], state["domains"])


if __name__ == "__main__":
    unittest.main()
