"""Synchronized calendar moving-block bootstrap for paired OOT decisions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import require_columns


def moving_block_date_weights(
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    block_days: int,
    rng: np.random.Generator,
) -> pd.Series:
    calendar = pd.date_range(start, end_exclusive - pd.Timedelta(days=1), freq="D")
    size = len(calendar)
    if size == 0:
        return pd.Series(dtype=int)
    length = min(block_days, size)
    maximum_start = size - length
    sampled: list[pd.Timestamp] = []
    while len(sampled) < size:
        offset = int(rng.integers(0, maximum_start + 1))
        sampled.extend(calendar[offset : offset + length].tolist())
    sampled = sampled[:size]
    return pd.Series(sampled).value_counts().reindex(calendar, fill_value=0).astype(int)


def synchronized_bootstrap_weights(
    exposures: pd.DataFrame,
    *,
    block_days: int,
    replicates: int,
    seed: int,
) -> list[pd.DataFrame]:
    require_columns(
        exposures,
        ["outer_fold", "exposure_start", "exposure_end_exclusive"],
        "bootstrap exposures",
    )
    unique = exposures.drop_duplicates("outer_fold").sort_values("outer_fold")
    outputs: list[pd.DataFrame] = []
    for replicate in range(replicates):
        rng = np.random.default_rng(seed + replicate)
        pieces: list[pd.DataFrame] = []
        for row in unique.itertuples(index=False):
            weights = moving_block_date_weights(
                pd.Timestamp(row.exposure_start),
                pd.Timestamp(row.exposure_end_exclusive),
                block_days,
                rng,
            )
            pieces.append(
                pd.DataFrame(
                    {
                        "outer_fold": row.outer_fold,
                        "date": weights.index,
                        "bootstrap_weight": weights.to_numpy(),
                    }
                )
            )
        result = pd.concat(pieces, ignore_index=True)
        result["replicate"] = replicate
        outputs.append(result)
    return outputs


def _weighted_policy_metrics(frame: pd.DataFrame, weight: pd.Series) -> tuple[float, float]:
    selected = frame["selected_signal"].astype(bool)
    signal_weights = weight.where(selected, 0.0)
    total = float(signal_weights.sum())
    if total == 0:
        return np.nan, np.nan
    hit = float((frame["message_hit"] * signal_weights).sum() / total)
    regret = float((frame["future_regret_bps"] * signal_weights).sum() / total)
    return hit, regret


def _weighted_quantile(values: pd.Series, weights: pd.Series, quantile: float) -> float:
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return np.nan
    ordered = pd.DataFrame(
        {"value": values.loc[valid].astype(float), "weight": weights.loc[valid].astype(float)}
    ).sort_values("value", kind="stable")
    cutoff = quantile * float(ordered["weight"].sum())
    return float(ordered.loc[ordered["weight"].cumsum().ge(cutoff), "value"].iloc[0])


def paired_policy_bootstrap(
    left: pd.DataFrame,
    right: pd.DataFrame,
    exposures: pd.DataFrame,
    *,
    block_days: int = 28,
    replicates: int = 5000,
    seed: int = 42029,
) -> pd.DataFrame:
    keys = ["outer_fold", "date", "corridor"]
    required = [*keys, "selected_signal", "message_hit", "future_regret_bps"]
    require_columns(left, required, "left bootstrap decisions")
    require_columns(right, required, "right bootstrap decisions")
    left_keys = set(left[keys].itertuples(index=False, name=None))
    right_keys = set(right[keys].itertuples(index=False, name=None))
    if left_keys != right_keys:
        raise AssertionError("Paired models do not share identical OOT row keys")
    pair = left[required].merge(
        right[required],
        on=keys,
        suffixes=("_left", "_right"),
        validate="one_to_one",
    )
    if not pair["message_hit_left"].equals(pair["message_hit_right"]):
        raise AssertionError("Paired models have different labels on common OOT rows")
    rows: list[dict[str, float | int]] = []
    for weights in synchronized_bootstrap_weights(
        exposures, block_days=block_days, replicates=replicates, seed=seed
    ):
        sampled = pair.merge(weights, on=["outer_fold", "date"], validate="many_to_one")
        weight = sampled["bootstrap_weight"].astype(float)
        left_frame = sampled.rename(
            columns={
                "selected_signal_left": "selected_signal",
                "message_hit_left": "message_hit",
                "future_regret_bps_left": "future_regret_bps",
            }
        )
        right_frame = sampled.rename(
            columns={
                "selected_signal_right": "selected_signal",
                "message_hit_right": "message_hit",
                "future_regret_bps_right": "future_regret_bps",
            }
        )
        left_hit, left_regret = _weighted_policy_metrics(left_frame, weight)
        right_hit, right_regret = _weighted_policy_metrics(right_frame, weight)
        left_signals = float((weight * sampled["selected_signal_left"].astype(int)).sum())
        right_signals = float((weight * sampled["selected_signal_right"].astype(int)).sum())
        rows.append(
            {
                "replicate": int(weights["replicate"].iloc[0]),
                "left_hit_rate": left_hit,
                "right_hit_rate": right_hit,
                "delta_hit_rate": right_hit - left_hit,
                "left_mean_regret_bps": left_regret,
                "right_mean_regret_bps": right_regret,
                "delta_mean_regret_bps": right_regret - left_regret,
                "left_signals": left_signals,
                "right_signals": right_signals,
                "delta_signals": right_signals - left_signals,
            }
        )
    return pd.DataFrame(rows)


def summarize_paired_bootstrap(replicates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for metric in ("delta_hit_rate", "delta_mean_regret_bps", "delta_signals"):
        values = replicates[metric].dropna().to_numpy(dtype=float)
        rows.append(
            {
                "metric": metric,
                "estimate": float(values.mean()) if len(values) else np.nan,
                "ci_low": float(np.quantile(values, 0.025)) if len(values) else np.nan,
                "ci_high": float(np.quantile(values, 0.975)) if len(values) else np.nan,
                "bootstrap_se": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                "probability_delta_gt_zero": float((values > 0).mean()) if len(values) else np.nan,
                "replicates": len(values),
            }
        )
    return pd.DataFrame(rows)


def model_vs_random_bootstrap(
    decisions: pd.DataFrame,
    random_schedules: pd.DataFrame,
    exposures: pd.DataFrame,
    *,
    block_days: int = 28,
    replicates: int = 5000,
    seed: int = 42029,
) -> pd.DataFrame:
    """Bootstrap a frozen policy against its materialized paired random draws."""
    keys = ["outer_fold", "date", "corridor"]
    require_columns(
        decisions,
        [*keys, "selected_signal", "message_hit", "future_regret_bps"],
        "model decisions",
    )
    require_columns(
        random_schedules,
        [*keys, "draw_id", "message_hit", "future_regret_bps"],
        "random schedules",
    )
    draw_count = int(random_schedules["draw_id"].nunique())
    if draw_count <= 0:
        raise ValueError("random_schedules contains no draw IDs")
    random_expected = (
        random_schedules.groupby(keys, observed=True)
        .agg(
            random_inclusions=("draw_id", "size"),
            random_message_hit=("message_hit", "first"),
            random_future_regret_bps=("future_regret_bps", "first"),
        )
        .reset_index()
    )
    random_expected["random_inclusion_probability"] = (
        random_expected["random_inclusions"] / draw_count
    )
    base = decisions.merge(
        random_expected[
            [
                *keys,
                "random_inclusion_probability",
                "random_message_hit",
                "random_future_regret_bps",
            ]
        ],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    base["random_inclusion_probability"] = base[
        "random_inclusion_probability"
    ].fillna(0.0)
    base["random_message_hit"] = base["random_message_hit"].fillna(
        base["message_hit"]
    )
    rows: list[dict[str, float | int]] = []
    for weights in synchronized_bootstrap_weights(
        exposures, block_days=block_days, replicates=replicates, seed=seed
    ):
        model = base.merge(
            weights, on=["outer_fold", "date"], validate="many_to_one"
        )
        model_weight = model["bootstrap_weight"] * model["selected_signal"].astype(int)
        model_count = float(model_weight.sum())
        model_hit = (
            float((model["message_hit"] * model_weight).sum() / model_count)
            if model_count
            else np.nan
        )
        model_regret = (
            float((model["future_regret_bps"] * model_weight).sum() / model_count)
            if model_count
            else np.nan
        )
        model_false_weight = model_weight.where(model["message_hit"].eq(0), 0.0)
        model_false_count = float(model_false_weight.sum())
        model_false_regret = (
            float(
                (model["future_regret_bps"] * model_false_weight).sum()
                / model_false_count
            )
            if model_false_count
            else np.nan
        )
        model_tail_regret = _weighted_quantile(
            model["future_regret_bps"], model_weight, 0.90
        )
        random_weight = (
            model["bootstrap_weight"] * model["random_inclusion_probability"]
        )
        random_count = float(random_weight.sum())
        random_hit = (
            float((model["random_message_hit"] * random_weight).sum() / random_count)
            if random_count
            else np.nan
        )
        random_regret = (
            float(
                (model["random_future_regret_bps"] * random_weight).sum()
                / random_count
            )
            if random_count
            else np.nan
        )
        random_false_weight = random_weight.where(
            model["random_message_hit"].eq(0), 0.0
        )
        random_false_count = float(random_false_weight.sum())
        random_false_regret = (
            float(
                (model["random_future_regret_bps"] * random_false_weight).sum()
                / random_false_count
            )
            if random_false_count
            else np.nan
        )
        random_tail_regret = _weighted_quantile(
            model["random_future_regret_bps"], random_weight, 0.90
        )
        rows.append(
            {
                "replicate": int(weights["replicate"].iloc[0]),
                "model_hit_rate": model_hit,
                "matched_random_hit_rate": random_hit,
                "delta_hit_rate": model_hit - random_hit,
                "lift": model_hit / random_hit if random_hit else np.nan,
                "model_mean_regret_bps": model_regret,
                "matched_random_mean_regret_bps": random_regret,
                "delta_mean_regret_bps": model_regret - random_regret,
                "model_false_push_regret_bps": model_false_regret,
                "matched_random_false_push_regret_bps": random_false_regret,
                "delta_false_push_regret_bps": model_false_regret - random_false_regret,
                "model_p90_regret_bps": model_tail_regret,
                "matched_random_p90_regret_bps": random_tail_regret,
                "delta_p90_regret_bps": model_tail_regret - random_tail_regret,
            }
        )
    return pd.DataFrame(rows)


def summarize_model_vs_random_bootstrap(replicates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    for metric in (
        "model_hit_rate",
        "matched_random_hit_rate",
        "delta_hit_rate",
        "lift",
        "model_mean_regret_bps",
        "matched_random_mean_regret_bps",
        "delta_mean_regret_bps",
        "delta_false_push_regret_bps",
        "delta_p90_regret_bps",
    ):
        values = replicates[metric].dropna().to_numpy(dtype=float)
        rows.append(
            {
                "metric": metric,
                "estimate": float(values.mean()) if len(values) else np.nan,
                "ci_low": float(np.quantile(values, 0.025)) if len(values) else np.nan,
                "ci_high": float(np.quantile(values, 0.975)) if len(values) else np.nan,
                "bootstrap_se": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                "probability_delta_gt_zero": (
                    float((values > 0).mean()) if metric == "delta_hit_rate" and len(values) else np.nan
                ),
                "probability_lift_ge_1_3": (
                    float((values >= 1.3).mean()) if metric == "lift" and len(values) else np.nan
                ),
                "probability_improvement": (
                    float((values > 0).mean())
                    if metric == "delta_hit_rate" and len(values)
                    else (
                        float((values < 0).mean())
                        if metric.startswith("delta_") and "regret" in metric and len(values)
                        else np.nan
                    )
                ),
                "replicates": len(values),
            }
        )
    return pd.DataFrame(rows)
