import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import core.runtime_guardrails as guardrails


class RuntimeGuardrailTests(unittest.TestCase):
    def test_repeated_critical_errors_enable_auto_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "runtime_guardrails_state.json"
            config = {
                **guardrails.DEFAULT_CONFIG,
                "autopilot": {
                    **guardrails.DEFAULT_CONFIG["autopilot"],
                    "consecutive_error_threshold": 2,
                    "auto_read_only_minutes": 30,
                    "recovery_success_threshold": 2,
                },
                "freshness": dict(guardrails.DEFAULT_CONFIG["freshness"]),
            }

            with (
                patch.object(guardrails, "STATE_FILE", state_file),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
            ):
                guardrails.record_guardrail_event("ai_predictor", "error", "预测数据缺失")
                guardrails.record_guardrail_event("ai_predictor", "error", "预测数据缺失")
                control = guardrails.get_guardrail_control_state(config=config)

        self.assertTrue(control["active"])
        self.assertTrue(control["automatic"])
        self.assertEqual(control["source"], "automatic")

    def test_auto_read_only_recovers_after_success_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "runtime_guardrails_state.json"
            config = {
                **guardrails.DEFAULT_CONFIG,
                "autopilot": {
                    **guardrails.DEFAULT_CONFIG["autopilot"],
                    "consecutive_error_threshold": 2,
                    "auto_read_only_minutes": 30,
                    "recovery_success_threshold": 2,
                },
                "freshness": dict(guardrails.DEFAULT_CONFIG["freshness"]),
            }

            with (
                patch.object(guardrails, "STATE_FILE", state_file),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
            ):
                guardrails.record_guardrail_event("ai_predictor", "error", "预测数据缺失")
                guardrails.record_guardrail_event("ai_predictor", "error", "预测数据缺失")
                guardrails.record_guardrail_success("ai_predictor", "恢复成功")
                mid = guardrails.get_guardrail_control_state(config=config)
                guardrails.record_guardrail_success("ai_predictor", "恢复成功")
                final = guardrails.get_guardrail_control_state(config=config)

        self.assertTrue(mid["active"])
        self.assertFalse(final["active"])

    def test_evaluate_runtime_mode_respects_auto_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "runtime_guardrails_state.json"
            config = {
                **guardrails.DEFAULT_CONFIG,
                "autopilot": {
                    **guardrails.DEFAULT_CONFIG["autopilot"],
                    "consecutive_error_threshold": 1,
                    "auto_read_only_minutes": 30,
                    "recovery_success_threshold": 2,
                },
                "freshness": dict(guardrails.DEFAULT_CONFIG["freshness"]),
            }
            snapshot = {
                "daily_search_age_hours": 2.0,
                "predictions_age_hours": 2.0,
                "fundamental_snapshot_age_hours": 2.0,
                "stock_pool_age_hours": 2.0,
            }

            with (
                patch.object(guardrails, "STATE_FILE", state_file),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
                patch.object(guardrails, "get_runtime_snapshot", return_value=snapshot),
            ):
                guardrails.record_guardrail_event("ai_predictor", "error", "预测数据缺失")
                result = guardrails.evaluate_runtime_mode("prediction_generate", universe_count=3)

        self.assertFalse(result.ok)
        self.assertTrue(any("只读模式" in reason for reason in result.reasons))

    def test_trade_buy_blocks_when_core_inputs_missing(self):
        snapshot = {
            "daily_search_age_hours": 25.0,
            "predictions_age_hours": 48.0,
            "fundamental_snapshot_age_hours": 12.0,
            "stock_pool_age_hours": 12.0,
        }
        config = {
            **guardrails.DEFAULT_CONFIG,
            "freshness": dict(guardrails.DEFAULT_CONFIG["freshness"]),
        }

        with (
            patch.object(guardrails, "load_guardrail_config", return_value=config),
            patch.object(guardrails, "get_runtime_snapshot", return_value=snapshot),
        ):
            result = guardrails.evaluate_runtime_mode(
                "trade_buy",
                universe_count=0,
                active_prediction_count=0,
                available_cash=0,
            )

        self.assertFalse(result.ok)
        self.assertIn("观察池为空，禁止自动买入", result.reasons)
        self.assertIn("没有可用的活跃预测，禁止自动买入", result.reasons)
        self.assertIn("预测数据已超过 36 小时未更新", result.reasons)
        self.assertIn("可用现金不足，禁止自动买入", result.reasons)

    def test_task_lock_rejects_second_live_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_dir = Path(temp_dir)
            config = {**guardrails.DEFAULT_CONFIG, "lock_stale_seconds": 3600}

            with (
                patch.object(guardrails, "LOCK_DIR", lock_dir),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
            ):
                with guardrails.task_lock("selector"):
                    with self.assertRaises(guardrails.TaskLockedError):
                        with guardrails.task_lock("selector"):
                            pass

    def test_self_healing_records_retry_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "runtime_guardrails_state.json"
            config = {
                **guardrails.DEFAULT_CONFIG,
                "self_healing": {
                    **guardrails.DEFAULT_CONFIG["self_healing"],
                    "retry_tasks": {
                        "selector": {
                            "args": ["scripts/selector.py", "top", "10"],
                            "cooldown_seconds": 0,
                            "max_attempts": 1,
                            "timeout_seconds": 30,
                        }
                    },
                },
            }

            with (
                patch.object(guardrails, "STATE_FILE", state_file),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
                patch.object(
                    guardrails.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""),
                ),
            ):
                guardrails.record_guardrail_event("selector", "error", "选股失败")
                snapshot = guardrails.get_self_healing_snapshot(config=config, state=guardrails.load_guardrail_state())

        self.assertEqual(snapshot["recovery_count"], 1)
        self.assertEqual(snapshot["recent_recoveries"][0]["status"], "success")

    def test_trade_buy_mode_blocks_when_upstream_task_recently_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "runtime_guardrails_state.json"
            with patch.object(guardrails, "STATE_FILE", state_file):
                state = guardrails.load_guardrail_state()
                state["autopilot"]["task_health"]["ai_predictor"] = {
                    "consecutive_errors": 1,
                    "consecutive_successes": 0,
                    "last_level": "error",
                    "last_message": "预测生成失败",
                    "last_time": datetime.now().isoformat(),
                }
                guardrails.save_guardrail_state(state)

            config = {
                **guardrails.DEFAULT_CONFIG,
                "self_healing": {
                    **guardrails.DEFAULT_CONFIG["self_healing"],
                    "upstream_error_ttl_minutes": 600,
                    "pipeline_dependencies": {
                        **guardrails.DEFAULT_CONFIG["self_healing"]["pipeline_dependencies"],
                        "trade_buy": ["ai_predictor"],
                    },
                },
                "freshness": dict(guardrails.DEFAULT_CONFIG["freshness"]),
            }
            snapshot = {
                "daily_search_age_hours": 2.0,
                "predictions_age_hours": 2.0,
                "fundamental_snapshot_age_hours": 2.0,
                "stock_pool_age_hours": 2.0,
            }
            with (
                patch.object(guardrails, "STATE_FILE", state_file),
                patch.object(guardrails, "load_guardrail_config", return_value=config),
                patch.object(guardrails, "get_runtime_snapshot", return_value=snapshot),
            ):
                result = guardrails.evaluate_runtime_mode(
                    "trade_buy",
                    universe_count=3,
                    active_prediction_count=2,
                    available_cash=10000,
                )

        self.assertFalse(result.ok)
        self.assertTrue(any("上游任务 ai_predictor 最近失败" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
