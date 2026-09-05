import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_backtest import add_auxiliary_features, add_features, add_implied_usd_features
from run_experiment import split_frame


class FeaturePipelineTest(unittest.TestCase):
    def test_features_are_causal_when_future_rates_change(self) -> None:
        dates = pd.date_range("2025-01-01", periods=100, freq="D")
        base = pd.DataFrame(
            {
                "date": dates,
                "rub_per_unit": [100 + i / 10 for i in range(100)],
                "same_rate_as_previous": False,
            }
        )
        changed = base.copy()
        changed.loc[changed["date"] > "2025-03-01", "rub_per_unit"] *= 10
        left = add_features(base).loc[lambda x: x["date"] <= "2025-03-01"]
        right = add_features(changed).loc[lambda x: x["date"] <= "2025-03-01"]
        pd.testing.assert_frame_equal(left, right)

    def test_auxiliary_join_never_uses_future_date(self) -> None:
        primary = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-02", "2025-01-05"]),
                "rub_per_unit": [1.0, 1.1],
            }
        )
        auxiliary = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-04"]),
                "rub_per_unit": [100.0, 110.0],
                "same_rate_as_previous": [False, False],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for currency in ("usd", "eur"):
                auxiliary.to_csv(path / f"rub_{currency}_observations.csv", index=False)
            merged = add_auxiliary_features(primary, path)
        self.assertTrue((merged["usd_source_date"] <= merged["date"]).all())
        self.assertTrue((merged["eur_source_date"] <= merged["date"]).all())

    def test_implied_usd_formula_and_backward_asof_are_exact(self) -> None:
        primary = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-02", "2025-01-05"]),
                "rub_per_unit": [10.0, 12.0],
            }
        )
        usd = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-04", "2025-01-06"]),
                "rub_per_unit": [100.0, 120.0, 1.0],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            usd.to_csv(path / "rub_usd_observations.csv", index=False)
            merged = add_implied_usd_features(primary, path)
        self.assertEqual(merged["implied_usd_per_lcy"].tolist(), [0.1, 0.1])
        self.assertEqual(
            merged["usd_source_date"].tolist(),
            [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-04")],
        )
        self.assertTrue((merged["usd_source_date"] <= merged["date"]).all())

    def test_implied_features_do_not_change_existing_feature_values(self) -> None:
        dates = pd.date_range("2025-01-01", periods=80, freq="D")
        primary = pd.DataFrame(
            {
                "date": dates,
                "rub_per_unit": [10.0 + index / 100 for index in range(80)],
                "same_rate_as_previous": False,
            }
        )
        usd = pd.DataFrame(
            {
                "date": dates,
                "rub_per_unit": [100.0 + index / 10 for index in range(80)],
            }
        )
        existing = add_features(primary)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            usd.to_csv(path / "rub_usd_observations.csv", index=False)
            augmented = add_implied_usd_features(existing, path)
        pd.testing.assert_frame_equal(augmented[existing.columns], existing)

    def test_walk_forward_purges_future_label_window(self) -> None:
        frame = pd.DataFrame({"date": pd.date_range("2019-01-01", "2023-12-31", freq="D")})
        train, validation, test = split_frame(frame, test_year=2023, horizon=20)
        self.assertLessEqual(train["date"].max() + pd.Timedelta(days=20), pd.Timestamp("2021-12-31"))
        self.assertLessEqual(validation["date"].max() + pd.Timedelta(days=20), pd.Timestamp("2022-12-31"))
        self.assertEqual(test["date"].min(), pd.Timestamp("2023-01-01"))


if __name__ == "__main__":
    unittest.main()
