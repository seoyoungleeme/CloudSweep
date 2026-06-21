import unittest

from cloudsweep.rule_engine import RuleValidationError, evaluate_predicate, validate_rule_document


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


if __name__ == "__main__":
    unittest.main()
