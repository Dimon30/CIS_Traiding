import unittest

import pandas as pd

from scripts.evaluation.contracts import TemporalRole
from scripts.evaluation.temporal import (
    assert_label_window_before,
    assert_role_disjointness,
    build_v3_outer_fold,
    slice_role,
    validate_corridor_synchronization,
)


class TemporalProtocolV3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {"date": pd.date_range("2016-09-02", "2026-08-29", freq="D")}
        )

    def test_outer_2022_has_separate_decision_blocks(self) -> None:
        fold = build_v3_outer_fold(2022, 3)
        self.assertEqual(len(fold.inner_folds), 1)
        self.assertEqual(fold.refit_train.end_exclusive, pd.Timestamp("2019-12-29"))
        self.assertEqual(fold.calibration.start, pd.Timestamp("2020-01-01"))
        self.assertEqual(fold.calibration.end_exclusive, pd.Timestamp("2020-12-29"))
        self.assertEqual(fold.policy.start, pd.Timestamp("2021-01-01"))
        self.assertEqual(fold.policy.end_exclusive, pd.Timestamp("2021-12-29"))
        self.assertEqual(fold.outer_test.start, pd.Timestamp("2022-01-01"))

    def test_inner_history_expands_without_seeing_later_roles(self) -> None:
        fold = build_v3_outer_fold(2026, 3)
        self.assertEqual([item.validation_year for item in fold.inner_folds], list(range(2019, 2024)))
        self.assertEqual(
            [item.train.end_exclusive for item in fold.inner_folds],
            [pd.Timestamp(year, 1, 1) - pd.Timedelta(days=3) for year in range(2019, 2024)],
        )

    def test_partial_fold_uses_label_complete_cutoff(self) -> None:
        fold = build_v3_outer_fold(
            2026,
            3,
            observed_data_cutoff=pd.Timestamp("2026-09-02"),
            label_complete_through=pd.Timestamp("2026-08-29"),
        )
        self.assertTrue(fold.is_partial_fold)
        self.assertEqual(fold.outer_test.end_exclusive, pd.Timestamp("2026-08-30"))

    def test_roles_are_disjoint_and_purged(self) -> None:
        fold = build_v3_outer_fold(2022, 3)
        calibration = slice_role(self.frame, fold.calibration)
        policy = slice_role(self.frame, fold.policy)
        test = slice_role(self.frame, fold.outer_test)
        assert_role_disjointness([calibration, policy, test])
        assert_label_window_before(calibration, fold.policy.start, 3, "calibration")
        assert_label_window_before(policy, fold.outer_test.start, 3, "policy")
        self.assertEqual(set(test["temporal_role"]), {TemporalRole.OUTER_TEST.value})

    def test_insufficient_corridor_rejects_whole_block(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=5).tolist() * 2,
                "corridor": ["RUB_TJS"] * 5 + ["RUB_UZS"] * 5,
            }
        )
        with self.assertRaisesRegex(ValueError, "RUB_KGS"):
            validate_corridor_synchronization(
                frame,
                ["RUB_TJS", "RUB_UZS", "RUB_KGS"],
                minimum_rows_per_corridor=5,
            )


if __name__ == "__main__":
    unittest.main()
