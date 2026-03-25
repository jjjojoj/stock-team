import unittest

from web.enhanced_cron_handler import derive_display_status


class EnhancedCronHandlerTests(unittest.TestCase):
    def test_message_failure_is_downgraded_to_warning(self):
        status = derive_display_status(
            {"delivery": {"mode": "announce"}},
            {
                "lastRunStatus": "error",
                "lastError": "⚠️ ✉️ Message failed",
                "lastDeliveryStatus": "delivered",
            }
        )

        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["status_label"], "notify_failed")
        self.assertEqual(status["raw_status"], "error")

    def test_legacy_message_failure_on_none_delivery_is_marked_as_history(self):
        status = derive_display_status(
            {"delivery": {"mode": "none"}, "updatedAtMs": 200},
            {
                "lastRunStatus": "error",
                "lastError": "⚠️ ✉️ Message failed",
                "lastDeliveryStatus": "delivered",
                "lastRunAtMs": 100,
            }
        )

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["status_label"], "history_cleared")
        self.assertIn("脚本 webhook", status["status_detail"])

    def test_running_at_timestamp_takes_priority_over_previous_error(self):
        status = derive_display_status(
            {"delivery": {"mode": "none"}},
            {
                "lastRunStatus": "error",
                "lastError": "⚠️ ✉️ Message failed",
                "runningAtMs": 1774404727776,
            }
        )

        self.assertEqual(status["status"], "running")
        self.assertEqual(status["status_label"], "running")


if __name__ == "__main__":
    unittest.main()
