import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import selector


class SelectorTests(unittest.TestCase):
    def test_top_filters_out_low_score_candidates(self):
        mock_results = [
            {"name": "A", "code": "sh.600000", "controller": "央企", "sector": "银行", "sub_sector": "国有", "price": 10.0, "change_pct": 1.0, "market_cap": 100.0, "score": {"total": 45, "details": "高分"}},
            {"name": "B", "code": "sh.600001", "controller": "央企", "sector": "银行", "sub_sector": "国有", "price": 10.0, "change_pct": 1.0, "market_cap": 100.0, "score": {"total": 20, "details": "刚过线"}},
            {"name": "C", "code": "sh.600002", "controller": "央企", "sector": "银行", "sub_sector": "国有", "price": 10.0, "change_pct": 1.0, "market_cap": 100.0, "score": {"total": 19, "details": "不达标"}},
            {"name": "D", "code": "sh.600003", "controller": "央企", "sector": "银行", "sub_sector": "国有", "price": 10.0, "change_pct": 1.0, "market_cap": 100.0, "score": {"total": 0, "details": "淘汰"}},
        ]

        with patch.object(selector, "HAS_ADAPTERS", False):
            stock_selector = selector.StockSelector()

        with patch.object(stock_selector, "scan", return_value=mock_results):
            top = stock_selector.top(10)

        self.assertEqual([item["code"] for item in top], ["sh.600000", "sh.600001"])

    def test_format_top_report_mentions_threshold(self):
        report = selector.format_top_report([])
        self.assertIn("综合评分达到", report)
        self.assertIn(str(selector.MIN_TOP_CANDIDATE_SCORE), report)

    def test_format_top_report_uses_bulleted_layout(self):
        report = selector.format_top_report(
            [
                {
                    "name": "宝地矿业",
                    "code": "sh.601121",
                    "sector": "有色金属",
                    "sub_sector": "其他",
                    "price": 7.43,
                    "change_pct": -0.13,
                    "market_cap": 65.4,
                    "score": {"total": 27, "details": "PB=2.05(+9)"},
                    "technical": {"macd": "死叉", "kdj": "正常", "technical_score": 20},
                }
            ]
        )

        self.assertIn("- 评分：27/100", report)
        self.assertIn("- 亮点：PB=2.05(+9)", report)
        self.assertIn("- 技术面：MACD=死叉", report)


if __name__ == "__main__":
    unittest.main()
