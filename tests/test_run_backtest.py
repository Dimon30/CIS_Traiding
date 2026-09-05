from datetime import datetime
import unittest

import numpy as np
import pandas as pd

from scripts.run_backtest import (
    LogisticModel,
    apply_cooldown,
    random_schedule_completion_counts,
    random_schedule_indices,
    random_schedule_state,
)


class RunBacktestTest(unittest.TestCase):
    def test_cooldown_keeps_first_signal_then_waits_full_pause(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-06"]),
                "score": [0.9, 0.8, 0.7],
            }
        )
        selected = apply_cooldown(frame, threshold=0.5, cooldown_days=4)
        self.assertEqual(selected["date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-01-01", "2026-01-06"])

    def test_random_schedule_respects_cooldown(self) -> None:
        dates = pd.Series(pd.date_range(datetime(2026, 1, 1), periods=30, freq="D"))
        selected = random_schedule_indices(dates, 5, 4, np.random.default_rng(42))
        chosen = sorted(dates.iloc[selected].tolist())
        self.assertEqual(len(chosen), 5)
        self.assertTrue(all((right - left).days > 4 for left, right in zip(chosen, chosen[1:])))

    def test_random_schedule_returns_requested_count(self) -> None:
        dates = pd.Series(pd.date_range(datetime(2026, 1, 1), periods=365, freq="D"))
        selected = random_schedule_indices(dates, 50, 4, np.random.default_rng(7))
        self.assertEqual(len(selected), 50)

    def test_random_schedule_counts_all_feasible_combinations(self) -> None:
        dates = pd.Series(pd.date_range(datetime(2026, 1, 1), periods=3, freq="D"))
        next_index, _ = random_schedule_state(dates, cooldown_days=0)
        ways = random_schedule_completion_counts(next_index, count=2)
        self.assertEqual(ways[0][2], 3)

    def test_logistic_model_ranks_separable_examples(self) -> None:
        x = pd.DataFrame({"feature": [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0]})
        y = pd.Series([0, 0, 0, 1, 1, 1])
        model = LogisticModel(l2=0.1).fit(x, y)
        scores = model.predict_proba(x)
        self.assertTrue(np.all(np.diff(scores) > 0))
        self.assertLess(scores[0], 0.5)
        self.assertGreater(scores[-1], 0.5)


if __name__ == "__main__":
    unittest.main()
