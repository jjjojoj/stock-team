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

    def test_build_pipeline_buy_signals_only_uses_proposals(self):
        trader = auto_trader.AutoTraderV3.__new__(auto_trader.AutoTraderV3)
        trader.cash = 200000.0
        trader.positions = {}
        trader.predictions = {
            "active": {
                "pred-1": {
                    "id": "pred-1",
                    "code": "sz.000831",
                    "name": "中国稀土",
                    "direction": "up",
                    "confidence": 80,
                    "target_price": 52.80,
                    "reasons": ["稀土景气改善"],
                    "created_at": "2026-03-31T09:00:00",
                }
            }
        }
        trader.RISK_CONFIG = dict(auto_trader.AutoTraderV3.RISK_CONFIG)

        proposal = {
            "id": 7,
            "symbol": "sz.000831",
            "name": "中国稀土",
            "status": "quant_validated",
            "target_price": 52.80,
            "stop_loss": 44.00,
            "thesis": "稀土行业进入修复阶段",
            "metadata": '{"research":{"score":55,"industry":"稀土"}}',
        }

        with (
            patch.object(auto_trader, "get_pipeline_candidates", return_value=[proposal]),
            patch.object(auto_trader, "apply_cio_decision") as cio_decision,
            patch.object(trader, "get_trade_quote", return_value={"price": 48.0, "source": "live_api", "market_cap": 300.0, "fundamental_source": "live"}),
            patch.object(trader, "check_risk_assessment", return_value=(True, "风控检查通过", "low")),
            patch.object(trader, "save_risk_assessment", return_value={"status": "risk_checked"}),
        ):
            signals = trader.build_pipeline_buy_signals()

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["proposal_id"], 7)
        self.assertEqual(signals[0]["code"], "sz.000831")
        self.assertTrue(signals[0]["risk_prechecked"])
        cio_decision.assert_called_once()

    def test_evaluate_cio_decision_accepts_conservative_65_confidence(self):
        trader = auto_trader.AutoTraderV3.__new__(auto_trader.AutoTraderV3)
        trader.PIPELINE_CONFIG = dict(auto_trader.AutoTraderV3.PIPELINE_CONFIG)

        proposal = {
            "metadata": '{"research":{"score":60}}',
        }
        signal = {
            "confidence": 65,
            "price": 48.0,
            "target_price": 51.0,
        }

        approved, reason, summary = trader._evaluate_cio_decision(
            proposal,
            signal,
            risk_passed=True,
            risk_level="low",
            risk_message="风控通过",
        )

        self.assertTrue(approved)
        self.assertEqual(summary["analysis_score"], 60)
        self.assertIn("批准交易", reason)


if __name__ == "__main__":
    unittest.main()
