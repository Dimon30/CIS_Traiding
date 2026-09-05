"""Canonical score, delivery, regret, and aggregation metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from .contracts import require_columns
from .policy import clustering_metrics, wilson_interval


def score_metrics(frame: pd.DataFrame, score_column: str = "calibrated_score") -> dict[str, float | int]:
    require_columns(frame, ["message_hit", score_column], "score metrics")
    valid = frame.loc[frame[score_column].notna()].copy()
    target = valid["message_hit"].astype(int)
    scores = valid[score_column].to_numpy(dtype=float)
    coverage = len(valid) / len(frame) if len(frame) else np.nan
    prevalence = float(target.mean()) if len(target) else np.nan
    result: dict[str, float | int] = {
        "eligible_rows": len(frame),
        "scored_rows": len(valid),
        "score_coverage": coverage,
        "target_rate": prevalence,
    }
    if len(target) and target.nunique() == 2:
        ap = float(average_precision_score(target, scores))
        result.update(
            {
                "roc_auc": float(roc_auc_score(target, scores)),
                "pr_auc": ap,
                "pr_auc_gain": ap - prevalence,
                "pr_auc_ratio": ap / prevalence if prevalence else np.nan,
                "brier": float(brier_score_loss(target, scores)),
                "log_loss": float(log_loss(target, np.clip(scores, 1e-9, 1 - 1e-9))),
            }
        )
    else:
        result.update({key: np.nan for key in ("roc_auc", "pr_auc", "pr_auc_gain", "pr_auc_ratio", "brier", "log_loss")})
    return result


def signal_metrics(
    decisions: pd.DataFrame,
    *,
    exposure_start: pd.Timestamp,
    exposure_end_exclusive: pd.Timestamp,
    random_hit_rate: float = np.nan,
    random_mcse: float = np.nan,
    cooldown_days: int = 4,
) -> dict[str, float | int]:
    require_columns(
        decisions,
        ["selected_signal", "candidate", "message_hit", "future_regret_bps", "date"],
        "signal metrics",
    )
    signals = decisions.loc[decisions["selected_signal"].astype(bool)].copy()
    count = len(signals)
    candidates = int(decisions["candidate"].astype(bool).sum())
    hits = int(signals["message_hit"].sum()) if count else 0
    false = count - hits
    exposure_days = max(1, int((exposure_end_exclusive - exposure_start).days))
    weeks = exposure_days / 7.0
    months = exposure_days / (365.2425 / 12.0)
    regrets = signals["future_regret_bps"].astype(float) if count else pd.Series(dtype=float)
    false_regrets = signals.loc[signals["message_hit"].eq(0), "future_regret_bps"].astype(float)
    low, high = wilson_interval(hits, count)
    gaps = clustering_metrics(
        signals,
        exposure_start=exposure_start,
        exposure_end_exclusive=exposure_end_exclusive,
    )
    exposure_months = pd.period_range(
        exposure_start.to_period("M"),
        (exposure_end_exclusive - pd.Timedelta(days=1)).to_period("M"),
        freq="M",
    )
    active_months = int(signals["date"].dt.to_period("M").nunique()) if count else 0
    if count > 1:
        cooldown_violations = int(
            signals.sort_values("date")["date"]
            .diff()
            .dt.days.dropna()
            .le(cooldown_days)
            .sum()
        )
    else:
        cooldown_violations = 0
    return {
        "evaluation_days": exposure_days,
        "evaluation_weeks": weeks,
        "candidates": candidates,
        "candidate_coverage": candidates / len(decisions) if len(decisions) else np.nan,
        "candidates_per_week": candidates / weeks,
        "signals": count,
        "signal_coverage": count / len(decisions) if len(decisions) else np.nan,
        "signal_active": count > 0,
        "signals_per_week": count / weeks,
        "signals_per_month": count / months,
        "suppressed_by_cooldown": candidates - count,
        "signal_hits": hits,
        "false_pushes": false,
        "signal_hit_rate": hits / count if count else np.nan,
        "hit_rate_ci_low": low,
        "hit_rate_ci_high": high,
        "false_push_rate": false / count if count else np.nan,
        "matched_random_hit_rate": random_hit_rate,
        "random_hit_rate": random_hit_rate,
        "matched_random_mcse": random_mcse,
        "delta_hit_rate": hits / count - random_hit_rate if count and np.isfinite(random_hit_rate) else np.nan,
        "lift": hits / count / random_hit_rate if count and random_hit_rate else np.nan,
        "mean_realized_regret_bps": float(regrets.mean()) if count else np.nan,
        "future_regret_bps_mean": float(regrets.mean()) if count else np.nan,
        "median_realized_regret_bps": float(regrets.median()) if count else np.nan,
        "p90_realized_regret_bps": float(regrets.quantile(0.90)) if count else np.nan,
        "p95_realized_regret_bps": float(regrets.quantile(0.95)) if count else np.nan,
        "max_realized_regret_bps": float(regrets.max()) if count else np.nan,
        "false_push_regret_bps_mean": float(false_regrets.mean()) if len(false_regrets) else np.nan,
        "false_push_regret_bps_p90": float(false_regrets.quantile(0.90)) if len(false_regrets) else np.nan,
        "cooldown_violations": cooldown_violations,
        "active_months": active_months,
        "inactive_months": len(exposure_months) - active_months,
        "active_month_share": active_months / len(exposure_months) if len(exposure_months) else np.nan,
        "moment_advantage_bps_mean": (
            float(signals["moment_advantage_bps"].mean())
            if count and "moment_advantage_bps" in signals
            else np.nan
        ),
        **gaps,
    }


def aggregate_signal_metrics(cells: pd.DataFrame) -> dict[str, float | int]:
    require_columns(
        cells,
        ["signals", "signal_hits", "matched_random_hit_rate", "evaluation_days"],
        "signal metric cells",
    )
    signals = int(cells["signals"].sum())
    hits = int(cells["signal_hits"].sum())
    expected_random_hits = float(
        (cells["matched_random_hit_rate"].fillna(0) * cells["signals"]).sum()
    )
    days = float(cells["evaluation_days"].sum())
    hit_rate = hits / signals if signals else np.nan
    random_rate = expected_random_hits / signals if signals else np.nan
    signal_weights = cells["signals"].astype(float)

    def weighted(column: str, weight_column: str = "signals") -> float:
        weights = cells[weight_column].astype(float) if weight_column in cells else signal_weights
        if column not in cells or not float(weights.sum()):
            return np.nan
        valid = cells[column].notna() & weights.gt(0)
        return (
            float(np.average(cells.loc[valid, column], weights=weights.loc[valid]))
            if valid.any()
            else np.nan
        )

    return {
        "total_signals": signals,
        "signal_hits": hits,
        "signal_hit_rate": hit_rate,
        "matched_random_hit_rate": random_rate,
        "delta_hit_rate": hit_rate - random_rate if signals else np.nan,
        "lift": hit_rate / random_rate if signals and random_rate else np.nan,
        "signals_per_week": signals / (days / 7.0) if days else np.nan,
        "signals_per_month": signals / (days / (365.2425 / 12.0)) if days else np.nan,
        "candidates": int(cells["candidates"].sum()) if "candidates" in cells else 0,
        "false_pushes": int(cells["false_pushes"].sum()) if "false_pushes" in cells else 0,
        "false_push_rate": (signals - hits) / signals if signals else np.nan,
        "mean_realized_regret_bps": weighted("mean_realized_regret_bps"),
        "false_push_regret_bps_mean": weighted("false_push_regret_bps_mean", "false_pushes"),
        "weighted_cell_p90_realized_regret_bps": weighted("p90_realized_regret_bps"),
        "moment_advantage_bps_mean": weighted("moment_advantage_bps_mean"),
        "suppressed_by_cooldown": (
            int(cells["suppressed_by_cooldown"].sum())
            if "suppressed_by_cooldown" in cells
            else 0
        ),
        "cooldown_violations": (
            int(cells["cooldown_violations"].sum())
            if "cooldown_violations" in cells
            else 0
        ),
        "active_months": int(cells["active_months"].sum()) if "active_months" in cells else 0,
        "inactive_months": int(cells["inactive_months"].sum()) if "inactive_months" in cells else 0,
        "active_cells": int(cells["signals"].gt(0).sum()),
        "inactive_cells": int(cells["signals"].eq(0).sum()),
        "active_cell_share": float(cells["signals"].gt(0).mean()) if len(cells) else np.nan,
    }
