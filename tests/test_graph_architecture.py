import unittest

from cloudsweep.enrichment import CallableMCPEnrichmentProvider
from cloudsweep.graph import CloudSweepRuntime, run_graph


SCENARIO = "sample/season2/GENAI-001"


class GraphArchitectureTests(unittest.TestCase):
    def test_send_fan_out_collects_domain_results_in_domain_order(self):
        state = run_graph(SCENARIO, write=False)

        self.assertEqual(
            ["bedrock", "sagemaker", "ec2"],
            [result["domain"] for result in state["domain_results"]],
        )
        self.assertIn("domain fan-out: 3 branch(es)", state["trace"])
        self.assertEqual(7, len(state["findings"]))

    def test_callable_mcp_provider_enriches_pricing_and_documentation(self):
        provider = CallableMCPEnrichmentProvider(
            pricing_lookup=lambda domain, finding: {
                "service_code": domain.upper(),
                "verified_unit_price_usd": 1.23,
            },
            docs_search=lambda query, finding: [
                f"https://docs.aws.amazon.com/{finding['domain']}/latest/guide/"
            ],
        )

        state = run_graph(SCENARIO, write=False, enrichment_provider=provider)

        self.assertEqual("aws-mcp", state["enrichment_status"]["pricing"]["provider"])
        self.assertTrue(all(finding["pricing_verification"]["status"] == "verified" for finding in state["findings"]))
        self.assertTrue(all(finding["documentation"]["status"] == "available" for finding in state["findings"]))

    def test_enrichment_failure_uses_fallback_and_keeps_report(self):
        class BrokenProvider:
            name = "broken-mcp"

            def verify_pricing(self, finding):
                raise RuntimeError("pricing unavailable")

            def fetch_doc_refs(self, finding):
                raise RuntimeError("docs unavailable")

        state = run_graph(SCENARIO, write=False, enrichment_provider=BrokenProvider())

        self.assertEqual(7, len(state["findings"]))
        self.assertEqual(7, state["enrichment_status"]["pricing"]["failure_count"])
        self.assertEqual(7, state["enrichment_status"]["documentation"]["failure_count"])
        self.assertTrue(all(finding["pricing_verification"]["status"] in {"evidence_only", "unavailable"} for finding in state["findings"]))
        self.assertIn("# CloudSweep LangGraph Report", state["report_markdown"])

    def test_checkpoint_interrupt_and_resume_approval(self):
        runtime = CloudSweepRuntime()
        paused = runtime.run(
            SCENARIO,
            thread_id="approval-test",
            write=False,
            require_approval=True,
            approval_threshold_usd=500.0,
        )

        self.assertEqual("pending", paused["approval_status"])
        self.assertEqual(1, len(paused["__interrupt__"]))
        request = paused["__interrupt__"][0].value
        self.assertEqual("cloudsweep_finops_approval", request["kind"])
        self.assertGreaterEqual(len(request["candidates"]), 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            runtime.run(SCENARIO, thread_id="approval-test", write=False)

        resumed = runtime.resume(
            "approval-test",
            {"approved": True, "reviewer": "finops-owner"},
        )

        self.assertEqual("approved", resumed["approval_status"])
        self.assertEqual("finops-owner", resumed["approval_decision"]["reviewer"])
        self.assertNotIn("__interrupt__", resumed)
        self.assertIn("approval gate: approved", resumed["trace"])


if __name__ == "__main__":
    unittest.main()
