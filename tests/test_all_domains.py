import json
import shutil
import tempfile
from pathlib import Path
import unittest

from cloudsweep.graph import ANALYZER_REGISTRY, _COMPLEX_DOMAINS, _load_skill_analysis, run_graph


ROOT = Path(__file__).resolve().parents[1]

_SIMPLE_SKILL_DIRS = {
    p.parent.name
    for p in (ROOT / ".claude" / "skills").glob("finops-*/SKILL.md")
    if p.parent.name not in {f"finops-{d}" for d in _COMPLEX_DOMAINS}
}
_COMPLEX_SKILL_DIRS = {f"finops-{d}" for d in _COMPLEX_DOMAINS}


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

    def test_simple_and_genai_skills_are_review_only(self):
        """Non-complex skills must not contain analysis logic — review only."""
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
                self.assertIn("Output Contract", text, f"{skill_dir} must declare output contract")
                self.assertIn("skill_analysis.json", text, f"{skill_dir} must reference skill_analysis.json")
                self.assertNotIn("Review-only authority", text, f"{skill_dir} must not be review-only")

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

    def test_complex_domain_skill_output_is_loaded_by_langgraph(self):
        """When a skill_analysis.json exists, LangGraph uses it instead of the Python stub."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            skill_finding = {
                "rule_id": "RDS_R4_EXTENDED_SUPPORT",
                "resource": "my_db",
                "severity": "HIGH",
                "confidence": "HIGH",
                "estimated_monthly_saving_usd": 250.0,
                "evidence": ["engine=mysql-5.7", "extended_support_active=true"],
                "recommendation": "Upgrade to mysql-8.0 to avoid Extended Support charges.",
                "optimized_replacement": None,
            }
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / "rds_skill_analysis.json").write_text(
                json.dumps({"schema_version": "1.0", "domain": "rds", "findings": [skill_finding]}),
                encoding="utf-8",
            )
            loaded = _load_skill_analysis(work_dir, "rds")
            self.assertEqual(1, len(loaded))
            self.assertEqual("RDS_R4_EXTENDED_SUPPORT", loaded[0]["rule_id"])

    def test_skill_analysis_domain_mismatch_is_ignored(self):
        """A skill_analysis.json with a wrong domain field must be silently skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result_dir = work_dir / "result"
            result_dir.mkdir()
            (result_dir / "elb_skill_analysis.json").write_text(
                json.dumps({"schema_version": "1.0", "domain": "rds", "findings": []}),
                encoding="utf-8",
            )
            loaded = _load_skill_analysis(work_dir, "elb")
            self.assertEqual([], loaded)

    def test_complex_domain_falls_back_to_python_stub_without_skill_output(self):
        """Without a skill output file, the Python fallback analyzer runs for complex domains."""
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            loaded = _load_skill_analysis(work_dir, "rds")
            self.assertEqual([], loaded, "No skill file → empty list, Python stub should be used")


if __name__ == "__main__":
    unittest.main()
