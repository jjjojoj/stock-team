import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import proposals


class ProposalPipelineTests(unittest.TestCase):
    def test_selection_proposal_refreshes_open_pipeline_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "stock_team.db"
            proposals.ensure_pipeline_tables(db_path)

            stock = {
                "code": "sh.601121",
                "name": "宝地矿业",
                "price": 7.43,
                "sector": "有色金属",
                "sub_sector": "其他",
                "score": {"total": 27, "details": "PB=2.05(+9)"},
                "proposal_reasons": ["动态选股综合评分 27/100", "PB=2.05(+9)"],
                "target_price": 7.88,
                "stop_loss": 6.98,
                "technical": {"technical_score": 20, "macd": "死叉", "kdj": "正常"},
            }

            with patch.object(proposals, "get_portfolio_baseline_date", return_value="2026-03-31"):
                first = proposals.create_or_update_selection_proposal(stock, db_path=db_path)
                second = proposals.create_or_update_selection_proposal({**stock, "target_price": 8.02}, db_path=db_path)

            self.assertEqual(first["proposal_id"], second["proposal_id"])

            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT status, target_price, metadata FROM proposals").fetchone()

            self.assertEqual(row[0], "pending")
            self.assertAlmostEqual(row[1], 8.02, places=2)
            self.assertIn("selection", row[2])

    def test_full_lifecycle_records_handoffs_and_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "stock_team.db"
            proposals.ensure_pipeline_tables(db_path)

            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        execution_order_id TEXT,
                        proposal_id INTEGER
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO trades (symbol, execution_order_id, proposal_id) VALUES (?, ?, NULL)",
                    ("sz.002466", "ord_test_1"),
                )
                conn.commit()

            analysis = {
                "code": "sz.002466",
                "name": "天齐锂业",
                "industry": "锂",
                "date": "2026-03-31",
                "price": 54.08,
                "score": 55,
                "recommendation": "推荐",
                "target_price": 64.90,
                "stop_loss": 45.97,
                "reasons": ["锂行业", "周期低位"],
                "fundamental_source": "snapshot",
            }
            prediction = {
                "id": "pred_1",
                "direction": "up",
                "confidence": 80,
                "target_price": 60.12,
                "reasons": ["技术面修复"],
                "risks": ["波动较大"],
                "rules_used": ["dir_rsi_oversold"],
                "signals": {"positive": 3, "negative": 1},
            }
            execution = {
                "order_id": "ord_test_1",
                "fill_price": 54.15,
                "filled_shares": 500,
                "status": "filled",
                "created_at": "2026-03-31T10:01:00",
            }

            with patch.object(proposals, "get_portfolio_baseline_date", return_value="2026-03-31"):
                research = proposals.create_or_update_research_proposal(analysis, db_path=db_path)
                quant = proposals.record_quant_validation(
                    "sz.002466",
                    prediction,
                    technicals={"technical_score": 72, "rsi": 28.5, "macd": "golden_cross"},
                    db_path=db_path,
                )
                risk = proposals.record_risk_review(
                    research["proposal_id"],
                    "sz.002466",
                    risk_level="low",
                    notes="风控通过",
                    passed=True,
                    suggested_position=0.15,
                    max_position=0.15,
                    db_path=db_path,
                )
                cio = proposals.apply_cio_decision(
                    research["proposal_id"],
                    approved=True,
                    reason="研究与量化一致向上",
                    summary={"confidence": 80},
                    db_path=db_path,
                )
                trader = proposals.mark_proposal_executed(research["proposal_id"], execution, db_path=db_path)
                snapshot = proposals.get_pipeline_snapshot(db_path=db_path)

            self.assertEqual(research["status"], "pending")
            self.assertEqual(quant["status"], "quant_validated")
            self.assertEqual(risk["status"], "risk_checked")
            self.assertEqual(cio["status"], "approved")
            self.assertEqual(trader["status"], "executed")
            self.assertEqual(snapshot["counts"]["executed"], 1)
            self.assertGreaterEqual(len(snapshot["recent_handoffs"]), 4)

            with sqlite3.connect(db_path) as conn:
                proposal_row = conn.execute("SELECT status FROM proposals WHERE id = ?", (research["proposal_id"],)).fetchone()
                trade_row = conn.execute("SELECT proposal_id FROM trades WHERE execution_order_id = ?", ("ord_test_1",)).fetchone()

            self.assertEqual(proposal_row[0], "executed")
            self.assertEqual(trade_row[0], research["proposal_id"])


if __name__ == "__main__":
    unittest.main()
