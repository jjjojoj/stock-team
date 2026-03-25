import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web.dashboard_v3 as dashboard
import scripts.auto_trader_v3 as auto_trader
import scripts.a_share_risk_monitor as risk_monitor
import scripts.circuit_breaker as circuit_breaker
import scripts.daily_web_search as daily_web_search
import scripts.daily_stock_research as daily_stock_research
import scripts.market_review_v2 as market_review
import scripts.news_trigger as news_trigger


class RealDataPathTests(unittest.TestCase):
    def test_dashboard_enhanced_cron_uses_actual_duration_only(self):
        cron_tasks = [
            {
                "id": "job-ok",
                "script_key": "selector",
                "status": "ok",
                "last_run_raw": 1,
                "duration_ms": 22096,
                "consecutive_errors": 0,
            },
            {
                "id": "job-error",
                "script_key": "rule_validator",
                "status": "error",
                "last_run_raw": 2,
                "duration_ms": 0,
                "consecutive_errors": 2,
            },
        ]

        with patch.object(dashboard, "get_openclaw_cron_status", return_value=cron_tasks):
            snapshot = dashboard.get_enhanced_cron_data()

        self.assertEqual(snapshot["avg_duration_ms"], 22096)
        self.assertEqual(snapshot["cron_tasks"][0]["success_count"], 1)
        self.assertEqual(snapshot["cron_tasks"][1]["error_count"], 2)
        self.assertEqual(snapshot["cron_tasks"][1]["avg_duration_ms"], 0)

    def test_daily_stock_research_parses_stock_pool_and_fundamentals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            (config_dir / "stock_pool.md").write_text(
                "\n".join(
                    [
                        "### 铜",
                        "| 代码 | 名称 | 实控人 | 主营 | 市值 | PB | 关注理由 |",
                        "|------|------|--------|------|------|----|----------|",
                        "| 601168 | 西部矿业 | 青海国资委 | 铜+锌 | ~200亿 | - | 铜资源禀赋好 |",
                    ]
                ),
                encoding="utf-8",
            )
            (config_dir / "fundamental_data.md").write_text(
                "\n".join(
                    [
                        "### 铜",
                        "| 代码 | 名称 | PB | PE(TTM) | ROE(%) | 净利润增长(%) | 股息率(%) | 更新日期 |",
                        "|------|------|-----|---------|--------|--------------|-----------|----------|",
                        "| sh.601168 | 西部矿业 | 1.85 | 12.5 | 15.2 | +25.3 | 1.8 | 2026-02-27 |",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(daily_stock_research, "CONFIG_DIR", config_dir):
                candidates = daily_stock_research.load_stock_pool_candidates()
                snapshot = daily_stock_research.load_fundamental_snapshot()

        self.assertEqual(candidates[0]["code"], "sh.601168")
        self.assertEqual(candidates[0]["industry"], "铜")
        self.assertAlmostEqual(snapshot["sh.601168"]["roe"], 15.2)
        self.assertAlmostEqual(snapshot["sh.601168"]["dividend_yield"], 1.8)

    def test_policy_risk_uses_recent_search_news_and_tracked_targets(self):
        monitor = risk_monitor.AShareRiskMonitor()
        fake_news = [
            {
                "title": "证监会就江西铜业境外收购发出监管问询",
                "content": "监管问询可能影响江西铜业相关项目推进",
                "source": "江西铜业",
                "url": "https://example.test/news",
            }
        ]

        with (
            patch.object(monitor, "_load_recent_policy_news", return_value=fake_news),
            patch.object(risk_monitor, "load_watchlist", return_value={"sh.600362": {"name": "江西铜业", "industry": "铜"}}),
            patch.object(risk_monitor, "load_positions", return_value={}),
        ):
            risks = monitor.check_policy_risk()

        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0]["severity"], "high")
        self.assertEqual(risks[0]["affected"][0]["name"], "江西铜业")

    def test_auto_trader_uses_real_quote_fallback_before_simulation(self):
        trader = auto_trader.AutoTraderV3()
        trader.dm = None

        with (
            patch.object(trader, "_get_fallback_quote_price", return_value=12.34),
            patch.object(trader, "_get_simulated_price", return_value=99.99),
        ):
            price = trader.get_realtime_price("sh.600459")

        self.assertEqual(price, 12.34)

    def test_daily_web_search_uses_storage_positions(self):
        searcher = daily_web_search.WebSearcher.__new__(daily_web_search.WebSearcher)
        searcher.tavily_key = "test"
        searcher.newsapi_key = "test"

        with (
            patch.object(daily_web_search, "load_positions", return_value={"sh.600459": {"name": "贵研铂业"}}),
            patch.object(searcher, "tavily_search", return_value=[{"title": "news"}]),
        ):
            results = searcher.search_holdings()

        self.assertIn("贵研铂业", results)

    def test_news_trigger_falls_back_to_daily_search_and_storage_positions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_dir = temp_root / "data" / "daily_search"
            data_dir.mkdir(parents=True, exist_ok=True)
            (temp_root / "data" / "news_cache.json").parent.mkdir(parents=True, exist_ok=True)
            (temp_root / "data" / "news_cache.json").write_text('{"processed":[]}', encoding="utf-8")
            (temp_root / "data" / "predictions.json").write_text('{"active":{},"history":[]}', encoding="utf-8")
            (data_dir / "20260326.json").write_text(
                json.dumps(
                    {
                        "date": "2026-03-26 08:30",
                        "watchlist": {
                            "贵研铂业": [
                                {
                                    "title": "贵研铂业获新增订单",
                                    "content": "公司新增贵金属订单，盈利预期改善",
                                    "url": "https://example.test/a",
                                }
                            ]
                        },
                        "holdings": {},
                        "market_overview": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with (
                patch.object(news_trigger, "PROJECT_ROOT", str(temp_root)),
                patch.object(news_trigger, "NEWS_CACHE_FILE", str(temp_root / "data" / "news_cache.json")),
                patch.object(news_trigger, "PREDICTIONS_FILE", str(temp_root / "data" / "predictions.json")),
                patch.object(news_trigger, "load_positions", return_value={"sh.600459": {"name": "贵研铂业"}}),
                patch.object(news_trigger, "load_watchlist", return_value={}),
            ):
                monitor = news_trigger.NewsMonitor()
                recent = monitor._fetch_recent_news()

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["title"], "贵研铂业获新增订单")

    def test_market_review_position_analysis_uses_portfolio_snapshot(self):
        review = market_review.MarketReview()

        with patch.object(
            market_review,
            "build_portfolio_snapshot",
            return_value={
                "positions": [
                    {
                        "code": "sh.600459",
                        "name": "贵研铂业",
                        "cost_price": 10.0,
                        "current_price": 10.8,
                    }
                ]
            },
        ):
            analysis = review._analyze_positions()

        self.assertEqual(analysis["total"], 1)
        self.assertEqual(analysis["profitable"], 1)

    def test_circuit_breaker_skips_synthetic_panic_when_unavailable(self):
        breaker = circuit_breaker.CircuitBreaker()
        with patch.object(breaker, "get_market_data", return_value={"000001.SH": {"change_pct": -1.0}}), patch.object(
            breaker, "get_panic_index", return_value=None
        ):
            status, rules = breaker.check_market_conditions()

        self.assertEqual(status, breaker.STATUS_NORMAL)
        self.assertEqual(rules, [])


if __name__ == "__main__":
    unittest.main()
