import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.fundamentals as fundamentals


class FundamentalBundleTests(unittest.TestCase):
    def test_bundle_merges_snapshot_watchlist_and_legacy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            data_dir = Path(temp_dir) / "data"
            config_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)

            (config_dir / "fundamental_data.md").write_text(
                "\n".join(
                    [
                        "| 代码 | 名称 | PB | PE(TTM) | ROE(%) | 净利润增长(%) | 股息率(%) | 更新日期 |",
                        "|------|------|-----|---------|--------|--------------|-----------|----------|",
                        "| sh.601168 | 西部矿业 | 1.85 | 12.5 | 15.2 | +25.3 | 1.8 | 2026-03-26 |",
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(fundamentals, "CONFIG_DIR", config_dir),
                patch.object(fundamentals, "DATA_DIR", data_dir),
                patch.object(fundamentals, "LIVE_CACHE_FILE", data_dir / "live_fundamentals_cache.json"),
                patch.object(fundamentals, "load_live_market_snapshot", return_value={}),
            ):
                bundle = fundamentals.get_fundamental_bundle(
                    "601168",
                    watchlist_data={"sh.601168": {"market_cap": 321.5}},
                    legacy_data={"sh.601168": {"dividend_yield": 2.2}},
                )

        self.assertEqual(bundle["symbol"], "sh.601168")
        self.assertEqual(bundle["source"], "snapshot")
        self.assertAlmostEqual(bundle["pb"], 1.85)
        self.assertAlmostEqual(bundle["roe"], 15.2)
        self.assertAlmostEqual(bundle["market_cap"], 321.5)
        self.assertAlmostEqual(bundle["dividend_yield"], 1.8)


if __name__ == "__main__":
    unittest.main()
