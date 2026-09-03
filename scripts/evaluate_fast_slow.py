"""Compare an early model signal with a two-update confirmation policy.

Fast sends on the first score above the validation-selected threshold. Slow
waits for a second consecutive eligible CBR update above that same threshold.
The confirmation may arrive at most ``confirmation_days`` calendar days later.
Positive waiting cost means the recipient currency became more expensive in
rubles between the early observation and confirmation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from run_backtest import (
    DEFAULT_CURRENCIES,
    DEFAULT_HORIZONS,
    FEATURE_COLUMNS,
    LogisticModel,
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
    parser.add_argument("--confirmation-days", type=int, default=3)
    parser.add_argument("--random-repeats", type=int, default=300)
    parser.add_argument("--seed", type=int, default=242)
    return parser.parse_args()


def slow_candidates(
    frame: pd.DataFrame, threshold: float, confirmation_days: int
) -> pd.DataFrame:
    """Return second consecutive qualifying updates and their waiting cost."""
    ordered = frame.sort_values("date").copy()
    ordered["previous_score"] = ordered["score"].shift(1)
    ordered["early_date"] = ordered["date"].shift(1)
    ordered["early_rate"] = ordered["rub_per_unit"].shift(1)
    ordered["wait_days"] = (ordered["date"] - ordered["early_date"]).dt.days
    confirmed = ordered.loc[
        (ordered["score"] >= threshold)
        & (ordered["previous_score"] >= threshold)
        & ordered["wait_days"].between(1, confirmation_days)
    ].copy()
    confirmed["waiting_cost_bps"] = (
        confirmed["rub_per_unit"] / confirmed["early_rate"] - 1.0
    ) * 10_000
    return confirmed


def apply_candidate_cooldown(candidates: pd.DataFrame, cooldown_days: int) -> pd.DataFrame:
    marked = candidates.copy()
    marked["score_for_policy"] = marked["score"]
    marked["score"] = 1.0
    selected = apply_cooldown(marked, 1.0, cooldown_days)
    selected["score"] = selected["score_for_policy"]
    return selected.drop(columns=["score_for_policy"])


def weighted_mean(group: pd.DataFrame, column: str) -> float:
    valid = group.loc[group[column].notna() & group["signals"].gt(0)]
    if valid.empty:
        return float("nan")
    return float(np.average(valid[column], weights=valid["signals"]))


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for currency_index, currency in enumerate(parse_str_list(args.currencies)):
        for horizon_index, horizon in enumerate(parse_int_list(args.horizons)):
            frame = load_model_frame(args.data_dir, currency, horizon, args.epsilon_bps)
            corridor = f"RUB_{currency}"
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

                model = LogisticModel().fit(train[list(FEATURE_COLUMNS)], train["message_hit"])
                validation["score"] = model.predict_proba(validation[list(FEATURE_COLUMNS)])
                test["score"] = model.predict_proba(test[list(FEATURE_COLUMNS)])
                threshold, _ = select_threshold(
                    validation,
                    cooldown_days=args.cooldown_days,
                    min_signals=12,
                    max_signals_per_week=2.0,
                )
                policies = {
                    "fast": apply_cooldown(test, threshold, args.cooldown_days),
                    "slow": apply_candidate_cooldown(
                        slow_candidates(test, threshold, args.confirmation_days),
                        args.cooldown_days,
                    ),
                }
                for policy_index, (policy, signals) in enumerate(policies.items()):
                    random_mean, _, _ = random_baseline(
                        test,
                        signal_count=len(signals),
                        cooldown_days=args.cooldown_days,
                        repeats=args.random_repeats,
                        seed=(
                            args.seed
                            + currency_index * 10000
                            + horizon_index * 1000
                            + policy_index * 100
                            + test_year
                        ),
                    )
                    hit_rate = float(signals["message_hit"].mean()) if len(signals) else np.nan
                    rows.append(
                        {
                            "policy": policy,
                            "corridor": corridor,
                            "horizon_days": horizon,
                            "test_year": test_year,
                            "threshold": threshold,
                            "signals": len(signals),
                            "signals_per_week": len(signals) / weeks_in(test),
                            "signal_hit_rate": hit_rate,
                            "random_hit_rate": random_mean,
                            "lift": hit_rate / random_mean if random_mean and len(signals) else np.nan,
                            "wait_days_mean": (
                                float(signals["wait_days"].mean()) if policy == "slow" and len(signals) else np.nan
                            ),
                            "waiting_cost_bps_mean": (
                                float(signals["waiting_cost_bps"].mean())
                                if policy == "slow" and len(signals)
                                else np.nan
                            ),
                            "waiting_cost_bps_median": (
                                float(signals["waiting_cost_bps"].median())
                                if policy == "slow" and len(signals)
                                else np.nan
                            ),
                        }
                    )

    folds = pd.DataFrame(rows)
    summary_rows: list[dict[str, object]] = []
    for (policy, corridor, horizon), group in folds.groupby(
        ["policy", "corridor", "horizon_days"]
    ):
        valid = group.dropna(subset=["lift"])
        total = int(valid["signals"].sum())
        hit = weighted_mean(valid, "signal_hit_rate")
        random = weighted_mean(valid, "random_hit_rate")
        summary_rows.append(
            {
                "policy": policy,
                "corridor": corridor,
                "horizon_days": horizon,
                "folds": len(valid),
                "signals": total,
                "signals_per_week": float(valid["signals"].sum() / sum(valid["signals"] / valid["signals_per_week"])),
                "signal_hit_rate": hit,
                "random_hit_rate": random,
                "lift": hit / random if random else np.nan,
                "median_fold_lift": float(valid["lift"].median()),
                "min_fold_lift": float(valid["lift"].min()),
                "folds_lift_ge_1_3": int((valid["lift"] >= 1.3).sum()),
                "wait_days_mean": weighted_mean(valid, "wait_days_mean"),
                "waiting_cost_bps_mean": weighted_mean(valid, "waiting_cost_bps_mean"),
                "waiting_cost_bps_median": weighted_mean(valid, "waiting_cost_bps_median"),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values(
        ["corridor", "horizon_days", "policy"]
    )
    folds.to_csv(args.output_dir / "fast_slow_folds.csv", index=False)
    summary.to_csv(args.output_dir / "fast_slow_summary.csv", index=False)
    showcase = summary.loc[
        summary["corridor"].eq("RUB_TJS") & summary["horizon_days"].eq(3)
    ]
    print(showcase.to_string(index=False))


if __name__ == "__main__":
    main()
