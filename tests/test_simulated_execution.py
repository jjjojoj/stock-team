import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.simulated_execution import PaperExecutionEngine


class PaperExecutionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "stock_team.db"
        self.config = {
            "board_lot": 100,
            "min_commission": 1.0,
            "commission_rate": 0.0003,
            "transfer_fee_rate": 0.00001,
            "stamp_duty_rate": 0.0005,
            "buy_slippage_bps": 6.0,
            "sell_slippage_bps": 8.0,
            "fallback_slippage_bps": 14.0,
            "simulated_price_slippage_bps": 35.0,
            "min_capacity_value": 500000.0,
            "capacity_value_per_yi_market_cap": 6000.0,
            "partial_fill_min_ratio": 0.2,
            "stale_order_minutes": 120,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_submit_buy_order_records_trade_and_fees(self):
        engine = PaperExecutionEngine(self.db_path, config=self.config)
        result = engine.submit_order(
            symbol="sh.600459",
            name="贵研铂业",
            direction="buy",
            requested_shares=1000,
            reference_price=10.0,
            price_source="live_api",
            reason="测试买入",
            cash_available=20000.0,
            market_cap=100.0,
        )

        self.assertEqual(result["status"], "filled")
        self.assertEqual(result["filled_shares"], 1000)
        self.assertLess(result["cash_effect"], 0)
        self.assertGreater(result["commission"], 0)

        with self._connect() as conn:
            order = conn.execute("SELECT * FROM simulated_orders").fetchone()
            trade = conn.execute("SELECT * FROM trades").fetchone()

        self.assertEqual(order["status"], "filled")
        self.assertEqual(order["filled_shares"], 1000)
        self.assertEqual(trade["execution_order_id"], result["order_id"])
        self.assertEqual(trade["simulated"], 1)

    def test_partial_fill_can_be_reconciled_later(self):
        config = {**self.config, "min_capacity_value": 3000.0}
        engine = PaperExecutionEngine(self.db_path, config=config)
        initial = engine.submit_order(
            symbol="sh.601121",
            name="宝地矿业",
            direction="buy",
            requested_shares=1000,
            reference_price=10.0,
            price_source="live_api",
            reason="测试部分成交",
            cash_available=30000.0,
            market_cap=0.0,
        )

        self.assertEqual(initial["status"], "partial_filled")
        self.assertGreater(initial["remaining_shares"], 0)

        reconciled = engine.reconcile_open_orders(
            lambda code: {"price": 10.1, "source": "live_api", "market_cap": 1000.0},
            cash_available=30000.0,
        )
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["status"], "filled")

        with self._connect() as conn:
            order = conn.execute(
                "SELECT status, filled_shares, remaining_shares FROM simulated_orders WHERE order_id = ?",
                (initial["order_id"],),
            ).fetchone()
            trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

        self.assertEqual(order["status"], "filled")
        self.assertEqual(order["filled_shares"], 1000)
        self.assertEqual(order["remaining_shares"], 0)
        self.assertEqual(trade_count, 2)

    def test_stale_partial_order_is_cancelled(self):
        config = {**self.config, "min_capacity_value": 3000.0, "stale_order_minutes": 1}
        engine = PaperExecutionEngine(self.db_path, config=config)
        initial = engine.submit_order(
            symbol="sh.601121",
            name="宝地矿业",
            direction="buy",
            requested_shares=1000,
            reference_price=10.0,
            price_source="live_api",
            reason="测试撤单",
            cash_available=30000.0,
            market_cap=0.0,
        )

        self.assertEqual(initial["status"], "partial_filled")

        with self._connect() as conn:
            conn.execute(
                "UPDATE simulated_orders SET created_at = ?, updated_at = ? WHERE order_id = ?",
                ("2026-03-20T09:00:00", "2026-03-20T09:00:00", initial["order_id"]),
            )
            conn.commit()

        reconciled = engine.reconcile_open_orders(
            lambda code: {"price": 10.1, "source": "live_api", "market_cap": 1000.0},
            cash_available=30000.0,
        )
        self.assertEqual(reconciled[0]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
