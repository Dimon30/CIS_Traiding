import unittest

import pandas as pd

from scripts.evaluation.uncertainty import (
    model_vs_random_bootstrap,
    paired_policy_bootstrap,
    synchronized_bootstrap_weights,
)


class UncertaintyTest(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.date_range("2025-01-01", periods=60, freq="D")
        rows = []
        for corridor in ("RUB_TJS", "RUB_KGS"):
            for index, date in enumerate(dates):
                rows.append(
                    {
                        "outer_fold": "outer_2025",
                        "date": date,
                        "corridor": corridor,
                        "selected_signal": index % 6 == 0,
                        "message_hit": int(index % 3 != 0),
                        "future_regret_bps": float(index),
                    }
                )
        self.decisions = pd.DataFrame(rows)
        self.exposures = pd.DataFrame(
            {
                "outer_fold": ["outer_2025"],
                "exposure_start": [pd.Timestamp("2025-01-01")],
                "exposure_end_exclusive": [pd.Timestamp("2025-03-02")],
            }
        )

    def test_weights_are_one_shared_calendar(self) -> None:
        weights = synchronized_bootstrap_weights(
            self.exposures, block_days=14, replicates=2, seed=10
        )
        self.assertEqual(len(weights), 2)
        self.assertEqual(int(weights[0]["bootstrap_weight"].sum()), 60)
        self.assertFalse(weights[0]["bootstrap_weight"].equals(weights[1]["bootstrap_weight"]))

    def test_identical_models_have_zero_paired_delta(self) -> None:
        result = paired_policy_bootstrap(
            self.decisions,
            self.decisions.copy(),
            self.exposures,
            block_days=14,
            replicates=20,
            seed=42,
        )
        self.assertTrue(result["delta_hit_rate"].fillna(0).eq(0).all())
        self.assertTrue(result["delta_mean_regret_bps"].fillna(0).eq(0).all())

    def test_model_random_bootstrap_preserves_shared_calendar_and_downside(self) -> None:
        schedules = self.decisions.loc[self.decisions["selected_signal"]].copy()
        schedules["draw_id"] = 0
        result = model_vs_random_bootstrap(
            self.decisions,
            schedules,
            self.exposures,
            block_days=14,
            replicates=10,
            seed=42,
        )
        self.assertTrue(result["delta_hit_rate"].fillna(0).eq(0).all())
        self.assertTrue(result["delta_mean_regret_bps"].fillna(0).eq(0).all())

    def test_paired_models_must_have_identical_oot_rows(self) -> None:
        with self.assertRaisesRegex(AssertionError, "identical OOT row keys"):
            paired_policy_bootstrap(
                self.decisions.iloc[:-1],
                self.decisions,
                self.exposures,
                block_days=14,
                replicates=2,
            )


if __name__ == "__main__":
    unittest.main()
