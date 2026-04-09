import unittest
from datetime import datetime
from unittest.mock import patch

import scripts.ai_predictor as ai_predictor


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 10, 9, 30)


class AIPredictorTests(unittest.TestCase):
    def test_load_watchlist_no_longer_invents_default_universe(self):
        predictor = ai_predictor.AIPredictor.__new__(ai_predictor.AIPredictor)

        with patch.object(ai_predictor, "load_watchlist", return_value={}):
            watchlist = predictor._load_watchlist()

        self.assertEqual(watchlist, {})

    def test_prepare_prediction_slot_archives_stale_same_symbol_predictions(self):
        class DummyPredictionSystem:
            def __init__(self):
                self.predictions = {
                    "active": {
                        "pred_old": {
                            "id": "pred_old",
                            "code": "sh.600111",
                            "created_at": "2026-04-07T09:30:00",
                            "status": "active",
                        }
                    },
                    "history": [],
                }
                self.saved = 0

            def _save_predictions(self):
                self.saved += 1

        predictor = ai_predictor.AIPredictor.__new__(ai_predictor.AIPredictor)
        predictor.prediction_system = DummyPredictionSystem()

        with patch.object(ai_predictor, "datetime", FixedDateTime):
            allowed = predictor._prepare_prediction_slot("sh.600111")

        self.assertTrue(allowed)
        self.assertEqual(predictor.prediction_system.saved, 1)
        self.assertEqual(predictor.prediction_system.predictions["active"], {})
        archived = predictor.prediction_system.predictions["history"][0]
        self.assertEqual(archived["status"], "expired")
        self.assertEqual(archived["result"]["status"], "expired")
        self.assertIn("按交易日刷新", archived["retired_reason"])

    def test_prepare_prediction_slot_skips_when_today_prediction_exists(self):
        class DummyPredictionSystem:
            def __init__(self):
                self.predictions = {
                    "active": {
                        "pred_today": {
                            "id": "pred_today",
                            "code": "sh.600111",
                            "created_at": "2026-04-10T09:01:00",
                            "status": "active",
                        }
                    },
                    "history": [],
                }
                self.saved = 0

            def _save_predictions(self):
                self.saved += 1

        predictor = ai_predictor.AIPredictor.__new__(ai_predictor.AIPredictor)
        predictor.prediction_system = DummyPredictionSystem()

        with patch.object(ai_predictor, "datetime", FixedDateTime):
            allowed = predictor._prepare_prediction_slot("sh.600111")

        self.assertFalse(allowed)
        self.assertEqual(predictor.prediction_system.saved, 0)
        self.assertEqual(len(predictor.prediction_system.predictions["active"]), 1)


if __name__ == "__main__":
    unittest.main()
