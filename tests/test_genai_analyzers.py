import json
from pathlib import Path
import tempfile
import unittest

from cloudsweep.graph import run_graph


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class GenAIAnalyzerTests(unittest.TestCase):
    def test_bedrock_commitment_and_underutilization_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            _write_json(
                work_dir / "genai_evidence.json",
                {
                    "schema_version": "1.0",
                    "metadata": {
                        "period_start": "2026-05-01",
                        "period_end": "2026-05-30",
                        "period_days": 30,
                        "resolution": "daily",
                        "region": "us-east-1",
                        "currency": "USD",
                    },
                    "resources": {
                        "steady-on-demand": {
                            "service": "bedrock",
                            "resource_type": "aws_bedrock_model_usage",
                            "model_id": "test.steady-model",
                            "configuration": {
                                "committed_capacity_exists": False,
                                "model_region_supports_commitment": True,
                                "latency_or_throughput_need": True,
                                "committed_units": 1,
                                "committed_tokens_per_minute": 120000,
                                "committed_hours_per_month": 730,
                            },
                            "metrics": {
                                "input_tokens": {"unit": "Count", "datapoints": [4000000] * 30},
                                "output_tokens": {"unit": "Count", "datapoints": [500000] * 30},
                                "requests": {"unit": "Count", "datapoints": [4000] * 30},
                                "traffic_tokens_per_minute": {"unit": "Count/Minute", "datapoints": [90000] * 30},
                            },
                            "costs": {
                                "input_price_per_1m_tokens": 3.0,
                                "output_price_per_1m_tokens": 15.0,
                                "hourly_price_per_unit": 0.4,
                            },
                        },
                        "idle-commitment": {
                            "service": "bedrock",
                            "resource_type": "aws_bedrock_provisioned_model_throughput",
                            "model_id": "test.committed-model",
                            "configuration": {
                                "committed_capacity_exists": True,
                                "committed_units": 1,
                                "committed_tokens_per_minute": 100000,
                                "committed_hours_per_month": 730,
                            },
                            "metrics": {
                                "traffic_tokens_per_minute": {"unit": "Count/Minute", "datapoints": [20000] * 30}
                            },
                            "costs": {"hourly_price_per_unit": 1.0},
                        },
                    },
                },
            )

            state = run_graph(work_dir, write=False)

        findings = {finding["rule_id"]: finding for finding in state["findings"]}
        self.assertAlmostEqual(293.0, findings["BEDROCK_B1_THROUGHPUT_COMMIT"]["estimated_monthly_saving_usd"])
        self.assertAlmostEqual(584.0, findings["BEDROCK_B2_UNDERUTILIZED_COMMITMENT"]["estimated_monthly_saving_usd"])

    def test_sagemaker_terraform_autoscaling_matching(self):
        base_tf = """
resource "aws_sagemaker_endpoint_configuration" "orders" {
  name = "orders-config"

  production_variants {
    variant_name           = "AllTraffic"
    instance_type          = "ml.g5.xlarge"
    initial_instance_count = 2
  }
}

resource "aws_sagemaker_endpoint" "orders" {
  name                 = "orders"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.orders.name
}
"""
        target_tf = """
resource "aws_appautoscaling_target" "orders" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "endpoint/orders/variant/AllTraffic"
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  service_namespace  = "sagemaker"
}
"""

        policy_tf = """
resource "aws_appautoscaling_policy" "orders" {
  name               = "orders-target-tracking"
  policy_type        = "TargetTrackingScaling"
  resource_id        = "endpoint/orders/variant/AllTraffic"
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  service_namespace  = "sagemaker"
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            tf_path = work_dir / "main.tf"
            tf_path.write_text(base_tf, encoding="utf-8")
            without_scaling = run_graph(work_dir, write=False)
            tf_path.write_text(base_tf + target_tf, encoding="utf-8")
            with_target_only = run_graph(work_dir, write=False)
            tf_path.write_text(base_tf + target_tf + policy_tf, encoding="utf-8")
            with_scaling = run_graph(work_dir, write=False)

        without_rules = {finding["rule_id"] for finding in without_scaling["findings"]}
        target_only_rules = {finding["rule_id"] for finding in with_target_only["findings"]}
        with_rules = {finding["rule_id"] for finding in with_scaling["findings"]}
        self.assertIn("SAGEMAKER_SM1_MISSING_TARGET_TRACKING", without_rules)
        self.assertIn("SAGEMAKER_SM1_MISSING_TARGET_TRACKING", target_only_rules)
        self.assertNotIn("SAGEMAKER_SM1_MISSING_TARGET_TRACKING", with_rules)

    def test_ec2_gpu_asg_schedule_matching(self):
        base_tf = """
resource "aws_launch_template" "gpu" {
  name_prefix   = "gpu-training-"
  instance_type = "g5.xlarge"
}

resource "aws_autoscaling_group" "gpu" {
  desired_capacity   = 3
  min_size           = 0
  max_size           = 3
  off_hours_per_week = 70

  launch_template {
    id = aws_launch_template.gpu.id
  }
}
"""
        schedule_tf = """
resource "aws_autoscaling_schedule" "gpu_nights" {
  scheduled_action_name  = "gpu-nights"
  min_size               = 0
  max_size               = 0
  desired_capacity       = 0
  recurrence             = "0 20 * * MON-FRI"
  autoscaling_group_name = aws_autoscaling_group.gpu.name
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            tf_path = work_dir / "main.tf"
            tf_path.write_text(base_tf, encoding="utf-8")
            without_schedule = run_graph(work_dir, write=False)
            tf_path.write_text(base_tf + schedule_tf, encoding="utf-8")
            with_schedule = run_graph(work_dir, write=False)

        without_rules = {finding["rule_id"] for finding in without_schedule["findings"]}
        with_rules = {finding["rule_id"] for finding in with_schedule["findings"]}
        self.assertIn("EC2G1_UNSCHEDULED_ACCELERATOR", without_rules)
        self.assertIn("EC2G3_FIXED_GPU_ASG_CAPACITY", without_rules)
        self.assertIn("EC2G4_RESIDUAL_COSTS_UNKNOWN", without_rules)
        self.assertFalse(without_rules & with_rules)


if __name__ == "__main__":
    unittest.main()
