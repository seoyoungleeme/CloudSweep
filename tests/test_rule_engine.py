import unittest
from pathlib import Path

from cloudsweep.graph import ANALYZER_REGISTRY
from cloudsweep.rule_engine import RuleEngine, RuleValidationError, evaluate_predicate, load_rule, validate_rule_document


ROOT = Path(__file__).resolve().parents[1]


class RuleEngineTests(unittest.TestCase):
    def test_nested_predicates_and_threshold_boundaries(self):
        predicate = {
            "all": [
                {"fact": "utilization", "op": "lt", "threshold": "max_utilization"},
                {"any": [
                    {"fact": "errors", "op": "eq", "value": 0},
                    {"fact": "override", "op": "eq", "value": True},
                ]},
                {"not": {"fact": "blocked", "op": "eq", "value": True}},
            ]
        }
        self.assertTrue(evaluate_predicate(predicate, {"utilization": 19, "errors": 0, "blocked": False}, {"max_utilization": 20}))
        self.assertFalse(evaluate_predicate(predicate, {"utilization": 20, "errors": 0, "blocked": False}, {"max_utilization": 20}))

    def test_unknown_fact_and_handler_fail_fast(self):
        document = {
            "schema_version": "2.0",
            "rule_id": "TEST_RULE",
            "domain": "test",
            "version": "2.0.0",
            "facts": {"utilization": {"type": "number", "required": True}},
            "thresholds": {"max": 20},
            "predicate": {"fact": "missing", "op": "lt", "threshold": "max"},
            "outcome": {"severity": "HIGH", "action": "RIGHTSIZE", "confidence": "MEDIUM"},
            "handlers": {"extractor": "test.extract", "savings": "test.save", "remediation": "test.fix"},
        }
        with self.assertRaisesRegex(RuleValidationError, "Unknown fact"):
            validate_rule_document(document)
        document["predicate"]["fact"] = "utilization"
        with self.assertRaisesRegex(RuleValidationError, "Unknown handler"):
            validate_rule_document(document, {"test.extract", "test.save"})

    def test_all_rule_files_are_v2_and_registered(self):
        rule_paths = sorted((ROOT / ".claude" / "skills").glob("finops-*/rules/*.json"))
        self.assertTrue(rule_paths)
        registered_files = {
            Path(rule_file).resolve()
            for domain in ANALYZER_REGISTRY.domains()
            for rule_file in ANALYZER_REGISTRY.get(domain).rule_files
        }
        for rule_path in rule_paths:
            with self.subTest(rule=rule_path.name):
                document = load_rule(rule_path)
                self.assertEqual("2.0", document["schema_version"])
                self.assertIn(document["domain"], ANALYZER_REGISTRY.domains())
                self.assertIn(rule_path.resolve(), registered_files)

    def test_rule_engine_uses_named_handlers(self):
        rule = {
            "schema_version": "2.0",
            "rule_id": "TEST_RULE",
            "domain": "test",
            "version": "2.0.0",
            "facts": {"utilization": {"type": "number", "required": True}},
            "thresholds": {"max": 20},
            "predicate": {"fact": "utilization", "op": "lt", "threshold": "max"},
            "outcome": {"severity": "HIGH", "action": "RIGHTSIZE", "confidence": "HIGH"},
            "handlers": {"extractor": "test.extract", "savings": "test.savings", "remediation": "test.remediation"},
        }
        engine = RuleEngine(
            extractors={"test.extract": lambda source: {"utilization": source["utilization"]}},
            savings_calculators={"test.savings": lambda facts, document: 12.345},
            remediation_builders={"test.remediation": lambda facts, document: {"kind": "candidate"}},
        )
        result = engine.evaluate(rule, {"utilization": 10})
        self.assertEqual(12.35, result["estimated_monthly_saving_usd"])
        self.assertEqual({"kind": "candidate"}, result["remediation_patch"])
        self.assertIsNone(engine.evaluate(rule, {"utilization": 20}))


if __name__ == "__main__":
    unittest.main()
