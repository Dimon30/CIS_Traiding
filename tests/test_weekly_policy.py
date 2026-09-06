import itertools
import unittest

import numpy as np
import pandas as pd

from scripts.evaluation.audit import audit_continuous_schedules
from scripts.evaluation.metrics import aggregate_signal_metrics
from scripts.evaluation.policy import SelectedPolicy
from scripts.evaluation.weekly import (
    attractiveness_gate, DeliveryState, continuous_draws, baseline_frames,
    quality_points, select_weekly_policy, cadence,
)


class WeeklyPolicyTest(unittest.TestCase):
    def frame(self, dates):
        return pd.DataFrame({"date": pd.to_datetime(dates), "corridor": "RUB_TJS",
            "outer_fold": [str(pd.Timestamp(d).year) for d in dates],
            "calibrated_score": .9, "message_hit": 1, "future_regret_bps": 0.,
            "attractiveness_gate": True, "candidate": True, "selected_signal": True})

    def test_gate_calendar_excludes_today_and_future_and_preserves_rows(self):
        observations = pd.DataFrame({"date": pd.to_datetime(["2025-01-01", "2025-01-28", "2025-01-29", "2025-02-01"]),
            "corridor": "RUB_TJS", "rub_per_unit": [100.5, 100.5, 100., 10000.]})
        result = attractiveness_gate(observations)
        self.assertEqual(len(result), 4)
        self.assertFalse(result.loc[1, "history_complete"])
        self.assertEqual(result.loc[2, "history_days"], 28)
        self.assertAlmostEqual(result.loc[2, "past_advantage_bps"], 50.)
        self.assertTrue(result.loc[2, "attractiveness_gate"])
        observations.loc[3, "rub_per_unit"] = 1.
        pd.testing.assert_series_equal(result.loc[2], attractiveness_gate(observations).loc[2])
        self.assertEqual(result.loc[2, "median_applicable_rate_28d"], 100.5)

    def test_cooldown_survives_year_threshold_inactive_and_is_isolated(self):
        state = DeliveryState()
        first = self.frame(["2024-12-30"])
        state.apply(first, SelectedPolicy(.8, "active"), "main", 3)
        state.apply(self.frame(["2025-01-01"]), SelectedPolicy(None, "inactive"), "main", 3)
        next_frame = self.frame(["2025-01-02", "2025-01-04"])
        result = state.apply(next_frame, SelectedPolicy(.1, "active"), "main", 3)
        self.assertEqual(result["selected_signal"].tolist(), [False, True])
        self.assertTrue(state.apply(next_frame.head(1), SelectedPolicy(.1, "active"), "frontier", 3)["selected_signal"].iloc[0])
        self.assertTrue(state.apply(next_frame.head(1).assign(corridor="RUB_KZT"), SelectedPolicy(.1, "active"), "main", 3)["selected_signal"].iloc[0])

    def test_exact_sampler_matches_exhaustive_support_and_draw_isolation(self):
        frame = self.frame(["2024-12-28", "2024-12-30", "2025-01-02", "2025-01-04", "2025-01-06"])
        schedule = frame.iloc[[0, 2]]
        draws = continuous_draws(frame, schedule, mode="calendar_month", draws=800, seed=42, cooldown_days=3, stream_id="test")
        feasible = set()
        for a, b in itertools.product([0, 1], [2, 3, 4]):
            if (frame.iloc[b]["date"] - frame.iloc[a]["date"]).days > 3:
                feasible.add((frame.iloc[a]["date"], frame.iloc[b]["date"]))
        observed = draws.groupby("draw_id")["date"].apply(tuple)
        self.assertEqual(set(observed), feasible)
        for count in observed.value_counts():
            self.assertLess(abs(count / 800 - 1 / len(feasible)), .06)
        first = continuous_draws(frame, schedule, mode="calendar_month", draws=1, seed=42, cooldown_days=3, stream_id="test")
        pd.testing.assert_frame_equal(first.reset_index(drop=True), draws.loc[draws["draw_id"].eq(0)].reset_index(drop=True))
        audit_continuous_schedules(schedule, draws, 3)

    def test_single_schedule_weekday_quotas_and_infeasible(self):
        frame = self.frame(["2024-12-30", "2025-01-02", "2025-01-06"])
        schedule = frame.iloc[[0, 2]]
        draws = continuous_draws(frame, schedule, mode="calendar_month_weekday", draws=3, seed=4, cooldown_days=3, stream_id="single")
        self.assertTrue(all(value == tuple(schedule["date"]) for value in draws.groupby("draw_id")["date"].apply(tuple)))
        with self.assertRaisesRegex(ValueError, "No cooldown-feasible"):
            continuous_draws(frame.head(2), frame.head(2), mode="calendar_month", draws=1, seed=4, cooldown_days=3, stream_id="bad")

    def test_invalid_random_rates_and_zero(self):
        frame = pd.DataFrame({"signals": [2, 0], "signal_hits": [1, 0], "matched_random_hit_rate": [0., np.nan], "evaluation_days": [10, 10]})
        result = aggregate_signal_metrics(frame)
        self.assertTrue(np.isnan(result["lift"]))
        self.assertEqual(result["signal_hits"], 1)
        self.assertEqual(result["delta_hit_rate"], .5)
        for value in (None, np.nan, np.inf, -0.1, 1.1):
            frame.loc[0, "matched_random_hit_rate"] = value
            with self.assertRaisesRegex(ValueError, "finite random rate"):
                aggregate_signal_metrics(frame)

    def test_quality_full_exposure_fallback_and_tie_break(self):
        frame = self.frame(pd.date_range("2024-01-01", periods=20, freq="7D"))
        frame["attractiveness_gate"] = [True] * 12 + [False] * 8
        config = {"cooldown_days": 3, "minimum_policy_signals": 12, "minimum_safety": .75,
                  "maximum_mean_regret_bps": 40, "maximum_p90_regret_bps": 100}
        points = quality_points(frame, 52, config)
        self.assertAlmostEqual(points["signals_per_week"].max(), 12/52)
        self.assertEqual(select_weekly_policy(points).threshold, .9)
        frame["future_regret_bps"] = 200
        self.assertEqual(select_weekly_policy(quality_points(frame, 52, config)).status, "inactive")
        points = pd.DataFrame({"threshold": [.1, .2, .3, .4], "quality_pass": True,
            "signals_per_week": [.7, .7, .7, .6], "hit_rate_wilson_lower": [.7, .8, .8, .99], "mean_regret_bps": [0, 2, 2, 0]})
        self.assertEqual(select_weekly_policy(points).threshold, .3)

    def test_three_outcomes(self):
        frame = self.frame(["2025-01-01", "2025-01-07", "2025-01-14"])
        frame["attractiveness_gate"] = [True, False, True]
        frame["message_hit"] = [1, 1, 0]
        full, uid1, oid1 = baseline_frames(frame, "future_safety")
        product, uid2, oid2 = baseline_frames(frame, "product")
        conditional, uid3, oid3 = baseline_frames(frame, "conditional")
        self.assertEqual(full["message_hit"].tolist(), [1, 1, 0])
        self.assertEqual(product["message_hit"].tolist(), [1, 0, 0])
        self.assertEqual(conditional["message_hit"].tolist(), [1, 0])
        self.assertEqual(uid1, uid2)
        self.assertNotEqual(uid1, uid3)
        self.assertEqual(len({oid1, oid2, oid3}), 3)

    def test_continuous_cadence_and_audit(self):
        frame = self.frame(["2024-12-30", "2025-01-06", "2025-01-13"])
        metrics = cadence(frame, pd.Timestamp("2024-12-30"), pd.Timestamp("2025-01-20"))
        self.assertEqual(metrics["inter_signal_gap_days_p90"], 7)
        self.assertEqual(metrics["active_week_share"], 1)
        bad = self.frame(["2024-12-30", "2025-01-02"])
        with self.assertRaisesRegex(AssertionError, "Continuous cooldown"):
            audit_continuous_schedules(bad, bad.assign(draw_id=0), 3)


if __name__ == "__main__":
    unittest.main()
