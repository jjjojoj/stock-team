import unittest
from unittest.mock import patch

import scripts.ai_predictor as ai_predictor


class AIPredictorTests(unittest.TestCase):
    def test_load_watchlist_no_longer_invents_default_universe(self):
        predictor = ai_predictor.AIPredictor.__new__(ai_predictor.AIPredictor)

        with patch.object(ai_predictor, "load_watchlist", return_value={}):
            watchlist = predictor._load_watchlist()

        self.assertEqual(watchlist, {})


if __name__ == "__main__":
    unittest.main()
