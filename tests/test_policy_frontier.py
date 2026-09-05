import unittest

import numpy as np
import pandas as pd

from scripts.evaluation.policy import (
    SelectedPolicy,
    apply_cooldown,
    apply_selected_policy,
    clustering_metrics,
    enumerate_policy_points,
    map_thresholds_to_frequency_budgets,
    select_operating_policy,
    thin_to_common_count,
)


class PolicyFrontierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2025-01-01", "2025-01-03", "2025-01-06", "2025-01-12"]
                ),
                "calibrated_score": [0.9, 0.8, 0.7, 0.6],
                "message_hit": [1, 0, 1, 1],
            }
        )

    def test_cooldown_requires_more_than_four_days(self) -> None:
        selected = apply_cooldown(self.frame, 0.6, 4)
        self.assertEqual(
            selected["date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2025-01-01", "2025-01-06", "2025-01-12"],
        )

    def test_frontier_includes_zero_signal_point_and_all_budgets(self) -> None:
        points = enumerate_policy_points(
            self.frame, cooldown_days=4, exposure_weeks=2.0
        )
        self.assertEqual(int(points.iloc[0]["signals"]), 0)
        frontier = map_thresholds_to_frequency_budgets(points, [0.1, 0.5, 1.5])
        self.assertEqual(len(frontier), 3)
        self.assertTrue((frontier["policy_signals_per_week"].dropna() <= frontier.loc[frontier["policy_signals_per_week"].notna(), "requested_signals_per_week"] + 1e-12).all())

    def test_budget_mapping_does_not_use_labels(self) -> None:
        left = enumerate_policy_points(self.frame, cooldown_days=4, exposure_weeks=2.0)
        changed = self.frame.copy()
        changed["message_hit"] = 1 - changed["message_hit"]
        right = enumerate_policy_points(changed, cooldown_days=4, exposure_weeks=2.0)
        left_frontier = map_thresholds_to_frequency_budgets(left, [0.5, 1.0])
        right_frontier = map_thresholds_to_frequency_budgets(right, [0.5, 1.0])
        np.testing.assert_allclose(left_frontier["threshold"], right_frontier["threshold"])

    def test_hard_constraint_has_no_fallback(self) -> None:
        points = enumerate_policy_points(self.frame, cooldown_days=4, exposure_weeks=2.0)
        points["matched_random_lift"] = 1.0
        selected = select_operating_policy(
            points, minimum_signals=10, maximum_signals_per_week=1.4
        )
        self.assertEqual(selected.status, "inactive")
        self.assertEqual(selected.inactive_reason, "no_feasible_policy")

    def test_thinning_uses_highest_scores_and_preserves_cooldown(self) -> None:
        decisions = apply_selected_policy(
            self.frame, SelectedPolicy(0.6, "active"), cooldown_days=4
        )
        thinned = thin_to_common_count(decisions, 2)
        self.assertEqual(thinned["calibrated_score"].tolist(), [0.9, 0.7])
        gaps = thinned.sort_values("date")["date"].diff().dt.days.dropna()
        self.assertTrue(gaps.gt(4).all())

    def test_clustering_metrics_use_calendar_gaps(self) -> None:
        signals = self.frame.iloc[[0, 2, 3]]
        metrics = clustering_metrics(signals)
        self.assertAlmostEqual(metrics["share_gaps_le_7_days"], 1.0)
        self.assertEqual(metrics["max_signals_in_28_calendar_days"], 3)


if __name__ == "__main__":
    unittest.main()
