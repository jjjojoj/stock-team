import sqlite3
import tempfile
import unittest
from pathlib import Path

import core.storage as storage


class RuleStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "stock_team.db"
        self.watchlist_file = Path(self.temp_dir.name) / "watchlist.json"
        self.rules_file = Path(self.temp_dir.name) / "prediction_rules.json"
        self.validation_pool_file = Path(self.temp_dir.name) / "rule_validation_pool.json"
        self.rejected_rules_file = Path(self.temp_dir.name) / "rejected_rules.json"

        self.original_watchlist_file = storage.WATCHLIST_FILE
        self.original_rules_file = storage.RULES_FILE
        self.original_validation_pool_file = storage.VALIDATION_POOL_FILE
        self.original_rejected_rules_file = storage.REJECTED_RULES_FILE

        storage.WATCHLIST_FILE = self.watchlist_file
        storage.RULES_FILE = self.rules_file
        storage.VALIDATION_POOL_FILE = self.validation_pool_file
        storage.REJECTED_RULES_FILE = self.rejected_rules_file

    def tearDown(self):
        storage.WATCHLIST_FILE = self.original_watchlist_file
        storage.RULES_FILE = self.original_rules_file
        storage.VALIDATION_POOL_FILE = self.original_validation_pool_file
        storage.REJECTED_RULES_FILE = self.original_rejected_rules_file
        self.temp_dir.cleanup()

    def test_watchlist_round_trip_prefers_database(self):
        watchlist = {
            "sh.600000": {
                "name": "浦发银行",
                "industry": "银行",
                "added_date": "2026-03-25",
                "reason": "低估值",
                "target_price": 12.0,
                "stop_loss": 9.5,
                "priority": "high",
                "score": 88,
            }
        }

        storage.save_watchlist(watchlist, db_path=self.db_path)
        loaded = storage.load_watchlist({}, db_path=self.db_path)

        self.assertEqual(loaded["sh.600000"]["name"], "浦发银行")
        self.assertEqual(loaded["sh.600000"]["priority"], "high")
        self.assertTrue(self.watchlist_file.exists())

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT symbol, name, priority, stop_loss FROM watchlist"
        ).fetchone()
        conn.close()

        self.assertEqual(row[0], "sh.600000")
        self.assertEqual(row[1], "浦发银行")
        self.assertEqual(row[2], "high")
        self.assertEqual(row[3], 9.5)

    def test_rule_collections_round_trip_to_sqlite(self):
        rules = {
            "direction_rules": {
                "dir_rsi_oversold": {
                    "condition": "RSI < 30",
                    "prediction": "未来5日上涨概率>60%",
                    "confidence_boost": 10,
                    "samples": 3,
                    "success_rate": 2 / 3,
                    "source": "技术分析",
                }
            }
        }
        validation_pool = {
            "rule_book_001_1": {
                "source": "book_001.point_001",
                "source_book": "股票作手回忆录",
                "rule": "价格总是沿最小阻力线运动",
                "testable_form": "突破 20 日高点后，价格继续上涨概率>55%",
                "category": "趋势",
                "backtest": {"samples": 26, "success_rate": 0.57, "avg_profit": 0.12, "avg_loss": 0.05, "profit_factor": 2.4},
                "live_test": {"samples": 5, "success_rate": 0.6},
                "status": "validating",
                "confidence": 0.78,
                "created_at": "2026-03-25T09:30:00",
            }
        }
        rejected_rules = {
            "bad_rule_001": {
                "rule_id": "bad_rule_001",
                "category": "direction_rules",
                "rule": "错误规则",
                "status": "rejected",
                "confidence": 0.1,
                "reject_reason": "成功率过低",
                "rejected_at": "2026-03-25T16:00:00",
            }
        }

        storage.save_rules(rules, db_path=self.db_path)
        storage.save_validation_pool(validation_pool, db_path=self.db_path)
        storage.save_rejected_rules(rejected_rules, db_path=self.db_path)

        self.assertEqual(storage.load_rules({}, db_path=self.db_path), rules)
        self.assertEqual(storage.load_validation_pool({}, db_path=self.db_path), validation_pool)
        self.assertEqual(storage.load_rejected_rules({}, db_path=self.db_path), rejected_rules)

        conn = sqlite3.connect(self.db_path)
        counts = {
            "rules": conn.execute("SELECT COUNT(*) FROM prediction_rules").fetchone()[0],
            "pool": conn.execute("SELECT COUNT(*) FROM rule_validation_pool").fetchone()[0],
            "rejected": conn.execute("SELECT COUNT(*) FROM rejected_rules").fetchone()[0],
        }
        conn.close()

        self.assertEqual(counts["rules"], 1)
        self.assertEqual(counts["pool"], 1)
        self.assertEqual(counts["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
