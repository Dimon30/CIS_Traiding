import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate_fast_slow import slow_candidates


class FastSlowTest(unittest.TestCase):
    def test_confirmation_requires_two_consecutive_scores(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                "rub_per_unit": [10.0, 10.1, 10.2],
                "score": [0.8, 0.4, 0.9],
            }
        )
        self.assertTrue(slow_candidates(frame, 0.7, 3).empty)

    def test_waiting_cost_is_positive_when_recipient_currency_gets_dearer(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-03"]),
                "rub_per_unit": [10.0, 10.1],
                "score": [0.8, 0.9],
            }
        )
        signals = slow_candidates(frame, 0.7, 3)
        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(float(signals.iloc[0]["waiting_cost_bps"]), 100.0)


if __name__ == "__main__":
    unittest.main()
