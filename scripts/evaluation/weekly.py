"""Exploratory weekly policy: causal gate, quality constraints and continuous OOT state."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contracts import require_columns
from .policy import SelectedPolicy, apply_selected_policy, enumerate_policy_points, clustering_metrics
from .random_baseline import QuotaScheduleSampler, schedule_quotas, stratum_values, stable_seed

GATE_COLUMNS = ["median_applicable_rate_28d", "past_advantage_bps", "history_days", "history_complete", "attractiveness_gate"]


def attractiveness_gate(observations: pd.DataFrame) -> pd.DataFrame:
    """Attach causal daily history, retaining exactly the input effective-date rows."""
    require_columns(observations, ["date", "corridor", "rub_per_unit"], "gate observations")
    parts = []
    for _, group in observations.groupby("corridor", observed=True):
        group = group.sort_values("date").copy()
        if group["date"].duplicated().any():
            raise ValueError("Duplicate effective date in gate observations")
        rates = group.set_index("date")["rub_per_unit"].astype(float)
        if (~np.isfinite(rates) | rates.le(0)).any():
            raise ValueError("Gate requires finite positive rates")
        daily = rates.reindex(pd.date_range(rates.index.min(), rates.index.max())).ffill()
        previous = daily.shift(1).rolling(28, min_periods=28)
        group["median_applicable_rate_28d"] = previous.median().reindex(rates.index).to_numpy()
        group["history_days"] = daily.shift(1).rolling(28, min_periods=1).count().reindex(rates.index).fillna(0).astype(int).to_numpy()
        group["history_complete"] = group["history_days"].eq(28)
        group["past_advantage_bps"] = (group["median_applicable_rate_28d"] / group["rub_per_unit"] - 1) * 10000
        # Floating-point equality at the declared 50-bp boundary.
        group["attractiveness_gate"] = group["history_complete"] & group["past_advantage_bps"].ge(50 - 1e-10)
        parts.append(group)
    return pd.concat(parts).sort_index()


def quality_points(frame: pd.DataFrame, exposure_weeks: float, config: dict) -> pd.DataFrame:
    gated = frame.loc[frame["attractiveness_gate"]].copy()
    if gated.empty:
        return pd.DataFrame(columns=["threshold", "signals", "signals_per_week", "signal_hit_rate", "hit_rate_wilson_lower", "mean_regret_bps", "p90_regret_bps", "quality_pass"])
    points = enumerate_policy_points(gated, cooldown_days=config["cooldown_days"], exposure_weeks=exposure_weeks)
    from .policy import apply_cooldown
    regrets = [apply_cooldown(gated, t, config["cooldown_days"])["future_regret_bps"] for t in points["threshold"]]
    points["mean_regret_bps"] = [s.mean() for s in regrets]
    points["p90_regret_bps"] = [s.quantile(.9) for s in regrets]
    points["quality_pass"] = (
        points["signals"].ge(config["minimum_policy_signals"])
        & points["signal_hit_rate"].ge(config["minimum_safety"])
        & points["mean_regret_bps"].le(config["maximum_mean_regret_bps"])
        & points["p90_regret_bps"].le(config["maximum_p90_regret_bps"])
    )
    return points


def select_weekly_policy(points: pd.DataFrame, budget: float = 1.0) -> SelectedPolicy:
    feasible = points.loc[points["quality_pass"].astype(bool) & points["signals_per_week"].le(budget + 1e-12)]
    if feasible.empty:
        return SelectedPolicy(None, "inactive", "no_quality_feasible_policy")
    best = feasible.sort_values(["signals_per_week", "hit_rate_wilson_lower", "mean_regret_bps", "threshold"], ascending=[False, False, True, False], kind="stable").iloc[0]
    return SelectedPolicy(float(best["threshold"]), "active")


@dataclass
class DeliveryState:
    last_sent: dict[tuple[str, str], pd.Timestamp] = field(default_factory=dict)

    def apply(self, frame: pd.DataFrame, policy: SelectedPolicy, variant: str, cooldown_days: int, *, gated: bool = True) -> pd.DataFrame:
        corridors = frame["corridor"].unique()
        if len(corridors) != 1:
            raise ValueError("Delivery state requires exactly one corridor")
        key = (str(corridors[0]), variant)
        result = apply_selected_policy(frame, policy, cooldown_days=cooldown_days, last_sent=self.last_sent.get(key), gate_column="attractiveness_gate" if gated else None)
        selected = result.loc[result["selected_signal"], "date"]
        if len(selected):
            self.last_sent[key] = pd.Timestamp(selected.max())
        return result


def continuous_draws(universe: pd.DataFrame, schedule: pd.DataFrame, *, mode: str, draws: int, seed: int, cooldown_days: int, stream_id: str) -> pd.DataFrame:
    """Uniform exact schedules across all OOT folds with fold/stratum quotas.

    Suffix counts look ahead across fold boundaries, avoiding greedy boundary
    dead ends. Each draw traverses its own conditional states independently.
    """
    ordered = universe.sort_values("date", kind="stable").reset_index(drop=True)
    if schedule.empty:
        return ordered.head(0).assign(draw_id=pd.Series(dtype=int), random_mode=mode)
    def strata(frame):
        return frame["outer_fold"].astype(str) + "|" + stratum_values(frame, mode)
    quotas = {str(k): int(v) for k, v in strata(schedule).value_counts().items()}
    previous_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(max(previous_limit, len(ordered) * 4 + 1000))
        samples = []
        if len(ordered) <= 500:
            sampler = QuotaScheduleSampler(ordered["date"], strata(ordered), quotas, cooldown_days)
            for draw in range(draws):
                rng = np.random.default_rng(stable_seed(seed, "continuous_v4", stream_id, mode, draw))
                indices = sampler.sample(rng)
                samples.append(ordered.iloc[indices].assign(draw_id=draw, random_mode=mode))
            return pd.concat(samples, ignore_index=True)
        fold_order = ordered.groupby("outer_fold", sort=False)["date"].min().sort_values().index.tolist()
        sampler_cache: dict[tuple[str, pd.Timestamp | None], QuotaScheduleSampler] = {}
        for draw in range(draws):
            completed = None
            # Boundary conflicts are resolved by restarting the draw, preserving
            # every fold quota rather than greedily dropping a requested date.
            for attempt in range(100):
                rng = np.random.default_rng(stable_seed(seed, "continuous_v4", stream_id, mode, draw, attempt))
                selected_parts, last_sent = [], None
                try:
                    for fold_id in fold_order:
                        fold = ordered.loc[ordered["outer_fold"].eq(fold_id)]
                        if last_sent is not None:
                            fold = fold.loc[fold["date"].gt(last_sent + pd.Timedelta(days=cooldown_days))]
                        prefix = f"{fold_id}|"
                        fold_quotas = {key: value for key, value in quotas.items() if key.startswith(prefix)}
                        if not sum(fold_quotas.values()):
                            continue
                        cache_key = (str(fold_id), last_sent)
                        sampler = sampler_cache.get(cache_key)
                        if sampler is None:
                            sampler = QuotaScheduleSampler(fold["date"], strata(fold), fold_quotas, cooldown_days)
                            sampler_cache[cache_key] = sampler
                        indices = sampler.sample(rng)
                        selected = fold.reset_index(drop=True).iloc[indices]
                        selected_parts.append(selected)
                        last_sent = pd.Timestamp(selected["date"].max())
                    completed = pd.concat(selected_parts, ignore_index=True)
                    break
                except ValueError:
                    continue
            if completed is None:
                raise ValueError(f"No continuous cooldown-feasible schedule after 100 attempts for draw={draw}")
            samples.append(completed.assign(draw_id=draw, random_mode=mode))
        return pd.concat(samples, ignore_index=True)
    finally:
        sys.setrecursionlimit(previous_limit)


def baseline_frames(frame: pd.DataFrame, baseline: str) -> tuple[pd.DataFrame, str, str]:
    if baseline == "future_safety":
        return frame.copy(), "full", "future_safety_message_hit_v2"
    if baseline == "product":
        product = frame.copy()
        product["message_hit"] = (product["message_hit"].eq(1) & product["attractiveness_gate"]).astype(int)
        return product, "full", "gate28_50_and_message_hit_v1"
    if baseline == "conditional":
        return frame.loc[frame["attractiveness_gate"]].copy(), "gate28_50", "conditional_message_hit_v2"
    raise ValueError(f"Unknown baseline {baseline}")


def cadence(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    selected = frame.loc[frame["selected_signal"]].sort_values("date")
    gaps = selected["date"].diff().dt.days.dropna()
    weeks = pd.period_range(start, end - pd.Timedelta(days=1), freq="W-SUN")
    return {**clustering_metrics(selected, exposure_start=start, exposure_end_exclusive=end),
            "inter_signal_gap_days_p90": float(gaps.quantile(.9)) if len(gaps) else np.nan,
            "active_week_share": selected["date"].dt.to_period("W-SUN").nunique() / len(weeks),
            "signals_per_week": len(selected) / ((end - start).days / 7),
            "signal_hit_rate": selected["message_hit"].mean(),
            "mean_regret_bps": selected["future_regret_bps"].mean(),
            "p90_regret_bps": selected["future_regret_bps"].quantile(.9)}
