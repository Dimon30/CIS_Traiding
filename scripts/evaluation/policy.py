"""Delivery-policy mechanics and frequency-indexed policy frontiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from .contracts import require_columns


@dataclass(frozen=True)
class SelectedPolicy:
    threshold: float | None
    status: str
    inactive_reason: str | None = None


def apply_cooldown(
    frame: pd.DataFrame,
    threshold: float,
    cooldown_days: int,
    *,
    score_column: str = "calibrated_score",
    last_sent: pd.Timestamp | None = None,
) -> pd.DataFrame:
    require_columns(frame, ["date", score_column], "policy frame")
    candidates = frame.loc[frame[score_column].ge(threshold)].sort_values(
        "date", kind="stable"
    )
    selected: list[object] = []
    for index, row in candidates.iterrows():
        date = pd.Timestamp(row["date"])
        if last_sent is None or date > last_sent + timedelta(days=cooldown_days):
            selected.append(index)
            last_sent = date
    return candidates.loc[selected].copy()


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return float("nan"), float("nan")
    rate = successes / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    adjustment = z * np.sqrt(
        (rate * (1.0 - rate) + z * z / (4.0 * total)) / total
    )
    return (centre - adjustment) / denominator, (centre + adjustment) / denominator


def threshold_candidates(scores: pd.Series | np.ndarray) -> np.ndarray:
    values = np.asarray(scores, dtype=float)
    values = np.unique(values[np.isfinite(values)])
    if values.size == 0:
        raise ValueError("Policy block contains no finite scores")
    above = np.nextafter(values.max(), np.inf)
    return np.concatenate(([above], values[::-1]))


def enumerate_policy_points(
    frame: pd.DataFrame,
    *,
    cooldown_days: int,
    exposure_weeks: float,
    score_column: str = "calibrated_score",
) -> pd.DataFrame:
    require_columns(frame, ["date", score_column, "message_hit"], "policy block")
    if exposure_weeks <= 0:
        raise ValueError("exposure_weeks must be positive")
    rows: list[dict[str, object]] = []
    for threshold in threshold_candidates(frame[score_column]):
        candidates = frame.loc[frame[score_column].ge(float(threshold))]
        signals = apply_cooldown(
            frame, float(threshold), cooldown_days, score_column=score_column
        )
        count = len(signals)
        successes = int(signals["message_hit"].sum()) if count else 0
        low, high = wilson_interval(successes, count)
        rows.append(
            {
                "threshold": float(threshold),
                "candidates": len(candidates),
                "signals": count,
                "signals_per_week": count / exposure_weeks,
                "signal_hits": successes,
                "signal_hit_rate": successes / count if count else np.nan,
                "hit_rate_wilson_lower": low,
                "hit_rate_wilson_upper": high,
                "suppressed_by_cooldown": len(candidates) - count,
            }
        )
    return pd.DataFrame(rows)


def map_thresholds_to_frequency_budgets(
    points: pd.DataFrame,
    budgets: Iterable[float],
) -> pd.DataFrame:
    require_columns(
        points,
        ["threshold", "signals", "signals_per_week"],
        "policy points",
    )
    rows: list[dict[str, object]] = []
    maximum = float(points["signals_per_week"].max())
    for index, budget in enumerate(budgets):
        feasible = points.loc[points["signals_per_week"].le(float(budget) + 1e-12)]
        if feasible.empty:
            rows.append(
                {
                    "frontier_point_id": f"budget_{index:02d}",
                    "requested_signals_per_week": float(budget),
                    "frontier_status": "infeasible",
                    "threshold": np.nan,
                    "policy_signals_per_week": np.nan,
                    "policy_signals": 0,
                    "maximum_achievable_signals_per_week": maximum,
                }
            )
            continue
        selected = feasible.sort_values(
            ["signals_per_week", "threshold"],
            ascending=[False, False],
            kind="stable",
        ).iloc[0]
        rows.append(
            {
                "frontier_point_id": f"budget_{index:02d}",
                "requested_signals_per_week": float(budget),
                "frontier_status": "active",
                "threshold": float(selected["threshold"]),
                "policy_signals_per_week": float(selected["signals_per_week"]),
                "policy_signals": int(selected["signals"]),
                "maximum_achievable_signals_per_week": maximum,
            }
        )
    return pd.DataFrame(rows)


def select_operating_policy(
    points: pd.DataFrame,
    *,
    minimum_signals: int,
    maximum_signals_per_week: float,
) -> SelectedPolicy:
    required = [
        "threshold",
        "signals",
        "signals_per_week",
        "hit_rate_wilson_lower",
        "matched_random_lift",
    ]
    require_columns(points, required, "policy points")
    feasible = points.loc[
        points["signals"].ge(minimum_signals)
        & points["signals_per_week"].le(maximum_signals_per_week + 1e-12)
    ].copy()
    if feasible.empty:
        return SelectedPolicy(None, "inactive", "no_feasible_policy")
    selected = feasible.sort_values(
        ["hit_rate_wilson_lower", "matched_random_lift", "signals", "threshold"],
        ascending=[False, False, False, False],
        kind="stable",
    ).iloc[0]
    return SelectedPolicy(float(selected["threshold"]), "active")


def apply_selected_policy(
    frame: pd.DataFrame,
    policy: SelectedPolicy,
    *,
    cooldown_days: int,
    score_column: str = "calibrated_score",
    last_sent: pd.Timestamp | None = None,
    gate_column: str | None = None,
) -> pd.DataFrame:
    result = frame.copy()
    result["candidate"] = False
    result["selected_signal"] = False
    result["policy_status"] = policy.status
    result["inactive_reason"] = policy.inactive_reason or ""
    result["threshold"] = policy.threshold if policy.threshold is not None else np.nan
    if policy.threshold is None:
        return result
    result["candidate"] = result[score_column].ge(policy.threshold)
    if gate_column is not None:
        result["candidate"] &= result[gate_column].fillna(False).astype(bool)
    signals = apply_cooldown(
        result.loc[result["candidate"]], policy.threshold, cooldown_days,
        score_column=score_column, last_sent=last_sent,
    )
    result.loc[signals.index, "selected_signal"] = True
    return result


def thin_to_common_count(
    frame: pd.DataFrame,
    count: int,
    *,
    signal_column: str = "selected_signal",
    score_column: str = "calibrated_score",
) -> pd.DataFrame:
    require_columns(frame, ["date", signal_column, score_column], "thinning frame")
    selected = frame.loc[frame[signal_column].astype(bool)].sort_values(
        [score_column, "date"], ascending=[False, True], kind="stable"
    )
    if count < 0 or count > len(selected):
        raise ValueError(f"Cannot thin {len(selected)} signals to count={count}")
    return selected.head(count).copy()


def clustering_metrics(
    signals: pd.DataFrame,
    *,
    exposure_start: pd.Timestamp | None = None,
    exposure_end_exclusive: pd.Timestamp | None = None,
) -> dict[str, float | int]:
    if signals.empty:
        return {
            "inter_signal_gap_days_median": np.nan,
            "inter_signal_gap_days_p10": np.nan,
            "share_gaps_le_7_days": np.nan,
            "max_signals_in_28_calendar_days": 0,
            "max_signals_in_calendar_month": 0,
            "longest_no_signal_gap_days": (
                int((exposure_end_exclusive - exposure_start).days)
                if exposure_start is not None and exposure_end_exclusive is not None
                else 0
            ),
        }
    dates = pd.Series(pd.to_datetime(signals["date"]).sort_values().unique())
    gaps = dates.diff().dt.days.dropna()
    rolling_max = 0
    for date in dates:
        rolling_max = max(
            rolling_max,
            int(((dates >= date) & (dates < date + pd.Timedelta(days=28))).sum()),
        )
    month_max = int(pd.Series(1, index=dates.dt.to_period("M")).groupby(level=0).sum().max())
    all_gaps = gaps.tolist()
    if exposure_start is not None:
        all_gaps.append(max(0, int((dates.iloc[0] - exposure_start).days)))
    if exposure_end_exclusive is not None:
        all_gaps.append(max(0, int((exposure_end_exclusive - dates.iloc[-1]).days)))
    return {
        "inter_signal_gap_days_median": float(gaps.median()) if len(gaps) else np.nan,
        "inter_signal_gap_days_p10": float(gaps.quantile(0.1)) if len(gaps) else np.nan,
        "share_gaps_le_7_days": float(gaps.le(7).mean()) if len(gaps) else np.nan,
        "max_signals_in_28_calendar_days": rolling_max,
        "max_signals_in_calendar_month": month_max,
        "longest_no_signal_gap_days": max(all_gaps) if all_gaps else 0,
    }
