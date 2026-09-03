"""Walk-forward backtest for product-level FX notification quality.

The model predicts message_hit: whether waiting through the selected horizon
would have produced a rate more than epsilon better than today's rate.
Thresholds are selected on the previous validation year only. Final metrics are
calculated after the notification cooldown and compared with random schedules
of the same size drawn from the same eligible dates.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_CURRENCIES = ("TJS", "UZS", "KGS", "AMD", "KZT")
DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
FEATURE_COLUMNS = (
    "return_1",
    "return_3",
    "return_5",
    "return_10",
    "return_20",
    "distance_to_min_5",
    "distance_to_min_10",
    "distance_to_min_20",
    "distance_to_min_60",
    "distance_to_mean_5",
    "distance_to_mean_10",
    "distance_to_mean_20",
    "distance_to_mean_60",
    "range_position_5",
    "range_position_10",
    "range_position_20",
    "range_position_60",
    "volatility_5",
    "volatility_10",
    "volatility_20",
    "down_streak",
    "days_since_previous",
    "month_sin",
    "month_cos",
    "weekday_sin",
    "weekday_cos",
)


def parse_int_list(raw: str) -> tuple[int, ...]:
    values = tuple(dict.fromkeys(int(value.strip()) for value in raw.split(",") if value.strip()))
    if not values:
        raise ValueError("Expected at least one integer")
    return values


def parse_str_list(raw: str) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(value.strip().upper() for value in raw.split(",") if value.strip()))
    if not values:
        raise ValueError("Expected at least one currency")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/backtest"))
    parser.add_argument("--currencies", default=",".join(DEFAULT_CURRENCIES))
    parser.add_argument("--horizons", default=",".join(map(str, DEFAULT_HORIZONS)))
    parser.add_argument("--epsilon-bps", type=int, default=50)
    parser.add_argument("--first-test-year", type=int, default=2022)
    parser.add_argument("--cooldown-days", type=int, default=4)
    parser.add_argument("--min-validation-signals", type=int, default=12)
    parser.add_argument("--max-signals-per-week", type=float, default=2.0)
    parser.add_argument("--random-repeats", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


@dataclass
class LogisticModel:
    l2: float = 1.0
    max_iter: int = 100
    tolerance: float = 1e-7

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "LogisticModel":
        raw = frame.to_numpy(dtype=float)
        self.medians = np.nanmedian(raw, axis=0)
        self.medians = np.where(np.isnan(self.medians), 0.0, self.medians)
        filled = np.where(np.isnan(raw), self.medians, raw)
        self.means = filled.mean(axis=0)
        self.scales = filled.std(axis=0)
        self.scales = np.where(self.scales < 1e-12, 1.0, self.scales)
        standardized = (filled - self.means) / self.scales
        design = np.column_stack([np.ones(len(standardized)), standardized])
        y = target.to_numpy(dtype=float)
        beta = np.zeros(design.shape[1], dtype=float)
        penalty = np.eye(design.shape[1])
        penalty[0, 0] = 0.0

        for _ in range(self.max_iter):
            logits = np.clip(design @ beta, -35, 35)
            probability = 1.0 / (1.0 + np.exp(-logits))
            weights = np.clip(probability * (1.0 - probability), 1e-8, None)
            gradient = design.T @ (y - probability) - self.l2 * (penalty @ beta)
            hessian = design.T @ (weights[:, None] * design) + self.l2 * penalty
            step = np.linalg.solve(hessian, gradient)
            beta += step
            if float(np.max(np.abs(step))) < self.tolerance:
                break
        self.beta = beta
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        raw = frame.to_numpy(dtype=float)
        filled = np.where(np.isnan(raw), self.medians, raw)
        standardized = (filled - self.means) / self.scales
        design = np.column_stack([np.ones(len(standardized)), standardized])
        logits = np.clip(design @ self.beta, -35, 35)
        return 1.0 / (1.0 + np.exp(-logits))


def add_features(observations: pd.DataFrame) -> pd.DataFrame:
    frame = observations.sort_values("date").copy()
    rate = frame["rub_per_unit"].astype(float)
    for period in (1, 3, 5, 10, 20):
        frame[f"return_{period}"] = rate.pct_change(periods=period, fill_method=None)
    for window in (5, 10, 20, 60):
        rolling = rate.rolling(window, min_periods=window)
        rolling_min = rolling.min()
        rolling_max = rolling.max()
        rolling_mean = rolling.mean()
        frame[f"distance_to_min_{window}"] = rate / rolling_min - 1.0
        frame[f"distance_to_mean_{window}"] = rate / rolling_mean - 1.0
        spread = (rolling_max - rolling_min).replace(0, np.nan)
        frame[f"range_position_{window}"] = (rate - rolling_min) / spread
    for window in (5, 10, 20):
        frame[f"volatility_{window}"] = frame["return_1"].rolling(
            window, min_periods=window
        ).std()
    down = rate.diff().lt(0).to_numpy()
    streak = np.zeros(len(frame), dtype=int)
    for index in range(1, len(frame)):
        streak[index] = streak[index - 1] + 1 if down[index] else 0
    frame["down_streak"] = streak
    frame["month_sin"] = np.sin(2 * np.pi * frame["date"].dt.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * frame["date"].dt.month / 12)
    frame["weekday_sin"] = np.sin(2 * np.pi * frame["date"].dt.dayofweek / 7)
    frame["weekday_cos"] = np.cos(2 * np.pi * frame["date"].dt.dayofweek / 7)
    repeated = frame["same_rate_as_previous"].astype(str).str.lower().eq("true")
    frame["eligible_for_signal"] = ~repeated
    return frame


def load_model_frame(data_dir: Path, currency: str, horizon: int, epsilon_bps: int) -> pd.DataFrame:
    prefix = f"rub_{currency.lower()}"
    observations = pd.read_csv(data_dir / f"{prefix}_observations.csv", parse_dates=["date"])
    labels = pd.read_csv(
        data_dir / f"{prefix}_labels_h{horizon}_e{epsilon_bps}bp.csv",
        parse_dates=["date"],
    )
    features = add_features(observations)
    label_columns = [
        "date",
        "corridor",
        "has_full_window",
        "message_hit",
        "future_regret_bps",
        "moment_advantage_bps",
    ]
    frame = features.merge(labels[label_columns], on=["date", "corridor"], validate="one_to_one")
    complete = frame["has_full_window"].astype(str).str.lower().eq("true")
    frame = frame.loc[complete & frame["eligible_for_signal"]].copy()
    frame["message_hit"] = frame["message_hit"].astype(int)
    return frame


def apply_cooldown(frame: pd.DataFrame, threshold: float, cooldown_days: int) -> pd.DataFrame:
    candidates = frame.loc[frame["score"] >= threshold].sort_values("date")
    selected: list[int] = []
    last_sent: pd.Timestamp | None = None
    for index, row in candidates.iterrows():
        if last_sent is None or row["date"] > last_sent + timedelta(days=cooldown_days):
            selected.append(index)
            last_sent = row["date"]
    return candidates.loc[selected].copy()


def weeks_in(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 1.0
    return max((frame["date"].max() - frame["date"].min()).days / 7.0, 1.0)


def wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    rate = successes / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    adjustment = z * math.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return (centre - adjustment) / denominator


def roc_auc(target: pd.Series, scores: np.ndarray) -> float:
    y = target.to_numpy(dtype=int)
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def threshold_candidates(scores: np.ndarray) -> np.ndarray:
    # Eighty-one operating points are enough to expose the quality/frequency
    # frontier while keeping a full 5x5 walk-forward run practical.
    return np.unique(np.quantile(scores, np.linspace(0.0, 1.0, 81)))


def select_threshold(
    validation: pd.DataFrame,
    *,
    cooldown_days: int,
    min_signals: int,
    max_signals_per_week: float,
) -> tuple[float, list[dict[str, float]]]:
    baseline = float(validation["message_hit"].mean())
    rows: list[dict[str, float]] = []
    for threshold in threshold_candidates(validation["score"].to_numpy()):
        signals = apply_cooldown(validation, float(threshold), cooldown_days)
        count = len(signals)
        if count == 0:
            continue
        hit_rate = float(signals["message_hit"].mean())
        frequency = count / weeks_in(validation)
        rows.append(
            {
                "threshold": float(threshold),
                "signals": count,
                "signals_per_week": frequency,
                "signal_hit_rate": hit_rate,
                "random_hit_rate": baseline,
                "lift": hit_rate / baseline if baseline else float("nan"),
                "hit_rate_wilson_lower": wilson_lower(int(signals["message_hit"].sum()), count),
            }
        )
    eligible = [
        row
        for row in rows
        if row["signals"] >= min_signals and row["signals_per_week"] <= max_signals_per_week
    ]
    if not eligible:
        eligible = [row for row in rows if row["signals"] >= min(5, min_signals)] or rows
    selected = max(
        eligible,
        key=lambda row: (row["hit_rate_wilson_lower"], row["lift"], row["signals"]),
    )
    return float(selected["threshold"]), rows


def random_schedule_indices(
    dates: pd.Series,
    count: int,
    cooldown_days: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if count <= 0:
        return np.array([], dtype=int)
    next_index, max_from = random_schedule_state(dates, cooldown_days)
    return sample_random_schedule(next_index, max_from, count, cooldown_days, rng)


def random_schedule_state(
    dates: pd.Series, cooldown_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Precompute cooldown feasibility once for repeated random schedules."""
    date_values = dates.reset_index(drop=True).to_numpy(dtype="datetime64[D]").astype(np.int64)
    size = len(date_values)
    next_index = np.searchsorted(date_values, date_values + cooldown_days, side="right")
    max_from = np.zeros(size + 1, dtype=int)
    for index in range(size - 1, -1, -1):
        max_from[index] = max(max_from[index + 1], 1 + max_from[next_index[index]])
    return next_index, max_from


