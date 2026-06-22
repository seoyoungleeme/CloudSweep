import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cloudsweep.evidence_normalization import normalize_environment, normalize_metric_name
from cloudsweep.graph import main, run_graph
from cloudsweep.ministack_collector import READ_ONLY_OPERATIONS, collect_ministack


class _S3Client:
    def list_buckets(self):
        return {"Buckets": [{"Name": "archive-bucket"}]}

    def get_bucket_tagging(self, **kwargs):
        return {"TagSet": [{"Key": "Environment", "Value": "dev"}]}

    def get_bucket_lifecycle_configuration(self, **kwargs):
        raise RuntimeError("no lifecycle configured")


class _LambdaClient:
    def list_functions(self, **kwargs):
        return {
            "Functions": [
                {
                    "FunctionName": "orders-worker",
                    "FunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:orders-worker",
                    "Role": "arn:aws:iam::000000000000:role/lambda-role",
                    "Handler": "index.handler",
                    "Runtime": "python3.12",
                    "MemorySize": 2048,
                    "Timeout": 30,
                }
            ]
        }

    def list_tags(self, **kwargs):
        return {"Tags": {"Environment": "dev"}}


class _RDSClient:
    def describe_db_instances(self, **kwargs):
        raise RuntimeError("RDS is unavailable")


class _LogsClient:
    def describe_log_groups(self, **kwargs):
        return {"logGroups": [{"logGroupName": "/aws/lambda/orders-worker", "storedBytes": 1024}]}


class _CloudWatchClient:
    def describe_alarms(self, **kwargs):
        return {"MetricAlarms": []}

    def list_metrics(self, **kwargs):
        return {
            "Metrics": [
                {
                    "Namespace": "LambdaInsights",
                    "MetricName": "MaxMemoryUsed",
                    "Dimensions": [{"Name": "FunctionName", "Value": "orders-worker"}],
                }
            ]
        }

    def get_metric_statistics(self, **kwargs):
        return {
            "Datapoints": [
                {
                    "Timestamp": datetime(2026, 6, 21, tzinfo=timezone.utc),
                    "Maximum": 100.0,
                    "Unit": "Megabytes",
                }
            ]
        }


class _Session:
    clients = {
        "s3": _S3Client(),
        "lambda": _LambdaClient(),
        "rds": _RDSClient(),
        "logs": _LogsClient(),
        "cloudwatch": _CloudWatchClient(),
    }

    def client(self, service, **kwargs):
        return self.clients[service]


