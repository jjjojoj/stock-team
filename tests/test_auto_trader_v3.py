import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import auto_trader_v3 as auto_trader


class AutoTraderV3Tests(unittest.TestCase):
    def test_calculate_buy_budget_respects_risk_caps(self):
        trader = auto_trader.AutoTraderV3.__new__(auto_trader.AutoTraderV3)
        trader.cash = 200000.0
        trader.positions = {}
        trader.RISK_CONFIG = dict(auto_trader.AutoTraderV3.RISK_CONFIG)

        budget = trader.calculate_buy_budget()

        self.assertEqual(budget, 30000.0)

    def test_save_risk_assessment_creates_proposal_and_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "stock_team.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    direction TEXT NOT NULL,
                    thesis TEXT,
                    target_price REAL,
                    stop_loss REAL,
                    source_agent TEXT NOT NULL,
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    metadata JSON
                );
                CREATE TABLE risk_assessment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    risk_level TEXT,
                    suggested_position REAL,
                    max_position REAL,
                    var_95 REAL,
                    volatility REAL,
                    industry_concentration REAL,
                    correlation_market REAL,
                    risk_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()
            conn.close()

            trader = auto_trader.AutoTraderV3.__new__(auto_trader.AutoTraderV3)
            trader.RISK_CONFIG = dict(auto_trader.AutoTraderV3.RISK_CONFIG)

            with patch.object(auto_trader, "DATABASE_FILE", db_path):
                trader.save_risk_assessment("sz.000831", "medium", "单笔交易金额过大")

            conn = sqlite3.connect(db_path)
            proposal = conn.execute(
                "SELECT symbol, direction, source_agent, status FROM proposals"
            ).fetchone()
            assessment = conn.execute(
                "SELECT symbol, risk_level, risk_notes FROM risk_assessment"
            ).fetchone()
            conn.close()

        self.assertEqual(proposal, ("sz.000831", "buy", "Trader", "risk_checked"))
        self.assertEqual(assessment, ("sz.000831", "medium", "单笔交易金额过大"))


if __name__ == "__main__":
    unittest.main()
