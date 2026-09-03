"""Walk-forward evaluation of the case's required simple indicator hypotheses."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from run_backtest import (
    DEFAULT_CURRENCIES,
    DEFAULT_HORIZONS,
    apply_cooldown,
    load_model_frame,
    parse_int_list,
    parse_str_list,
    random_baseline,
    select_threshold,
    weeks_in,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/backtest"))
    parser.add_argument("--currencies", default=",".join(DEFAULT_CURRENCIES))
    parser.add_argument("--horizons", default=",".join(map(str, DEFAULT_HORIZONS)))
    parser.add_argument("--epsilon-bps", type=int, default=50)
    parser.add_argument("--first-test-year", type=int, default=2022)
    parser.add_argument("--cooldown-days", type=int, default=4)
    parser.add_argument("--random-repeats", type=int, default=300)
    parser.add_argument("--seed", type=int, default=142)
    return parser.parse_args()


def score_indicator(
    name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    if name == "momentum":
        return -validation["return_3"].to_numpy(), -test["return_3"].to_numpy()
    if name == "level":
        return -validation["distance_to_min_20"].to_numpy(), -test["distance_to_min_20"].to_numpy()
    if name == "reversal":
        validation_score = validation["return_1"] - validation["distance_to_min_20"]
        test_score = test["return_1"] - test["distance_to_min_20"]
        return validation_score.to_numpy(), test_score.to_numpy()
    if name == "seasonality":
        by_month = train.groupby(train["date"].dt.month)["message_hit"].mean()
        fallback = float(train["message_hit"].mean())
        validation_score = validation["date"].dt.month.map(by_month).fillna(fallback)
        test_score = test["date"].dt.month.map(by_month).fillna(fallback)
        return validation_score.to_numpy(), test_score.to_numpy()
    raise ValueError(name)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    indicators = ("momentum", "level", "reversal", "seasonality")
    for currency_index, currency in enumerate(parse_str_list(args.currencies)):
        for horizon_index, horizon in enumerate(parse_int_list(args.horizons)):
            frame = load_model_frame(args.data_dir, currency, horizon, args.epsilon_bps)
            for test_year in range(args.first_test_year, int(frame["date"].dt.year.max()) + 1):
                validation_start = pd.Timestamp(test_year - 1, 1, 1)
                test_start = pd.Timestamp(test_year, 1, 1)
                next_test_start = pd.Timestamp(test_year + 1, 1, 1)
                gap = pd.Timedelta(days=horizon)
                train = frame.loc[frame["date"] < validation_start - gap].copy()
                validation = frame.loc[
                    (frame["date"] >= validation_start) & (frame["date"] < test_start - gap)
                ].copy()
                test = frame.loc[
                    (frame["date"] >= test_start) & (frame["date"] < next_test_start)
                ].copy()
                if len(train) < 500 or len(validation) < 100 or len(test) < 40:
                    continue
                for indicator_index, indicator in enumerate(indicators):
                    validation_scores, test_scores = score_indicator(
                        indicator, train, validation, test
                    )
                    validation["score"] = np.nan_to_num(validation_scores, nan=-1e9)
                    test["score"] = np.nan_to_num(test_scores, nan=-1e9)
                    threshold, _ = select_threshold(
                        validation,
                        cooldown_days=args.cooldown_days,
                        min_signals=12,
                        max_signals_per_week=2.0,
                    )
                    signals = apply_cooldown(test, threshold, args.cooldown_days)
                    random_mean, _, _ = random_baseline(
                        test,
                        signal_count=len(signals),
                        cooldown_days=args.cooldown_days,
                        repeats=args.random_repeats,
                        seed=(
                            args.seed
                            + currency_index * 10000
                            + horizon_index * 1000
                            + indicator_index * 100
                            + test_year
                        ),
                    )
                    hit_rate = float(signals["message_hit"].mean()) if len(signals) else np.nan
                    rows.append(
                        {
                            "indicator": indicator,
                            "corridor": f"RUB_{currency}",
                            "horizon_days": horizon,
                            "test_year": test_year,
                            "threshold": threshold,
                            "signals": len(signals),
                            "signals_per_week": len(signals) / weeks_in(test),
                            "signal_hit_rate": hit_rate,
                            "random_hit_rate": random_mean,
                            "lift": hit_rate / random_mean if random_mean and len(signals) else np.nan,
                        }
                    )

    folds = pd.DataFrame(rows)
    summary_rows: list[dict[str, object]] = []
    for (indicator, corridor, horizon), group in folds.groupby(
        ["indicator", "corridor", "horizon_days"]
    ):
        valid = group.dropna(subset=["lift"])
        total = int(valid["signals"].sum())
        hit = float((valid["signal_hit_rate"] * valid["signals"]).sum() / total) if total else np.nan
        random = float((valid["random_hit_rate"] * valid["signals"]).sum() / total) if total else np.nan
        summary_rows.append(
            {
                "indicator": indicator,
                "corridor": corridor,
                "horizon_days": horizon,
                "folds": len(valid),
                "signals": total,
                "signal_hit_rate": hit,
                "random_hit_rate": random,
                "lift": hit / random if random else np.nan,
                "median_fold_lift": float(valid["lift"].median()),
                "min_fold_lift": float(valid["lift"].min()),
                "folds_lift_ge_1_3": int((valid["lift"] >= 1.3).sum()),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["median_fold_lift", "signals"], ascending=[False, False]
    )
    folds.to_csv(args.output_dir / "indicator_folds.csv", index=False)
    summary.to_csv(args.output_dir / "indicator_summary.csv", index=False)
    print(summary.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