class MiniStackCollectorTests(unittest.TestCase):
    def test_collects_evidence_and_isolates_service_failures(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "cloudsweep.ministack_collector.boto3.Session", return_value=_Session()
        ):
            output_dir = collect_ministack(tmp)
            terraform = (output_dir / "main.tf").read_text(encoding="utf-8")
            metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
            parsed = json.loads((output_dir / "parsed_input.json").read_text(encoding="utf-8"))
            state = run_graph(output_dir, write=True, standard_output=True)
            report = (output_dir / "result" / "finops_report.md").read_text(encoding="utf-8")

        self.assertIn('resource "aws_s3_bucket"', terraform)
        self.assertIn('resource "aws_lambda_function"', terraform)
        self.assertIn('resource "aws_cloudwatch_log_group"', terraform)
        self.assertNotIn('resource "aws_s3_bucket_lifecycle_configuration"', terraform)
        self.assertEqual(3, len(parsed["resources"]))
        self.assertTrue(any(error["service"] == "rds" for error in parsed["collection_errors"]))
        lambda_metrics = next(
            record for record in metrics["resources"].values() if record["service"] == "lambda"
        )
        self.assertEqual([100.0], lambda_metrics["metrics"]["memory_used_mb"]["datapoints"])
        self.assertEqual("Megabytes", lambda_metrics["metrics"]["memory_used_mb"]["unit"])
        self.assertEqual({"s3", "lambda", "cloudwatch"}, set(state["domains"]))
        self.assertTrue(any(finding["domain"] == "lambda" for finding in state["findings"]))
        self.assertIn("CloudSweep LangGraph Report", report)

    def test_operation_allowlist_contains_only_read_verbs(self):
        forbidden = ("create", "update", "put", "delete", "modify", "invoke", "start", "stop")
        self.assertTrue(READ_ONLY_OPERATIONS)
        self.assertFalse(any(verb in operation.split(".", 1)[1] for operation in READ_ONLY_OPERATIONS for verb in forbidden))

    def test_cli_collects_ministack_evidence_before_running_graph(self):
        requested_dir = Path("requested-work-dir")
        collected_dir = Path("collected-work-dir").resolve()
        graph_state = {
            "intent": "waste_optimization",
            "execution_plan": ["domain_analysis", "report"],
            "domains": ["lambda"],
            "findings": [],
        }
        with patch(
            "cloudsweep.ministack_collector.collect_ministack", return_value=collected_dir
        ) as collect_mock, patch("cloudsweep.graph.run_graph", return_value=graph_state) as run_mock:
            main([str(requested_dir), "--from-ministack", "--dry-run", "--standard-output"])

        collect_mock.assert_called_once_with(str(requested_dir))
        run_mock.assert_called_once_with(collected_dir, write=False, standard_output=True)

    def test_cli_can_collect_without_running_graph(self):
        collected_dir = Path("collected-work-dir").resolve()
        with patch(
            "cloudsweep.ministack_collector.collect_ministack", return_value=collected_dir
        ) as collect_mock, patch("cloudsweep.graph.run_graph") as run_mock:
            main(["requested-work-dir", "--from-ministack", "--collect-only"])

        collect_mock.assert_called_once_with("requested-work-dir")
        run_mock.assert_not_called()

    def test_official_aws_names_are_normalized_deterministically(self):
        self.assertEqual("cpu_utilization", normalize_metric_name("CPUUtilization"))
        self.assertEqual("database_connections", normalize_metric_name("DatabaseConnections"))
        self.assertEqual("read_iops", normalize_metric_name("ReadIOPS"))
        self.assertEqual("memory_used_mb", normalize_metric_name("MaxMemoryUsed"))
        self.assertEqual("dev", normalize_environment("development"))
        self.assertEqual("prod", normalize_environment("Production"))
        self.assertEqual("custom-lab", normalize_environment("custom-lab"))

    def test_rds_analyzer_accepts_environment_and_legacy_metric_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "main.tf").write_text(
                '''resource "aws_db_instance" "analytics" {
  identifier     = "dev-analytics"
  engine         = "postgres"
  engine_version = "15.3"
  instance_class = "db.r5.xlarge"
  storage_type   = "gp3"
  multi_az       = true

  tags = {
    Environment = "development"
  }
}
''',
                encoding="utf-8",
            )
            (work_dir / "metrics.json").write_text(
                json.dumps(
                    {
                        "resources": {
                            "analytics": {
                                "service": "rds",
                                "resource_type": "aws_db_instance",
                                "metrics": {
                                    "cpuutilization": {
                                        "unit": "Percent",
                                        "datapoints": [10, 12, 15, 11],
                                    }
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            state = run_graph(work_dir, write=True)
            request = json.loads(
                (work_dir / "result" / "rds_skill_request.json").read_text(encoding="utf-8")
            )

        rules = {finding["rule_id"] for finding in state["findings"]}
        self.assertIn("RDS_R1_NONPROD_MULTI_AZ", rules)
        self.assertIn("RDS_R2_LOW_UTILIZATION", rules)
        self.assertTrue(all(finding["review_status"] == "needs_skill_review" for finding in state["findings"]))
        self.assertTrue(all(finding["analysis_source"] == "langgraph_candidate" for finding in state["findings"]))
        self.assertTrue(all(finding["estimated_monthly_saving_usd"] == 0.0 for finding in state["findings"]))
        self.assertTrue(all("remediation_patch" not in finding for finding in state["findings"]))
        self.assertEqual("needs_skill_review", request["status"])
        self.assertEqual(2, len(request["candidates"]))
        self.assertTrue(any("requires result/rds_skill_analysis.json" in warning for warning in state["warnings"]))


if __name__ == "__main__":
    unittest.main()