def sample_random_schedule(
    next_index: np.ndarray,
    max_from: np.ndarray,
    count: int,
    cooldown_days: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if max_from[0] < count:
        raise ValueError(
            f"Cannot draw {count} dates with cooldown={cooldown_days}; maximum={max_from[0]}"
        )

    selected: list[int] = []
    index = 0
    remaining = count
    while remaining:
        can_take = 1 + max_from[next_index[index]] >= remaining
        can_skip = max_from[index + 1] >= remaining
        take = can_take and (not can_skip or bool(rng.integers(0, 2)))
        if take:
            selected.append(index)
            remaining -= 1
            index = int(next_index[index])
        else:
            index += 1
    return np.array(selected, dtype=int)


def random_baseline(
    frame: pd.DataFrame,
    *,
    signal_count: int,
    cooldown_days: int,
    repeats: int,
    seed: int,
) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    outcomes = frame["message_hit"].reset_index(drop=True)
    next_index, max_from = random_schedule_state(frame["date"], cooldown_days)
    rates: list[float] = []
    for _ in range(repeats):
        indices = sample_random_schedule(
            next_index, max_from, signal_count, cooldown_days, rng
        )
        if len(indices):
            rates.append(float(outcomes.iloc[indices].mean()))
    if not rates:
        return float("nan"), float("nan"), float("nan")
    values = np.array(rates)
    return (
        float(values.mean()),
        float(np.quantile(values, 0.025)),
        float(np.quantile(values, 0.975)),
    )


def mean_ci(values: pd.Series) -> tuple[float, float, float]:
    clean = values.dropna().to_numpy(dtype=float)
    if len(clean) == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(clean.mean())
    if len(clean) == 1:
        return mean, mean, mean
    margin = 1.96 * float(clean.std(ddof=1)) / math.sqrt(len(clean))
    return mean, mean - margin, mean + margin


def backtest_fold(
    frame: pd.DataFrame,
    *,
    corridor: str,
    horizon: int,
    test_year: int,
    cooldown_days: int,
    min_validation_signals: int,
    max_signals_per_week: float,
    random_repeats: int,
    seed: int,
) -> tuple[dict[str, object], list[dict[str, object]], pd.DataFrame] | None:
    validation_start = pd.Timestamp(test_year - 1, 1, 1)
    test_start = pd.Timestamp(test_year, 1, 1)
    next_test_start = pd.Timestamp(test_year + 1, 1, 1)
    gap = pd.Timedelta(days=horizon)
    train = frame.loc[frame["date"] < validation_start - gap].copy()
    validation = frame.loc[
        (frame["date"] >= validation_start) & (frame["date"] < test_start - gap)
    ].copy()
    test = frame.loc[(frame["date"] >= test_start) & (frame["date"] < next_test_start)].copy()
    if len(train) < 500 or len(validation) < 100 or len(test) < 40:
        return None

    model = LogisticModel().fit(train[list(FEATURE_COLUMNS)], train["message_hit"])
    validation["score"] = model.predict_proba(validation[list(FEATURE_COLUMNS)])
    test["score"] = model.predict_proba(test[list(FEATURE_COLUMNS)])
    threshold, tradeoffs = select_threshold(
        validation,
        cooldown_days=cooldown_days,
        min_signals=min_validation_signals,
        max_signals_per_week=max_signals_per_week,
    )
    signals = apply_cooldown(test, threshold, cooldown_days)
    random_mean, random_low, random_high = random_baseline(
        test,
        signal_count=len(signals),
        cooldown_days=cooldown_days,
        repeats=random_repeats,
        seed=seed,
    )
    signal_hit_rate = float(signals["message_hit"].mean()) if len(signals) else float("nan")
    lift = signal_hit_rate / random_mean if random_mean and len(signals) else float("nan")
    advantage_mean, advantage_low, advantage_high = mean_ci(signals["moment_advantage_bps"])
    regret_mean, _, _ = mean_ci(signals["future_regret_bps"])
    metrics: dict[str, object] = {
        "corridor": corridor,
        "horizon_days": horizon,
        "test_year": test_year,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows": len(test),
        "threshold": threshold,
        "validation_auc": roc_auc(validation["message_hit"], validation["score"].to_numpy()),
        "test_auc": roc_auc(test["message_hit"], test["score"].to_numpy()),
        "signals": len(signals),
        "signals_per_week": len(signals) / weeks_in(test),
        "signal_hit_rate": signal_hit_rate,
        "random_hit_rate": random_mean,
        "random_hit_rate_ci_low": random_low,
        "random_hit_rate_ci_high": random_high,
        "lift": lift,
        "future_regret_bps_mean": regret_mean,
        "moment_advantage_bps_mean": advantage_mean,
        "moment_advantage_bps_ci_low": advantage_low,
        "moment_advantage_bps_ci_high": advantage_high,
    }
    tradeoff_rows = [
        {"corridor": corridor, "horizon_days": horizon, "test_year": test_year, **row}
        for row in tradeoffs
    ]
    signals = signals.copy()
    signals["threshold"] = threshold
    signals["horizon_days"] = horizon
    signals["test_year"] = test_year
    signals["signal_strength"] = np.where(
        signals["score"] >= threshold + 0.15,
        "strong",
        np.where(signals["score"] >= threshold + 0.05, "medium", "base"),
    )
    signals["indicator"] = "logistic_message_hit"
    signals["direction"] = "RUB_to_recipient_currency"
    signals["signal_speed"] = "fast_baseline"
    signals["recommended_scenario"] = "positive_push_now"
    signals["reason_code"] = "score_above_threshold_outside_cooldown"
    return metrics, tradeoff_rows, signals


def summarize(folds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (corridor, horizon), group in folds.groupby(["corridor", "horizon_days"]):
        valid = group.dropna(subset=["lift"])
        signal_total = int(valid["signals"].sum())
        weighted_hit = (
            float((valid["signal_hit_rate"] * valid["signals"]).sum() / signal_total)
            if signal_total
            else float("nan")
        )
        weighted_random = (
            float((valid["random_hit_rate"] * valid["signals"]).sum() / signal_total)
            if signal_total
            else float("nan")
        )
        total_weeks = float(
            (valid["signals"] / valid["signals_per_week"].replace(0, np.nan)).sum()
        )
        rows.append(
            {
                "corridor": corridor,
                "horizon_days": horizon,
                "folds": len(valid),
                "signals": signal_total,
                "signals_per_week": signal_total / total_weeks if total_weeks else float("nan"),
                "signal_hit_rate": weighted_hit,
                "random_hit_rate": weighted_random,
                "lift": weighted_hit / weighted_random if weighted_random else float("nan"),
                "median_fold_lift": float(valid["lift"].median()),
                "min_fold_lift": float(valid["lift"].min()),
                "folds_lift_ge_1_3": int((valid["lift"] >= 1.3).sum()),
                "mean_test_auc": float(valid["test_auc"].mean()),
                "moment_advantage_bps_mean": float(
                    np.average(valid["moment_advantage_bps_mean"], weights=valid["signals"])
                )
                if signal_total
                else float("nan"),
                "stable_lift_ge_1_3": bool(len(valid) >= 3 and (valid["lift"] >= 1.3).all()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["stable_lift_ge_1_3", "median_fold_lift", "signals"],
        ascending=[False, False, False],
    )


def main() -> None:
    args = parse_args()
    currencies = parse_str_list(args.currencies)
    horizons = parse_int_list(args.horizons)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fold_rows: list[dict[str, object]] = []
    tradeoff_rows: list[dict[str, object]] = []
    signal_frames: list[pd.DataFrame] = []

    for currency_index, currency in enumerate(currencies):
        for horizon_index, horizon in enumerate(horizons):
            frame = load_model_frame(args.data_dir, currency, horizon, args.epsilon_bps)
            corridor = f"RUB_{currency}"
            last_year = int(frame["date"].dt.year.max())
            for test_year in range(args.first_test_year, last_year + 1):
                result = backtest_fold(
                    frame,
                    corridor=corridor,
                    horizon=horizon,
                    test_year=test_year,
                    cooldown_days=args.cooldown_days,
                    min_validation_signals=args.min_validation_signals,
                    max_signals_per_week=args.max_signals_per_week,
                    random_repeats=args.random_repeats,
                    seed=args.seed + currency_index * 1000 + horizon_index * 100 + test_year,
                )
                if result is None:
                    continue
                metrics, tradeoffs, signals = result
                fold_rows.append(metrics)
                tradeoff_rows.extend(tradeoffs)
                signal_frames.append(signals)
                print(
                    f"{corridor} h={horizon} test={test_year}: "
                    f"lift={metrics['lift']:.3f}, hit={metrics['signal_hit_rate']:.3f}, "
                    f"random={metrics['random_hit_rate']:.3f}, signals={metrics['signals']}",
                    flush=True,
                )

    folds = pd.DataFrame(fold_rows)
    if folds.empty:
        raise RuntimeError("No valid walk-forward folds were produced")
    summary = summarize(folds)
    tradeoffs = pd.DataFrame(tradeoff_rows)
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signal_columns = [
        "date",
        "corridor",
        "rub_per_unit",
        "horizon_days",
        "test_year",
        "score",
        "threshold",
        "message_hit",
        "future_regret_bps",
        "moment_advantage_bps",
        "indicator",
        "direction",
        "signal_strength",
        "signal_speed",
        "recommended_scenario",
        "reason_code",
    ]
    folds.to_csv(args.output_dir / "walk_forward_folds.csv", index=False)
    summary.to_csv(args.output_dir / "summary_by_corridor_horizon.csv", index=False)
    tradeoffs.to_csv(args.output_dir / "validation_threshold_tradeoffs.csv", index=False)
    signals[signal_columns].to_csv(args.output_dir / "signals.csv", index=False)
    metadata = {
        "target": "message_hit",
        "horizons_days": list(horizons),
        "currencies": list(currencies),
        "epsilon_bps": args.epsilon_bps,
        "cooldown_days": args.cooldown_days,
        "eligibility": "CBR effective-date observations excluding repeated unchanged rates",
        "random_baseline": "same corridor/fold, same signal count, same cooldown",
        "threshold_selection": "maximum validation Wilson lower bound with minimum event count",
        "first_test_year": args.first_test_year,
        "random_repeats": args.random_repeats,
        "model": "L2 logistic regression implemented with NumPy IRLS",
    }
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nTop corridor/horizon combinations:")
    print(summary.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
