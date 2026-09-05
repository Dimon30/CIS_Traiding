"""Cross-run comparisons for compatible temporal_v3 result bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .artifacts import validate_protocol_compatibility
from .contracts import require_columns
from .policy import thin_to_common_count
from .uncertainty import paired_policy_bootstrap, summarize_paired_bootstrap


def load_compatible_runs(left: Path, right: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifests = [
        json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        for path in (left, right)
    ]
    validate_protocol_compatibility(manifests)
    if manifests[0].get("config") != manifests[1].get("config"):
        raise ValueError("Runs use different frozen evaluation configurations")
    if manifests[0].get("target_contract") != manifests[1].get("target_contract"):
        raise ValueError("Runs use different target contracts")
    for key in ("random_draws", "bootstrap_replicates", "smoke_evaluation"):
        if manifests[0].get(key) != manifests[1].get(key):
            raise ValueError(f"Runs use different execution contract: {key}")
    if manifests[0].get("universe_ids") != manifests[1].get("universe_ids"):
        raise ValueError("Runs use different eligible universes")
    return manifests[0], manifests[1]


def compare_selected_policies(
    left: Path,
    right: Path,
    *,
    block_days: int = 28,
    replicates: int = 5000,
    seed: int = 42029,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return paired replicates and their summary for two frozen policies."""
    load_compatible_runs(left, right)
    left_decisions = pd.read_csv(left / "policy_decisions.csv.gz", parse_dates=["date"])
    right_decisions = pd.read_csv(right / "policy_decisions.csv.gz", parse_dates=["date"])
    boundaries = pd.read_csv(left / "fold_boundaries.csv")
    require_columns(
        boundaries,
        ["outer_fold", "test_start", "test_end_exclusive"],
        "fold boundaries",
    )
    exposures = boundaries.rename(
        columns={
            "test_start": "exposure_start",
            "test_end_exclusive": "exposure_end_exclusive",
        }
    )[["outer_fold", "exposure_start", "exposure_end_exclusive"]]
    exposures["exposure_start"] = pd.to_datetime(exposures["exposure_start"])
    exposures["exposure_end_exclusive"] = pd.to_datetime(
        exposures["exposure_end_exclusive"]
    )
    replicates_frame = paired_policy_bootstrap(
        left_decisions,
        right_decisions,
        exposures,
        block_days=block_days,
        replicates=replicates,
        seed=seed,
    )
    return replicates_frame, summarize_paired_bootstrap(replicates_frame)


def compare_policy_frontiers(left: Path, right: Path) -> pd.DataFrame:
    """Align OOT frontier metrics at the frozen communication-budget grid."""
    load_compatible_runs(left, right)
    keys = ["outer_fold", "corridor", "requested_signals_per_week"]
    columns = [
        *keys,
        "frontier_status",
        "signals_per_week",
        "signal_hit_rate",
        "matched_random_hit_rate",
        "lift",
        "mean_realized_regret_bps",
    ]
    left_frame = pd.read_csv(left / "policy_frontier.csv")
    right_frame = pd.read_csv(right / "policy_frontier.csv")
    require_columns(left_frame, columns, "left policy frontier")
    require_columns(right_frame, columns, "right policy frontier")
    merged = left_frame[columns].merge(
        right_frame[columns],
        on=keys,
        how="outer",
        suffixes=("_left", "_right"),
        validate="one_to_one",
    )
    merged["delta_hit_rate"] = (
        merged["signal_hit_rate_right"] - merged["signal_hit_rate_left"]
    )
    merged["delta_mean_regret_bps"] = (
        merged["mean_realized_regret_bps_right"]
        - merged["mean_realized_regret_bps_left"]
    )
    merged["frequency_gap_per_week"] = (
        merged["signals_per_week_right"] - merged["signals_per_week_left"]
    )
    return merged


def compare_frontiers_at_common_count(left: Path, right: Path) -> pd.DataFrame:
    """Score-only thinning diagnostic at equal realized signal counts."""
    load_compatible_runs(left, right)
    left_frame = pd.read_csv(left / "frontier_decisions.csv.gz", parse_dates=["date"])
    right_frame = pd.read_csv(right / "frontier_decisions.csv.gz", parse_dates=["date"])
    group_keys = ["outer_fold", "corridor", "frontier_point_id"]
    rows: list[dict[str, object]] = []
    left_groups = {key: group for key, group in left_frame.groupby(group_keys, observed=True)}
    right_groups = {key: group for key, group in right_frame.groupby(group_keys, observed=True)}
    for key in sorted(set(left_groups).intersection(right_groups)):
        left_selected = int(left_groups[key]["selected_signal"].astype(bool).sum())
        right_selected = int(right_groups[key]["selected_signal"].astype(bool).sum())
        common_count = min(left_selected, right_selected)
        if common_count == 0:
            rows.append(
                {
                    **dict(zip(group_keys, key)),
                    "common_signal_count": 0,
                    "comparison_status": "inactive",
                }
            )
            continue
        left_thinned = thin_to_common_count(left_groups[key], common_count)
        right_thinned = thin_to_common_count(right_groups[key], common_count)
        left_hit = float(left_thinned["message_hit"].mean())
        right_hit = float(right_thinned["message_hit"].mean())
        left_regret = float(left_thinned["future_regret_bps"].mean())
        right_regret = float(right_thinned["future_regret_bps"].mean())
        rows.append(
            {
                **dict(zip(group_keys, key)),
                "common_signal_count": common_count,
                "comparison_status": "active",
                "left_hit_rate": left_hit,
                "right_hit_rate": right_hit,
                "delta_hit_rate": right_hit - left_hit,
                "left_mean_regret_bps": left_regret,
                "right_mean_regret_bps": right_regret,
                "delta_mean_regret_bps": right_regret - left_regret,
            }
        )
    return pd.DataFrame(rows)
