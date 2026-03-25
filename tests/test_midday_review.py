import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.midday_review as midday_review


class MiddayReviewTests(unittest.TestCase):
    def setUp(self):
        self.learning_cfg = {
            "midday_learning": {
                "min_verified_predictions": 4,
                "min_wrong_cases": 3,
                "min_bias_ratio": 0.6,
                "consecutive_error_runs": 2,
                "adjustment_step": 0.02,
                "min_confidence_threshold": 0.65,
                "max_confidence_threshold": 0.9,
                "rollback_window_runs": 3,
                "rollback_drop_pct": 8.0,
            }
        }

    def test_summarize_lessons_requires_sample_gate(self):
        results = {
            "verified": 2,
            "correct": 0,
            "wrong": 2,
            "details": [
                {"direction": "up", "status": "❌ 错误"},
                {"direction": "up", "status": "❌ 错误"},
            ],
        }

        with patch.object(midday_review, "load_guardrail_config", return_value=self.learning_cfg):
            lessons = midday_review.summarize_lessons(results)

        self.assertTrue(any("低于自动调参门槛" in lesson["content"] for lesson in lessons))
        self.assertFalse(any(lesson.get("actionable") for lesson in lessons))

    def test_apply_to_future_adjusts_only_after_consecutive_biased_runs(self):
        results = {
            "verified": 4,
            "correct": 1,
            "wrong": 3,
            "details": [
                {"direction": "up", "status": "❌ 错误"},
                {"direction": "up", "status": "❌ 错误"},
                {"direction": "up", "status": "❌ 错误"},
                {"direction": "down", "status": "✅ 正确"},
            ],
        }
        lessons = [
            {
                "type": "error",
                "content": "早盘上涨判断偏乐观，错误集中在看多方向",
                "action": "提高上涨预测置信度阈值",
                "actionable": True,
                "adjustment_direction": "up",
            }
        ]
        state = {
            "events": [],
            "midday_learning": {
                "history": [
                    {
                        "timestamp": "2026-03-25T11:30:00",
                        "verified": 4,
                        "correct": 1,
                        "wrong": 3,
                        "accuracy": 25.0,
                        "dominant_bias": "up",
                    }
                ],
                "adjustments": [],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            log_dir = Path(temp_dir) / "logs"
            config_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "prediction_config.json"
            config_file.write_text(json.dumps({"confidence_threshold": 0.8}), encoding="utf-8")
            saved_state = {}

            with (
                patch.object(midday_review, "CONFIG_DIR", config_dir),
                patch.object(midday_review, "LOG_DIR", log_dir),
                patch.object(midday_review, "load_guardrail_config", return_value=self.learning_cfg),
                patch.object(midday_review, "load_guardrail_state", return_value=state),
                patch.object(midday_review, "save_guardrail_state", side_effect=lambda payload: saved_state.update(payload)),
                patch.object(midday_review, "_append_memory_entry"),
            ):
                midday_review.apply_to_future(lessons, results)

            updated = json.loads(config_file.read_text(encoding="utf-8"))

        self.assertEqual(updated["confidence_threshold"], 0.82)
        self.assertEqual(saved_state["midday_learning"]["adjustments"][0]["status"], "active")

    def test_apply_to_future_rolls_back_after_degraded_window(self):
        results = {
            "verified": 4,
            "correct": 1,
            "wrong": 3,
            "details": [
                {"direction": "down", "status": "❌ 错误"},
                {"direction": "down", "status": "❌ 错误"},
                {"direction": "down", "status": "❌ 错误"},
                {"direction": "up", "status": "✅ 正确"},
            ],
        }
        state = {
            "events": [],
            "midday_learning": {
                "history": [
                    {"accuracy": 70.0, "wrong": 1, "dominant_bias": "up"},
                    {"accuracy": 60.0, "wrong": 3, "dominant_bias": "down"},
                    {"accuracy": 55.0, "wrong": 3, "dominant_bias": "down"},
                ],
                "adjustments": [
                    {
                        "applied_at": "2026-03-23T11:30:00",
                        "applied_run_index": 0,
                        "old_value": 0.8,
                        "new_value": 0.78,
                        "reason": "早盘下跌判断偏悲观，错误集中在看空方向",
                        "baseline_accuracy": 75.0,
                        "evaluation_due_run": 3,
                        "status": "active",
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            log_dir = Path(temp_dir) / "logs"
            config_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "prediction_config.json"
            config_file.write_text(json.dumps({"confidence_threshold": 0.78}), encoding="utf-8")
            saved_state = {}

            with (
                patch.object(midday_review, "CONFIG_DIR", config_dir),
                patch.object(midday_review, "LOG_DIR", log_dir),
                patch.object(midday_review, "load_guardrail_config", return_value=self.learning_cfg),
                patch.object(midday_review, "load_guardrail_state", return_value=state),
                patch.object(midday_review, "save_guardrail_state", side_effect=lambda payload: saved_state.update(payload)),
                patch.object(midday_review, "_append_memory_entry"),
            ):
                midday_review.apply_to_future([], results)

            updated = json.loads(config_file.read_text(encoding="utf-8"))

        self.assertEqual(updated["confidence_threshold"], 0.8)
        self.assertEqual(saved_state["midday_learning"]["adjustments"][0]["status"], "rolled_back")


if __name__ == "__main__":
    unittest.main()
