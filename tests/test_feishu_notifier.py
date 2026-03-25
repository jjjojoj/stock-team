import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import feishu_notifier


class FeishuNotifierTests(unittest.TestCase):
    def test_build_card_payload_trims_long_content_under_safe_limit(self):
        content = "\n\n".join(
            f"第{i}段 " + ("测试内容" * 400)
            for i in range(1, 18)
        )

        payload = feishu_notifier._build_card_payload("超长测试", content, "info")
        encoded = feishu_notifier.json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.assertEqual(payload["msg_type"], "interactive")
        self.assertLessEqual(len(encoded), feishu_notifier.SAFE_JSON_BYTES)
        self.assertLessEqual(len(payload["card"]["elements"]), feishu_notifier.CARD_MAX_BLOCKS + 1)

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


if __name__ == "__main__":
    unittest.main()
