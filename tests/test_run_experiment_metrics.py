import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_hypotheses import paired_lift_test
from run_experiment import (
    design_matrix,
    metric_views,
    strategy_semantics,
    summarize,
    threshold_for_group,
)


def fold_row(test_year: int, *, signals: int, weeks: float, lift: float) -> dict[str, object]:
    active = signals > 0
    return {
        "hypothesis_id": "H_TEST",
        "horizon_days": 3,
        "epsilon_bps": 50,
        "strategy": "pooled_with_corridor_thresholds",
        "model": "logistic",
        "corridor": "RUB_TJS",
        "test_year": test_year,
        "train_rows": 1000,
        "validation_rows": 200,
        "test_rows": 200,
        "feature_count": 2,
        "hyperparameters": "{}",
        "validation_auc": 0.65,
        "validation_pr_auc": 0.75,
        "train_target_rate": 0.58,
        "validation_target_rate": 0.59,
        "evaluation_weeks": weeks,
        "target_positives": 120,
        "target_rate": 0.6,
        "roc_auc": 0.7 if active else 0.5,
        "pr_auc": 0.8 if active else 0.6,
        "pr_auc_baseline": 0.6,
        "pr_auc_gain": 0.2 if active else 0.0,
        "pr_auc_ratio": 4 / 3 if active else 1.0,
        "brier": 0.2 if active else 0.25,
        "brier_baseline": 0.24,
        "brier_skill_score": 1 / 6 if active else -1 / 24,
        "log_loss": 0.6 if active else 0.7,
        "balanced_accuracy": 0.6,
        "candidate_precision": 0.8 if active else 0.0,
        "candidate_recall": 0.2 if active else 0.0,
        "candidates": 8 if active else 0,
        "candidates_per_week": 8 / weeks if active else 0.0,
        "threshold": 0.7,
        "signals": signals,
        "signals_per_week": signals / weeks,
        "suppressed_by_cooldown": 3 if active else 0,
        "signal_active": active,
        "signal_hits": 4 if active else 0,
        "false_pushes": 1 if active else 0,
        "signal_hit_rate": 0.8 if active else np.nan,
        "hit_rate_ci_low": 0.4 if active else np.nan,
        "hit_rate_ci_high": 0.95 if active else np.nan,
        "false_push_rate": 0.2 if active else np.nan,
        "random_hit_rate": 0.5 if active else np.nan,
        "random_hit_rate_ci_low": 0.3 if active else np.nan,
        "random_hit_rate_ci_high": 0.7 if active else np.nan,
        "lift": lift,
        "moment_advantage_bps_mean": 10.0 if active else np.nan,
        "future_regret_bps_mean": 5.0 if active else np.nan,
        "client_advantage_rub_mean": 100.0 if active else np.nan,
        "client_regret_rub_mean": 50.0 if active else np.nan,
    }


class ExperimentMetricTest(unittest.TestCase):
    def test_pooling_strategy_can_hide_corridor_identity(self) -> None:
        frame = pd.DataFrame(
            {"corridor": ["RUB_TJS", "RUB_UZS"], "return_1": [0.1, 0.2]}
        )

        pooled, include_corridor, global_threshold = strategy_semantics(
            "pooled_without_corridor_feature"
        )
        matrix = design_matrix(frame, ["return_1"], include_corridor, ["TJS", "UZS"])

        self.assertTrue(pooled)
        self.assertFalse(include_corridor)
        self.assertFalse(global_threshold)
        self.assertEqual(list(matrix.columns), ["return_1"])

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            strategy_semantics("typo")

    def test_summary_keeps_inactive_fold_in_coverage_and_frequency(self) -> None:
        folds = pd.DataFrame(
            [
                fold_row(2025, signals=5, weeks=10.0, lift=1.6),
                fold_row(2026, signals=0, weeks=5.0, lift=np.nan),
            ]
        )

        result = summarize(folds).iloc[0]

        self.assertEqual(result["folds"], 2)
        self.assertEqual(result["active_folds"], 1)
        self.assertEqual(result["inactive_folds"], 1)
        self.assertAlmostEqual(result["active_fold_share"], 0.5)
        self.assertAlmostEqual(result["signals_per_week"], 5 / 15)
        self.assertAlmostEqual(result["roc_auc"], 0.6)

    def test_metric_views_separate_model_candidate_and_signal_columns(self) -> None:
        folds = pd.DataFrame([fold_row(2025, signals=5, weeks=10.0, lift=1.6)])

        views = metric_views(folds)

        self.assertEqual(
            set(views),
            {
                "model_metrics.csv",
                "candidate_policy_metrics.csv",
                "signal_policy_metrics.csv",
            },
        )
        self.assertIn("pr_auc", views["model_metrics.csv"])
        self.assertNotIn("lift", views["model_metrics.csv"])
        self.assertIn("candidate_precision", views["candidate_policy_metrics.csv"])
        self.assertIn("lift", views["signal_policy_metrics.csv"])

    @patch("run_experiment.random_baseline", return_value=(0.5, 0.4, 0.6))
    def test_validation_threshold_uses_matched_random_lift(self, _) -> None:
        validation = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=20, freq="D"),
                "score": np.linspace(0.1, 0.9, 20),
                "message_hit": [0, 1] * 10,
            }
        )

        threshold, tradeoffs = threshold_for_group(
            validation,
            cooldown_days=0,
            min_signals=2,
            max_signals_per_week=20.0,
            random_repeats=10,
            seed=42,
        )

        selected = [row for row in tradeoffs if row["threshold"] == threshold]
        self.assertEqual(len(selected), 1)
        self.assertIn("matched_random_hit_rate", selected[0])
        self.assertAlmostEqual(
            selected[0]["matched_random_lift"],
            selected[0]["signal_hit_rate"] / 0.5,
        )

    def test_paired_lift_reports_asymmetric_policy_coverage(self) -> None:
        folds = pd.DataFrame(
            [
                {"hypothesis_id": "LEFT", "horizon_days": 3, "epsilon_bps": 50, "model": "logistic", "strategy": "pooled", "corridor": "RUB_TJS", "test_year": 2025, "signals": 5, "lift": 1.2},
                {"hypothesis_id": "RIGHT", "horizon_days": 3, "epsilon_bps": 50, "model": "logistic", "strategy": "pooled", "corridor": "RUB_TJS", "test_year": 2025, "signals": 5, "lift": 1.4},
                {"hypothesis_id": "LEFT", "horizon_days": 3, "epsilon_bps": 50, "model": "logistic", "strategy": "pooled", "corridor": "RUB_TJS", "test_year": 2026, "signals": 4, "lift": 1.3},
                {"hypothesis_id": "RIGHT", "horizon_days": 3, "epsilon_bps": 50, "model": "logistic", "strategy": "pooled", "corridor": "RUB_TJS", "test_year": 2026, "signals": 0, "lift": np.nan},
            ]
        )

        result = paired_lift_test(
            folds,
            {"hypothesis_id": "LEFT"},
            {"hypothesis_id": "RIGHT"},
            "test",
        )

        self.assertEqual(result["corridor_year_cells"], 2)
        self.assertEqual(result["left_active_cells"], 2)
        self.assertEqual(result["right_active_cells"], 1)
        self.assertEqual(result["common_active_cells"], 1)
        self.assertEqual(result["all_time_blocks"], 2)
        self.assertEqual(result["n_time_blocks"], 1)


if __name__ == "__main__":
    unittest.main()
