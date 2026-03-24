import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.predictions import apply_prediction_verdict, build_prediction_record
from core.storage import sync_positions_and_account_to_db, sync_predictions_to_db


class StorageSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "stock_team.db"
        self._create_schema()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_schema(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                name TEXT,
                direction TEXT,
                current_price REAL,
                target_price REAL,
                confidence INTEGER,
                timeframe TEXT,
                reasons TEXT,
                risks TEXT,
                source_agent TEXT,
                status TEXT,
                result TEXT,
                actual_end_price REAL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                verified_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                name TEXT,
                shares INTEGER,
                cost_price REAL,
                current_price REAL,
                market_value REAL,
                profit_loss REAL,
                profit_loss_pct REAL,
                position_pct REAL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT,
                bought_at TIMESTAMP,
                sold_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                total_asset REAL,
                cash REAL,
                market_value REAL,
                total_profit REAL,
                total_profit_pct REAL,
                daily_profit REAL,
                daily_profit_pct REAL,
                position_count INTEGER,
                max_drawdown REAL,
                updated_at TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    def test_sync_predictions_to_db_persists_active_and_verified_records(self):
        active = build_prediction_record(
            {
                "code": "sh.600000",
                "name": "浦发银行",
                "direction": "up",
                "target_price": 12.0,
                "current_price": 10.0,
                "confidence": 70,
                "timeframe": "1周",
                "reasons": ["技术面改善"],
            },
            created_at=datetime(2026, 3, 25, 9, 30),
        )
        verified = apply_prediction_verdict(active, 12.2, datetime(2026, 4, 1, 15, 0))

        predictions = {
            "active": {active["id"]: active},
            "history": [verified],
        }

        sync_predictions_to_db(predictions, self.db_path)

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT symbol, status, result FROM predictions ORDER BY created_at"
        ).fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "sh.600000")
        self.assertEqual(rows[0][1], "verified")
        self.assertEqual(rows[0][2], "correct")

    def test_sync_positions_and_account_to_db_updates_market_value(self):
        positions = {
            "sh.600000": {
                "name": "浦发银行",
                "shares": 100,
                "cost_price": 10.0,
                "current_price": 12.0,
                "buy_date": "2026-03-25",
            }
        }
        metrics = sync_positions_and_account_to_db(
            positions,
            cash=5000.0,
            portfolio={"total_capital": 6000.0},
            db_path=self.db_path,
        )

        conn = sqlite3.connect(self.db_path)
        position = conn.execute(
            "SELECT symbol, current_price, market_value FROM positions"
        ).fetchone()
        account = conn.execute(
            "SELECT total_asset, cash, market_value, total_profit FROM account"
        ).fetchone()
        conn.close()

        self.assertEqual(position[0], "sh.600000")
        self.assertEqual(position[1], 12.0)
        self.assertEqual(position[2], 1200.0)
        self.assertAlmostEqual(metrics["total_asset"], 6200.0)
        self.assertEqual(account[0], 6200.0)
        self.assertEqual(account[1], 5000.0)
        self.assertEqual(account[2], 1200.0)
        self.assertEqual(account[3], 200.0)


if __name__ == "__main__":
    unittest.main()
