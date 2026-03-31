import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import daily_performance_report


class DailyPerformanceReportTests(unittest.TestCase):
    def test_load_trade_history_filters_records_before_baseline(self):
        reporter = daily_performance_report.DailyPerformanceReport()
        reporter.baseline_date = "2026-03-31"

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "trade_history.json"
            history_path.write_text(
                """
[
  {"timestamp": "2026-03-10T10:00:00", "type": "sell"},
  {"timestamp": "2026-03-31T10:00:00", "type": "sell"}
]
                """.strip(),
                encoding="utf-8",
            )
            reporter.trade_history_path = str(history_path)
            history = reporter._load_trade_history()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["timestamp"], "2026-03-31T10:00:00")

    def test_quant_metrics_use_verified_prediction_history(self):
        reporter = daily_performance_report.DailyPerformanceReport()
        predictions = [
            {
                "direction": "up",
                "confidence": 80,
                "result": {"status": "correct", "price_change_pct": 10.0},
            },
            {
                "direction": "down",
                "confidence": 60,
                "result": {"status": "partial", "partial": True, "price_change_pct": -4.0},
            },
            {
                "direction": "up",
                "confidence": 40,
                "result": {"status": "wrong", "price_change_pct": -6.0},
            },
        ]

        with patch.object(reporter, "_verified_predictions", return_value=predictions):
            metrics = reporter._collect_quant_metrics()

        self.assertAlmostEqual(metrics["选股胜率"], (1.0 + 0.5 + 0.0) / 3)
        self.assertAlmostEqual(metrics["推荐收益"], (0.10 + 0.04 - 0.06) / 3)
        self.assertGreaterEqual(metrics["因子 IC"], -1.0)
        self.assertLessEqual(metrics["因子 IC"], 1.0)

    def test_research_metrics_use_latest_search_and_real_proposals(self):
        reporter = daily_performance_report.DailyPerformanceReport()
        predictions = [
            {"result": {"status": "correct", "price_change_pct": 8.0}},
            {"result": {"status": "partial", "partial": True, "price_change_pct": 3.0}},
            {"result": {"status": "wrong", "price_change_pct": -5.0}},
        ]

        with (
            patch.object(reporter, "_verified_predictions", return_value=predictions),
            patch.object(reporter, "_latest_daily_search_count", return_value=14),
            patch.object(reporter, "_query_rows", return_value=[{"status": "approved"}, {"status": "pending"}]),
        ):
            metrics = reporter._collect_research_metrics()

        self.assertEqual(metrics["信息条数"], 14)
        self.assertAlmostEqual(metrics["预测准确率"], 0.5)
        self.assertAlmostEqual(metrics["研报采用"], 0.5)

    def test_trader_metrics_filter_trades_before_baseline(self):
        reporter = daily_performance_report.DailyPerformanceReport()
        reporter.baseline_date = "2026-03-31"

        with (
            patch.object(reporter, "_query_value", return_value=2),
            patch.object(reporter, "_query_rows", return_value=[{"amount": 1000.0, "commission": 2.0}]),
            patch.object(
                reporter,
                "_load_trade_history",
                return_value=[
                    {"timestamp": "2026-03-31T10:00:00", "type": "sell", "pnl_pct": 0.03},
                ],
            ),
        ):
            metrics = reporter._collect_trader_metrics()

        self.assertAlmostEqual(metrics["成交率"], 1.0)
        self.assertAlmostEqual(metrics["滑点控制"], 0.002)
        self.assertAlmostEqual(metrics["择时胜率"], 1.0)


if __name__ == "__main__":
    unittest.main()
