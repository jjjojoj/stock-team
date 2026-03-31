import math
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import backtester


class BacktesterTests(unittest.TestCase):
    def test_calculate_metrics_uses_realized_pnl_and_infinite_profit_factor_when_no_losses(self):
        engine = backtester.Backverifyer(initial_capital=100000)
        engine.portfolio_values = [100000, 100251.15]
        engine.trades = [
            backtester.Trade(
                date="2026-03-01",
                stock_code="sh.600000",
                stock_name="测试股",
                action="buy",
                price=10.0,
                shares=100,
                value=1000.0,
                cost_basis=1000.0,
            ),
            backtester.Trade(
                date="2026-03-10",
                stock_code="sh.600000",
                stock_name="测试股",
                action="sell",
                price=11.0,
                shares=100,
                value=1100.0,
                cost_basis=1000.0,
                realized_pnl=98.57,
                realized_pnl_pct=9.857,
            ),
        ]

        metrics = engine.calculate_metrics()

        self.assertEqual(metrics["win_rate"], 100.0)
        self.assertAlmostEqual(metrics["avg_win"], 98.57)
        self.assertTrue(math.isinf(metrics["profit_factor"]))

    def test_notify_learning_formats_percent_points_without_double_scaling(self):
        engine = backtester.Backverifyer()
        captured = {}

        def fake_send(title, content, level):
            captured["title"] = title
            captured["content"] = content
            captured["level"] = level

        fake_module = types.ModuleType("feishu_notifier")
        fake_module.send_feishu_message = fake_send

        with unittest.mock.patch.dict(sys.modules, {"feishu_notifier": fake_module}):
            engine._notify_learning(
                {
                    "period": "2026-01-01 to 2026-03-28",
                    "conclusion": "策略需要优化",
                    "win_rate": 100.0,
                    "profit_loss_ratio": float("inf"),
                    "sharpe_ratio": -0.04,
                    "annual_return": 1.18,
                    "lessons": ["建议：延长止盈区间，让利润奔跑"],
                }
            )

        self.assertIn("胜率：100.0%", captured["content"])
        self.assertIn("盈亏比：∞", captured["content"])
        self.assertIn("年化收益：1.18%", captured["content"])


if __name__ == "__main__":
    unittest.main()
