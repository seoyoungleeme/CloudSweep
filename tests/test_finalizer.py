import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cloudsweep.finalizer import ReviewValidationError, finalize
from cloudsweep.graph import run_graph


ROOT = Path(__file__).resolve().parents[1]


class FinalizerTests(unittest.TestCase):
    def test_accepts_machine_values_and_rejects_stale_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            source = ROOT / "sample" / "season2" / "GENAI-001"
            shutil.copy2(source / "genai_evidence.json", work_dir / "genai_evidence.json")
            shutil.copy2(source / "cost_report.json", work_dir / "cost_report.json")
            state = run_graph(work_dir, write=True)
            review = {
                "schema_version": "1.0",
                "run_id": state["run_id"],
                "finding_reviews": [
                    {"finding_id": finding["finding_id"], "disposition": "accepted", "rationale": "Evidence reviewed."}
                    for finding in state["findings"]
                ],
                "cross_domain_review": [],
                "final_summary": "Accepted deterministic findings after review.",
            }
            review_path = work_dir / "result" / "claude_review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")

            outputs = finalize(work_dir, review_path)

            report = Path(outputs["report"]).read_text(encoding="utf-8")
            self.assertIn("$1786.19", report)
            self.assertTrue(Path(outputs["optimized_tf"]).exists())
            review["run_id"] = "stale-run"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(ReviewValidationError, "run_id"):
                finalize(work_dir, review_path)


if __name__ == "__main__":
    unittest.main()
