import unittest
from datetime import datetime

from core.predictions import (
    apply_prediction_verdict,
    build_prediction_record,
    normalize_prediction_record,
)


class PredictionUtilsTests(unittest.TestCase):
    def test_build_prediction_record_sets_due_at_from_timeframe(self):
        created_at = datetime(2026, 3, 25, 9, 30)
        record = build_prediction_record(
            {
                "code": "sh.600000",
                "name": "浦发银行",
                "direction": "up",
                "target_price": 12.5,
                "current_price": 10.0,
                "confidence": 70,
                "timeframe": "1周",
            },
            created_at=created_at,
        )

        self.assertEqual(record["status"], "active")
        self.assertEqual(record["due_at"], "2026-04-01T09:30:00")

    def test_apply_prediction_verdict_marks_partial_correctly(self):
        record = build_prediction_record(
            {
                "code": "sh.600000",
                "name": "浦发银行",
                "direction": "up",
                "target_price": 12.0,
                "current_price": 10.0,
                "confidence": 70,
                "timeframe": "1周",
            },
            created_at=datetime(2026, 3, 25, 9, 30),
        )

        verified = apply_prediction_verdict(record, 11.0, datetime(2026, 4, 1, 15, 0))

        self.assertEqual(verified["status"], "verified")
        self.assertTrue(verified["result"]["partial"])
        self.assertEqual(verified["result"]["status"], "partial")

    def test_normalize_prediction_record_supports_legacy_result_strings(self):
        normalized = normalize_prediction_record(
            {
                "id": "legacy_001",
                "code": "sh.600000",
                "name": "浦发银行",
                "direction": "up",
                "target_price": 12.0,
                "current_price": 10.0,
                "confidence": 70,
                "timeframe": "1周",
                "created_at": "2026-03-25T09:30:00",
                "status": "verified",
                "result": "incorrect",
            }
        )

        self.assertEqual(normalized["result_status"], "wrong")
        self.assertFalse(normalized["result"]["correct"])
        self.assertFalse(normalized["result"]["partial"])


if __name__ == "__main__":
    unittest.main()
