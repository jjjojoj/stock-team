import unittest

from web.enhanced_cron_handler import derive_display_status


class EnhancedCronHandlerTests(unittest.TestCase):
    def test_message_failure_is_downgraded_to_warning(self):
        status = derive_display_status(
            {
                "lastRunStatus": "error",
                "lastError": "⚠️ ✉️ Message failed",
                "lastDeliveryStatus": "delivered",
            }
        )

        self.assertEqual(status["status"], "warning")
        self.assertEqual(status["status_label"], "notify_failed")
        self.assertEqual(status["raw_status"], "error")


if __name__ == "__main__":
    unittest.main()
