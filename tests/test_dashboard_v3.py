import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web.dashboard_v3 as dashboard


class DashboardSnapshotTests(unittest.TestCase):
    def test_get_api_health_snapshot_flattens_nested_status(self):
        api_status = {
            "market": {
                "api": {
                    "healthy": True,
                    "response_time_ms": 120.5,
                    "last_check": "2026-03-25T10:00:00",
                    "consecutive_failures": 0,
                }
            },
            "search": {
                "api": {
                    "healthy": False,
                    "response_time_ms": 0,
                    "last_check": "2026-03-25T10:01:00",
                    "last_error": "timeout",
                    "consecutive_failures": 2,
                }
            },
        }

        with patch.object(dashboard, "load_json", return_value=api_status):
            snapshot = dashboard.get_api_health_snapshot()

        self.assertEqual(snapshot["healthy_count"], 1)
        self.assertEqual(snapshot["total_count"], 2)
        self.assertEqual(snapshot["services"][0]["domain"], "market")
        self.assertEqual(snapshot["services"][1]["last_error"], "timeout")

    def test_get_reports_snapshot_reads_weekly_report_and_strips_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            weekly_dir = root / "data" / "weekly_reports"
            review_dir = root / "data" / "reviews"
            weekly_dir.mkdir(parents=True)
            review_dir.mkdir(parents=True)

            (weekly_dir / "weekly_2026-03-16_2026-03-22.md").write_text(
                "\n".join(
                    [
                        "# 周总结报告",
                        "",
                        "**时间范围**: 2026-03-16 ~ 2026-03-22",
                        "",
                        "| 指标 | 数值 |",
                        "|------|------|",
                        "| **准确率** | **36.5%** |",
                        "| **综合得分** | **61.9%** |",
                        "",
                        "*报告自动生成 by 股票团队 AI*",
                    ]
                ),
                encoding="utf-8",
            )
            (review_dir / "review_2026-03-24.md").write_text(
                "# 复盘\n\n今日市场偏震荡，资源股相对更强。\n",
                encoding="utf-8",
            )

            with (
                patch.object(dashboard, "PROJECT_ROOT", root),
                patch.object(
                    dashboard,
                    "get_account_latest",
                    return_value={"date": "2026-03-24", "total_asset": 123456.0, "daily_profit": 321.0},
                ),
                patch.object(
                    dashboard,
                    "get_trades",
                    return_value=[{"executed_at": "2026-03-24 10:00:00", "direction": "buy", "name": "测试股份"}],
                ),
            ):
                snapshot = dashboard.get_reports_snapshot()

        self.assertEqual(snapshot["daily"]["date"], "2026-03-24")
        self.assertEqual(snapshot["weekly"]["period"], "2026-03-16 ~ 2026-03-22")
        self.assertEqual(snapshot["weekly"]["accuracy"], "36.5%")
        self.assertEqual(snapshot["weekly"]["score"], "61.9%")

    def test_get_backtest_results_parses_markdown_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs_dir = root / "outputs"
            outputs_dir.mkdir(parents=True)

            (outputs_dir / "backverify_20260325.md").write_text(
                "\n".join(
                    [
                        "# 回测结果",
                        "",
                        "**回测期间**: 2025-01-01 至 2026-03-25",
                        "",
                        "| 指标 | 数值 |",
                        "|------|------|",
                        "| 总收益率 | +5.20% |",
                        "| 最大回撤 | 4.10% |",
                        "| 夏普比率 | 1.32 |",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(dashboard, "PROJECT_ROOT", root):
                results = dashboard.get_backtest_results(5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["period"], "2025-01-01 至 2026-03-25")
        self.assertEqual(results[0]["return_pct"], "+5.20%")
        self.assertEqual(results[0]["max_drawdown"], "4.10%")
        self.assertEqual(results[0]["sharpe_ratio"], "1.32")

    def test_get_news_snapshot_filters_low_quality_rows_and_normalizes_direction(self):
        rows = [
            {
                "title": "公司业绩大幅增长，净利润同比增长150%",
                "sentiment": "neutral",
                "urgency": "中",
                "impact_score": 50.0,
                "news_time": None,
                "source": "",
                "event_types": '["政策法规","业绩财报","重组并购","订单合同","重大诉讼"]',
                "sentiment_confidence": 0.4,
                "display_time": None,
            },
            {
                "title": "证监会加强监管，发布新规",
                "sentiment": "negative",
                "urgency": "高",
                "impact_score": 72.0,
                "news_time": "2026-03-25 09:00:00",
                "source": "官方公告",
                "event_types": '["政策法规"]',
                "sentiment_confidence": 0.8,
                "display_time": "2026-03-25 09:00:00",
            },
        ]

        with (
            patch.object(dashboard, "query_sql", return_value=rows),
            patch.object(dashboard, "_get_recent_search_news", return_value=[]),
        ):
            snapshot = dashboard.get_news_snapshot(10)

        self.assertEqual(snapshot["today_count"], 1)
        self.assertEqual(snapshot["urgent_count"], 1)
        self.assertEqual(len(snapshot["news"]), 1)
        self.assertEqual(snapshot["news"][0]["direction_label"], "利空")
        self.assertEqual(snapshot["news"][0]["strength_label"], "强")
        self.assertEqual(snapshot["news"][0]["event_types_display"], "政策法规")


if __name__ == "__main__":
    unittest.main()
