import json
from pathlib import Path
import tempfile
import unittest

from cloudsweep.token_usage import compute_usage, render_markdown


class TokenUsageTests(unittest.TestCase):
    def test_completed_run_snapshot_survives_rerender_without_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            machine_dir = result_dir / ".machine"
            machine_dir.mkdir(parents=True)
            (machine_dir / "token_usage.json").write_text(
                json.dumps(
                    {
                        "measured": True,
                        "model": "claude-sonnet-5",
                        "run_id": "run-1",
                        "window_id": "window-1",
                        "start_time": "2026-07-07T00:00:00+00:00",
                        "input_tokens": 4,
                        "output_tokens": 688,
                        "cache_creation_input_tokens": 2064,
                        "cache_read_input_tokens": 1659208,
                        "message_count": 0,
                        "total_tokens": 1661964,
                        "estimated_cost_usd": 0.5158,
                    }
                ),
                encoding="utf-8",
            )

            usage = compute_usage(result_dir, run_id="run-1")

        self.assertTrue(usage["measured"])
        self.assertTrue(usage["from_snapshot"])
        self.assertEqual(1661964, usage["total_tokens"])
        self.assertIn("Persisted from the completed CloudSweep AI window", "\n".join(render_markdown(usage)))

    def test_snapshot_with_wrong_run_id_is_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "result"
            machine_dir = result_dir / ".machine"
            machine_dir.mkdir(parents=True)
            (machine_dir / "token_usage.json").write_text(
                json.dumps(
                    {
                        "measured": True,
                        "model": "claude-sonnet-5",
                        "run_id": "old-run",
                        "window_id": "old-window",
                        "start_time": "2026-07-07T00:00:00+00:00",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "message_count": 1,
                        "total_tokens": 2,
                        "estimated_cost_usd": 0.0,
                    }
                ),
                encoding="utf-8",
            )

            usage = compute_usage(result_dir, run_id="new-run")

        self.assertFalse(usage["measured"])
        self.assertNotIn("from_snapshot", usage)

    def test_active_marker_does_not_reuse_snapshot_from_previous_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_dir = root / "result"
            machine_dir = result_dir / ".machine"
            machine_dir.mkdir(parents=True)
            (machine_dir / ".token_usage_start.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "window_id": "new-window",
                        "start_time": "2026-07-07T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (machine_dir / "token_usage.json").write_text(
                json.dumps(
                    {
                        "measured": True,
                        "model": "claude-sonnet-5",
                        "run_id": "run-1",
                        "window_id": "old-window",
                        "start_time": "2026-07-06T00:00:00+00:00",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "message_count": 1,
                        "total_tokens": 2,
                        "estimated_cost_usd": 0.0,
                    }
                ),
                encoding="utf-8",
            )

            usage = compute_usage(result_dir, cwd=root, run_id="run-1")

        self.assertFalse(usage["measured"])
        self.assertNotIn("from_snapshot", usage)


if __name__ == "__main__":
    unittest.main()
