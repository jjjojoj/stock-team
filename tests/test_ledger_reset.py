import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import core.storage as storage


class LedgerResetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "stock_team.db"
        self.portfolio_file = self.root / "portfolio.json"
        self.positions_file = self.root / "positions.json"
        self.trade_history_file = self.root / "trade_history.json"
        self.archive_dir = self.root / "archives"
        storage.ensure_storage_tables(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reset_operational_ledger_archives_and_resets_live_tables(self):
        storage.save_json(
            self.portfolio_file,
            {"total_capital": 200000, "available_cash": 274898.0, "note": "脏账"},
        )
        storage.save_json(self.positions_file, {"sh.600000": {"name": "测试", "shares": 100}})
        storage.save_json(self.trade_history_file, [{"action": "BUY", "code": "sh.600000"}])

        with storage.get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO account (
                    date, total_asset, cash, market_value, total_profit, total_profit_pct,
                    daily_profit, daily_profit_pct, position_count, max_drawdown, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-03-10", 274898.0, 274898.0, 0.0, 74898.0, 37.449, 0.0, 0.0, 0, 0.0, "2026-03-10T15:00:00"),
            )
            conn.execute(
                """
                INSERT INTO trades (symbol, name, direction, shares, price, amount, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("sh.600000", "测试", "buy", 100, 10.0, 1000.0, "2026-03-10T10:00:00"),
            )
            conn.execute(
                """
                INSERT INTO simulated_orders (
                    order_id, symbol, direction, requested_shares, remaining_shares,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("sim_1", "sh.600000", "buy", 100, 100, "pending", "2026-03-10T10:00:00", "2026-03-10T10:00:00"),
            )
            conn.execute(
                """
                INSERT INTO simulated_fills (
                    order_id, symbol, direction, shares, price, amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("sim_1", "sh.600000", "buy", 50, 10.0, 500.0, "2026-03-10T10:01:00"),
            )
            conn.commit()

        result = storage.reset_operational_ledger(
            200000.0,
            reset_at=datetime(2026, 3, 31, 11, 30),
            reason="重置模拟账本",
            db_path=self.db_path,
            portfolio_file=self.portfolio_file,
            positions_file=self.positions_file,
            trade_history_file=self.trade_history_file,
            archive_dir=self.archive_dir,
        )

        self.assertEqual(result["baseline_date"], "2026-03-31")
        self.assertTrue(Path(result["archive_path"]).exists())

        portfolio = storage.load_json(self.portfolio_file, {})
        self.assertEqual(portfolio["available_cash"], 200000.0)
        self.assertEqual(portfolio["total_asset"], 200000.0)

        self.assertEqual(storage.load_json(self.positions_file, None), {})
        self.assertEqual(storage.load_json(self.trade_history_file, None), [])

        with storage.get_db(self.db_path) as conn:
            account_rows = conn.execute("SELECT date, total_asset, cash, total_profit FROM account").fetchall()
            self.assertEqual(len(account_rows), 1)
            self.assertEqual(tuple(account_rows[0]), ("2026-03-31", 200000.0, 200000.0, 0.0))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM simulated_orders").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM simulated_fills").fetchone()[0], 0)

    def test_build_portfolio_snapshot_prefers_live_account_cash_over_file_override(self):
        portfolio_file = self.root / "portfolio_override.json"
        storage.save_json(
            portfolio_file,
            {"total_capital": 200000, "available_cash": 274898.0, "baseline_date": "2026-03-31"},
        )

        with storage.get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO account (
                    date, total_asset, cash, market_value, total_profit, total_profit_pct,
                    daily_profit, daily_profit_pct, position_count, max_drawdown, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-03-31", 200000.0, 200000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, "2026-03-31T11:30:00"),
            )
            conn.commit()

        with patch.object(storage, "PORTFOLIO_FILE", portfolio_file):
            snapshot = storage.build_portfolio_snapshot(self.db_path)

        self.assertEqual(snapshot["available_cash"], 200000.0)
        self.assertEqual(snapshot["total_assets"], 200000.0)
        self.assertEqual(snapshot["total_profit"], 0.0)

    def test_build_portfolio_snapshot_ignores_account_older_than_baseline_date(self):
        portfolio_file = self.root / "portfolio_override.json"
        storage.save_json(
            portfolio_file,
            {"total_capital": 200000, "available_cash": 200000.0, "baseline_date": "2026-03-31"},
        )

        with storage.get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO account (
                    date, total_asset, cash, market_value, total_profit, total_profit_pct,
                    daily_profit, daily_profit_pct, position_count, max_drawdown, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-03-10", 162248.0, 162248.0, 0.0, -37752.0, -18.876, 0.0, 0.0, 0, 0.0, "2026-03-10T15:00:00"),
            )
            conn.commit()

        with patch.object(storage, "PORTFOLIO_FILE", portfolio_file):
            snapshot = storage.build_portfolio_snapshot(self.db_path)

        self.assertEqual(snapshot["available_cash"], 200000.0)
        self.assertEqual(snapshot["total_assets"], 200000.0)
        self.assertEqual(snapshot["account"]["date"], "2026-03-31")


if __name__ == "__main__":
    unittest.main()
