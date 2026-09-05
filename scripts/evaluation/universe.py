"""Construction and hashing of the model-independent eligible-date universe."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from .contracts import EligibilitySpec, require_columns


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def build_eligible_universe(
    frame: pd.DataFrame,
    spec: EligibilitySpec = EligibilitySpec(),
) -> pd.DataFrame:
    """Return all input rows with explicit eligibility and reason columns."""
    require_columns(
        frame,
        ["date", "corridor", "has_full_window", "same_rate_as_previous"],
        "eligible universe input",
    )
    result = frame.copy().sort_values(["date", "corridor"], kind="stable")
    full = _truthy(result["has_full_window"])
    unchanged = _truthy(result["same_rate_as_previous"])
    eligible = pd.Series(True, index=result.index)
    reasons = pd.Series("", index=result.index, dtype="object")
    if spec.require_full_window:
        reasons = reasons.mask(~full, "incomplete_target_window")
        eligible &= full
    if spec.exclude_unchanged_rate:
        reasons = reasons.mask(eligible & unchanged, "unchanged_effective_rate")
        eligible &= ~unchanged
    result["eligible"] = eligible.astype(bool)
    result["ineligible_reason"] = reasons.mask(eligible, "eligible")
    result["eligible_gap_days"] = np.nan
    eligible_gaps = (
        result.loc[eligible]
        .groupby("corridor", observed=True)["date"]
        .diff()
        .dt.days
    )
    result.loc[eligible, "eligible_gap_days"] = eligible_gaps
    result["eligibility_version"] = spec.version
    return result.reset_index(drop=True)


def eligible_rows(universe: pd.DataFrame) -> pd.DataFrame:
    require_columns(universe, ["eligible"], "eligible universe")
    return universe.loc[_truthy(universe["eligible"])].copy()


def compute_universe_id(
    universe: pd.DataFrame,
    *,
    extra_contract: Mapping[str, object] | None = None,
) -> str:
    require_columns(
        universe,
        ["date", "corridor", "eligible", "eligibility_version"],
        "eligible universe",
    )
    columns = ["date", "corridor", "eligible", "eligibility_version"]
    for optional in ("same_rate_as_previous", "has_full_window", "horizon_calendar_days"):
        if optional in universe.columns:
            columns.append(optional)
    normalized = universe[columns].copy().sort_values(["date", "corridor"], kind="stable")
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.strftime("%Y-%m-%d")
    payload = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    digest = hashlib.sha256()
    digest.update(payload)
    digest.update(
        json.dumps(extra_contract or {}, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    return digest.hexdigest()[:24]


def common_label_complete_through(
    universe: pd.DataFrame,
    corridors: Iterable[str],
) -> pd.Timestamp:
    eligible = eligible_rows(universe)
    maxima = eligible.loc[eligible["corridor"].isin(tuple(corridors))].groupby(
        "corridor", observed=True
    )["date"].max()
    missing = sorted(set(corridors) - set(maxima.index))
    if missing:
        raise ValueError("No eligible rows for corridors: " + ", ".join(missing))
    return pd.Timestamp(maxima.min()).normalize()


def validate_universe_independent_of_model(
    universes: Mapping[str, pd.DataFrame],
) -> str:
    identities = {name: compute_universe_id(frame) for name, frame in universes.items()}
    if len(set(identities.values())) != 1:
        raise AssertionError(f"Models received different eligible universes: {identities}")
    return next(iter(identities.values()))
