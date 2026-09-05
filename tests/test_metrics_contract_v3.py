import unittest

import numpy as np
import pandas as pd

from scripts.evaluation.metrics import aggregate_signal_metrics, signal_metrics


class MetricsContractV3Test(unittest.TestCase):
    def test_aggregate_lift_uses_expected_hits_not_mean_cell_lift(self) -> None:
        cells = pd.DataFrame(
            {
                "signals": [10, 90],
                "signal_hits": [10, 45],
                "matched_random_hit_rate": [0.5, 0.5],
                "evaluation_days": [365, 365],
            }
        )
        result = aggregate_signal_metrics(cells)
        self.assertAlmostEqual(result["signal_hit_rate"], 0.55)
        self.assertAlmostEqual(result["matched_random_hit_rate"], 0.5)
        self.assertAlmostEqual(result["lift"], 1.1)

    def test_signal_metrics_include_downside_and_inactive_frequency(self) -> None:
        decisions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-06", "2025-01-12"]),
                "candidate": [True, True, True],
                "selected_signal": [True, True, True],
                "message_hit": [1, 0, 0],
                "future_regret_bps": [0.0, 100.0, 200.0],
            }
        )
        result = signal_metrics(
            decisions,
            exposure_start=pd.Timestamp("2025-01-01"),
            exposure_end_exclusive=pd.Timestamp("2025-02-01"),
            random_hit_rate=0.5,
        )
        self.assertAlmostEqual(result["signal_hit_rate"], 1 / 3)
        self.assertAlmostEqual(result["false_push_regret_bps_mean"], 150.0)
        self.assertAlmostEqual(result["p90_realized_regret_bps"], 180.0)
        self.assertEqual(result["cooldown_violations"], 0)

    def test_zero_signal_cell_is_not_dropped(self) -> None:
        decisions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01"]),
                "candidate": [False],
                "selected_signal": [False],
                "message_hit": [1],
                "future_regret_bps": [0.0],
            }
        )
        result = signal_metrics(
            decisions,
            exposure_start=pd.Timestamp("2025-01-01"),
            exposure_end_exclusive=pd.Timestamp("2025-02-01"),
        )
        self.assertEqual(result["signals"], 0)
        self.assertTrue(np.isnan(result["signal_hit_rate"]))

    def test_cooldown_guardrail_uses_the_frozen_parameter(self) -> None:
        decisions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-04"]),
                "candidate": [True, True],
                "selected_signal": [True, True],
                "message_hit": [1, 1],
                "future_regret_bps": [0.0, 0.0],
            }
        )
        permissive = signal_metrics(
            decisions,
            exposure_start=pd.Timestamp("2025-01-01"),
            exposure_end_exclusive=pd.Timestamp("2025-02-01"),
            cooldown_days=2,
        )
        strict = signal_metrics(
            decisions,
            exposure_start=pd.Timestamp("2025-01-01"),
            exposure_end_exclusive=pd.Timestamp("2025-02-01"),
            cooldown_days=4,
        )
        self.assertEqual(permissive["cooldown_violations"], 0)
        self.assertEqual(strict["cooldown_violations"], 1)


if __name__ == "__main__":
    unittest.main()
