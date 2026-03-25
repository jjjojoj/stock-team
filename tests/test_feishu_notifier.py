import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import feishu_notifier


class FeishuNotifierTests(unittest.TestCase):
    def test_get_default_webhook_prefers_env_then_local_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "feishu_config.json").write_text(
                json.dumps({"webhook_url": "", "daily_report_enabled": True}, ensure_ascii=False),
                encoding="utf-8",
            )
            (config_dir / "feishu_config.local.json").write_text(
                json.dumps({"webhook_url": "https://local.test/hook"}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.object(feishu_notifier, "PROJECT_ROOT", project_root):
                with patch.dict(feishu_notifier.os.environ, {}, clear=True):
                    self.assertEqual(
                        feishu_notifier.get_default_webhook_url(),
                        "https://local.test/hook",
                    )

                    with patch.dict(feishu_notifier.os.environ, {"FEISHU_WEBHOOK_URL": "https://env.test/hook"}):
                        self.assertEqual(
                            feishu_notifier.get_default_webhook_url(),
                            "https://env.test/hook",
                        )

    def test_build_card_payload_trims_long_content_under_safe_limit(self):
        content = "\n\n".join(
            f"第{i}段 " + ("测试内容" * 400)
            for i in range(1, 18)
        )

        payload = feishu_notifier._build_card_payload("超长测试", content, "info")
        encoded = feishu_notifier.json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertLessEqual(len(encoded), feishu_notifier.SAFE_JSON_BYTES)
        self.assertLessEqual(len(payload["card"]["body"]["elements"]), feishu_notifier.CARD_MAX_BLOCKS + 2)

    def test_send_feishu_message_falls_back_to_text_when_card_fails(self):
        captured_payloads = []

        def fake_post(payload, webhook_url):
            captured_payloads.append(payload)
            if payload["msg_type"] == "interactive":
                return False, {"code": 190001, "msg": "card too long"}
            return True, {"code": 0}

        with (
            patch.object(feishu_notifier, "get_default_webhook_url", return_value="https://example.test/hook"),
            patch.object(feishu_notifier, "_post_webhook", side_effect=fake_post),
        ):
            success = feishu_notifier.send_feishu_message("测试标题", "测试内容", level="info")

        self.assertTrue(success)
        self.assertEqual(len(captured_payloads), 2)
        self.assertEqual(captured_payloads[0]["msg_type"], "interactive")
        self.assertEqual(captured_payloads[1]["msg_type"], "text")

    def test_generate_portfolio_report_uses_unified_snapshot(self):
        snapshot = {
            "total_capital": 200000.0,
            "available_cash": 274898.0,
            "total_value": 0.0,
            "total_profit": 74898.0,
            "total_profit_pct": 37.449,
            "total_assets": 274898.0,
            "positions": [],
        }

        with patch.object(feishu_notifier, "build_portfolio_snapshot", return_value=snapshot):
            report = feishu_notifier.generate_portfolio_report("close")

        self.assertEqual(report["available_cash"], 274898.0)
        self.assertEqual(report["positions"], [])
        self.assertAlmostEqual(report["total_profit_pct"], 37.449)

    def test_format_report_handles_empty_positions_without_config_warning(self):
        portfolio = {
            "total_assets": 274898.0,
            "available_cash": 274898.0,
            "total_value": 0.0,
            "total_profit": 74898.0,
            "total_profit_pct": 37.45,
            "positions": [],
        }

        _, content, _ = feishu_notifier.format_report("close", portfolio)

        self.assertIn("当前空仓", content)
        self.assertNotIn("暂无持仓配置", content)


if __name__ == "__main__":
    unittest.main()
