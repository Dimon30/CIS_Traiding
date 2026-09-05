import unittest

import pandas as pd

from scripts.evaluation.universe import (
    build_eligible_universe,
    compute_universe_id,
    eligible_rows,
    validate_universe_independent_of_model,
)


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "corridor": ["RUB_TJS"] * 3,
            "rub_per_unit": [10.0, 10.0, 9.9],
            "has_full_window": [False, True, True],
            "same_rate_as_previous": [False, True, False],
            "horizon_calendar_days": [3, 3, 3],
        }
    )


class EvaluationUniverseTest(unittest.TestCase):
    def test_reasons_are_explicit(self) -> None:
        universe = build_eligible_universe(sample_frame())
        self.assertEqual(
            universe["ineligible_reason"].tolist(),
            ["incomplete_target_window", "unchanged_effective_rate", "eligible"],
        )
        self.assertEqual(eligible_rows(universe)["date"].tolist(), [pd.Timestamp("2026-01-03")])

    def test_feature_columns_do_not_change_universe_hash(self) -> None:
        left = build_eligible_universe(sample_frame())
        right_source = sample_frame().assign(arbitrary_feature=[1.0, None, 3.0])
        right = build_eligible_universe(right_source)
        self.assertEqual(compute_universe_id(left), compute_universe_id(right))

    def test_horizon_contract_changes_universe_hash(self) -> None:
        left = build_eligible_universe(sample_frame())
        right = left.copy()
        right["horizon_calendar_days"] = 5
        self.assertNotEqual(compute_universe_id(left), compute_universe_id(right))

    def test_models_must_share_universe(self) -> None:
        universe = build_eligible_universe(sample_frame())
        identifier = validate_universe_independent_of_model(
            {"model_a": universe, "model_b": universe.copy()}
        )
        self.assertEqual(identifier, compute_universe_id(universe))


if __name__ == "__main__":
    unittest.main()
