from collections import Counter
import unittest

import numpy as np
import pandas as pd

from scripts.evaluation.random_baseline import (
    RandomDrawBank,
    RandomDrawKey,
    sample_quota_schedule_indices,
    schedule_quotas,
    stable_seed,
    stratum_values,
)


class RandomBaselineV3Test(unittest.TestCase):
    def test_quota_sampler_respects_count_and_cooldown(self) -> None:
        dates = pd.Series(pd.date_range("2025-01-01", periods=40, freq="D"))
        strata = pd.Series([date.strftime("%Y-%m") for date in dates])
        selected = sample_quota_schedule_indices(
            dates,
            strata,
            {"2025-01": 4, "2025-02": 1},
            4,
            np.random.default_rng(42),
        )
        chosen = dates.iloc[selected].sort_values()
        self.assertEqual(len(chosen), 5)
        self.assertTrue(chosen.diff().dt.days.dropna().gt(4).all())
        self.assertEqual(Counter(chosen.dt.strftime("%Y-%m")), {"2025-01": 4, "2025-02": 1})

    def test_impossible_quota_fails(self) -> None:
        dates = pd.Series(pd.date_range("2025-01-01", periods=5, freq="D"))
        with self.assertRaisesRegex(ValueError, "No cooldown-feasible"):
            sample_quota_schedule_indices(
                dates,
                pd.Series("ALL", index=dates.index),
                {"ALL": 3},
                4,
                np.random.default_rng(1),
            )

    def test_stable_seed_is_order_independent_of_process_hash(self) -> None:
        self.assertEqual(stable_seed(42, "RUB_TJS", 2025), stable_seed(42, "RUB_TJS", 2025))
        self.assertNotEqual(stable_seed(42, "RUB_TJS", 2025), stable_seed(42, "RUB_KGS", 2025))

    def test_draw_bank_reuses_identical_draw(self) -> None:
        universe = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=50, freq="D"),
                "message_hit": [0, 1] * 25,
                "future_regret_bps": np.arange(50),
                "eligible_gap_days": 1,
            }
        )
        schedule = universe.iloc[[0, 5, 10, 35, 40]]
        quotas = tuple(sorted(schedule_quotas(schedule, "calendar_month").items()))
        key = RandomDrawKey("universe", "RUB_TJS", "outer_2025", "calendar_month", quotas)
        bank = RandomDrawBank(42)
        left = bank.draw(universe, key, draw_id=7, cooldown_days=3)
        right = bank.draw(universe, key, draw_id=7, cooldown_days=3)
        self.assertEqual(left["date"].tolist(), right["date"].tolist())
        self.assertEqual(schedule_quotas(left, "calendar_month"), dict(quotas))

    def test_sampler_cache_does_not_cross_cooldown_contracts(self) -> None:
        universe = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=50, freq="D"),
                "message_hit": [0, 1] * 25,
                "future_regret_bps": np.arange(50),
                "eligible_gap_days": 1,
            }
        )
        key = RandomDrawKey(
            "universe", "RUB_TJS", "outer_2025", "fold_count_only", (("ALL", 5),)
        )
        bank = RandomDrawBank(42)
        bank.draw(universe, key, draw_id=1, cooldown_days=2)
        strict = bank.draw(universe, key, draw_id=1, cooldown_days=3)
        self.assertTrue(strict["date"].sort_values().diff().dt.days.dropna().gt(3).all())

    def test_draw_bank_bounds_sampler_cache(self) -> None:
        universe = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=50, freq="D"),
                "message_hit": [0, 1] * 25,
                "future_regret_bps": np.arange(50),
                "eligible_gap_days": 1,
            }
        )
        bank = RandomDrawBank(42, maximum_cached_samplers=2)
        for count in (2, 3, 4):
            key = RandomDrawKey(
                "universe",
                "RUB_TJS",
                "outer_2025",
                "fold_count_only",
                (("ALL", count),),
            )
            bank.draw(universe, key, draw_id=1, cooldown_days=3)
        self.assertLessEqual(len(bank._samplers), 2)

    def test_update_gap_strata_are_explicit(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-04"]),
                "eligible_gap_days": [1, 2, 3],
            }
        )
        values = stratum_values(frame, "month_update_gap")
        self.assertEqual(values.tolist(), ["2025-01|gap=1", "2025-01|gap=2", "2025-01|gap=3+"])


if __name__ == "__main__":
    unittest.main()
