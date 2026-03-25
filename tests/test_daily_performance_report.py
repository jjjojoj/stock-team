import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import daily_performance_report


class DailyPerformanceReportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
