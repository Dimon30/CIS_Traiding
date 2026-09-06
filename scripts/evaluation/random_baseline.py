"""Versioned matched-random schedules with exact cooldown/quota sampling."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np
import pandas as pd

from .contracts import MATCHED_RANDOM_VERSION, require_columns


def stable_seed(base_seed: int, *parts: object) -> int:
    payload = json.dumps(
        [base_seed, MATCHED_RANDOM_VERSION, *parts],
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def cooldown_state(dates: pd.Series, cooldown_days: int) -> tuple[np.ndarray, np.ndarray]:
    ordered = pd.to_datetime(dates).reset_index(drop=True)
    values = ordered.to_numpy(dtype="datetime64[D]").astype(np.int64)
    next_index = np.searchsorted(values, values + cooldown_days, side="right")
    max_from = np.zeros(len(values) + 1, dtype=int)
    for index in range(len(values) - 1, -1, -1):
        max_from[index] = max(max_from[index + 1], 1 + max_from[next_index[index]])
    return next_index, max_from


class QuotaScheduleSampler:
    """Precomputed exact sampler reusable across Monte Carlo draw IDs."""

    def __init__(
        self,
        dates: pd.Series,
        strata: pd.Series,
        quotas: dict[str, int],
        cooldown_days: int,
    ) -> None:
        ordered = pd.DataFrame(
            {"date": pd.to_datetime(dates), "stratum": strata.astype(str)}
        )
        ordered = ordered.sort_values("date", kind="stable").reset_index(drop=True)
        next_index, max_from = cooldown_state(ordered["date"], cooldown_days)
        names = tuple(sorted(quotas))
        positions = {name: index for index, name in enumerate(names)}
        target = tuple(int(quotas[name]) for name in names)
        if any(value < 0 for value in target):
            raise ValueError("Quotas must be non-negative")
        stratum_indices = np.array(
            [positions.get(value, -1) for value in ordered["stratum"]]
        )
        suffix_counts = np.zeros((len(ordered) + 1, len(names)), dtype=np.int32)
        for index in range(len(ordered) - 1, -1, -1):
            suffix_counts[index] = suffix_counts[index + 1]
            position = int(stratum_indices[index])
            if position >= 0:
                suffix_counts[index, position] += 1

        self.ordered = ordered
        self.next_index = next_index
        self.max_from = max_from
        self.names = names
        self.target = target
        self.stratum_indices = stratum_indices
        self.suffix_counts = suffix_counts

        @lru_cache(maxsize=None)
        def ways(index: int, remaining: tuple[int, ...]) -> int:
            total_remaining = sum(remaining)
            if total_remaining == 0:
                return 1
            if index >= len(self.ordered) or total_remaining > int(self.max_from[index]):
                return 0
            if any(
                remaining[position] > int(self.suffix_counts[index, position])
                for position in range(len(remaining))
            ):
                return 0
            result = ways(index + 1, remaining)
            position = int(self.stratum_indices[index])
            if position >= 0 and remaining[position] > 0:
                reduced = list(remaining)
                reduced[position] -= 1
                result += ways(int(self.next_index[index]), tuple(reduced))
            return result

        self.ways = ways
        if self.ways(0, self.target) == 0:
            raise ValueError(
                f"No cooldown-feasible schedule for quotas={dict(zip(names, target))}"
            )

    def sample(self, rng: np.random.Generator) -> np.ndarray:
        selected: list[int] = []
        index = 0
        remaining = self.target
        while sum(remaining):
            skip_ways = self.ways(index + 1, remaining)
            take_ways = 0
            reduced_tuple: tuple[int, ...] | None = None
            position = int(self.stratum_indices[index])
            if position >= 0 and remaining[position] > 0:
                reduced = list(remaining)
                reduced[position] -= 1
                reduced_tuple = tuple(reduced)
                take_ways = self.ways(int(self.next_index[index]), reduced_tuple)
            total = skip_ways + take_ways
            if total <= 0:
                raise RuntimeError("Quota sampler reached an infeasible state")
            if take_ways and rng.random() < take_ways / total:
                selected.append(index)
                remaining = reduced_tuple  # type: ignore[assignment]
                index = int(self.next_index[index])
            else:
                index += 1
        return np.asarray(selected, dtype=int)


def sample_quota_schedule_indices(
    dates: pd.Series,
    strata: pd.Series,
    quotas: dict[str, int],
    cooldown_days: int,
    rng: np.random.Generator,
) -> np.ndarray:
    return QuotaScheduleSampler(dates, strata, quotas, cooldown_days).sample(rng)


def stratum_values(frame: pd.DataFrame, mode: str) -> pd.Series:
    dates = pd.to_datetime(frame["date"])
    if mode == "fold_count_only":
        return pd.Series("ALL", index=frame.index)
    month = dates.dt.strftime("%Y-%m")
    if mode == "calendar_month":
        return month
    if mode == "calendar_month_weekday":
        return month + "|weekday=" + dates.dt.dayofweek.astype(str)
    if mode == "month_update_gap":
        require_columns(frame, ["eligible_gap_days"], "update-gap random universe")
        gap = pd.to_numeric(frame["eligible_gap_days"], errors="coerce")
        bucket = np.select([gap.eq(1), gap.eq(2)], ["1", "2"], default="3+")
        return month + "|gap=" + pd.Series(bucket, index=frame.index)
    raise ValueError(f"Unknown random stratification mode: {mode}")


def schedule_quotas(schedule: pd.DataFrame, mode: str) -> dict[str, int]:
    values = stratum_values(schedule, mode)
    return {str(key): int(value) for key, value in values.value_counts().items()}


@dataclass(frozen=True)
class RandomDrawKey:
    universe_id: str
    corridor: str
    outer_fold: str
    mode: str
    quotas: tuple[tuple[str, int], ...]


class RandomDrawBank:
    def __init__(self, base_seed: int = 42, maximum_cached_samplers: int = 4):
        self.base_seed = base_seed
        self.maximum_cached_samplers = maximum_cached_samplers
        self._samplers: OrderedDict[
            tuple[RandomDrawKey, int], QuotaScheduleSampler
        ] = OrderedDict()

    def draw(
        self,
        universe: pd.DataFrame,
        key: RandomDrawKey,
        draw_id: int,
        cooldown_days: int,
    ) -> pd.DataFrame:
        ordered = universe.sort_values("date", kind="stable").reset_index(drop=True)
        strata = stratum_values(ordered, key.mode)
        seed = stable_seed(
            self.base_seed,
            key.universe_id,
            key.corridor,
            key.outer_fold,
            key.mode,
            draw_id,
        )
        sampler_key = (key, cooldown_days)
        if sampler_key not in self._samplers:
            self._samplers[sampler_key] = QuotaScheduleSampler(
                ordered["date"], strata, dict(key.quotas), cooldown_days
            )
            while len(self._samplers) > self.maximum_cached_samplers:
                self._samplers.popitem(last=False)
        else:
            self._samplers.move_to_end(sampler_key)
        indices = self._samplers[sampler_key].sample(np.random.default_rng(seed))
        result = ordered.iloc[indices].copy()
        result["draw_id"] = draw_id
        result["random_mode"] = key.mode
        return result


def draw_metrics(draws: Iterable[pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for draw in draws:
        require_columns(draw, ["draw_id", "message_hit"], "random draw")
        count = len(draw)
        hits = int(draw["message_hit"].sum()) if count else 0
        rows.append(
            {
                "draw_id": int(draw["draw_id"].iloc[0]) if count else -1,
                "signals": count,
                "signal_hits": hits,
                "signal_hit_rate": hits / count if count else np.nan,
                "future_regret_bps_mean": (
                    float(draw["future_regret_bps"].mean())
                    if count and "future_regret_bps" in draw
                    else np.nan
                ),
                "future_regret_bps_p90": (
                    float(draw["future_regret_bps"].quantile(0.9))
                    if count and "future_regret_bps" in draw else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def summarize_draw_metrics(metrics: pd.DataFrame) -> dict[str, float]:
    require_columns(metrics, ["signal_hit_rate"], "random draw metrics")
    values = metrics["signal_hit_rate"].dropna().to_numpy(dtype=float)
    if values.size == 0:
        return {"random_hit_rate": np.nan, "random_hit_rate_mcse": np.nan}
    return {
        "random_hit_rate": float(values.mean()),
        "random_hit_rate_mcse": (
            float(values.std(ddof=1) / np.sqrt(values.size)) if values.size > 1 else 0.0
        ),
        "random_hit_rate_ci_low": float(np.quantile(values, 0.025)),
        "random_hit_rate_ci_high": float(np.quantile(values, 0.975)),
    }
