"""Post-run invariants for frozen temporal_v3 experiment bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .contracts import ARTIFACT_SCHEMA_VERSION, EVALUATION_PROTOCOL_VERSION, require_columns


REQUIRED_ARTIFACTS = (
    "manifest.json",
    "fold_boundaries.csv",
    "eligible_universe.csv.gz",
    "oot_scores.csv.gz",
    "candidate_policy_metrics.csv",
    "selected_policies.csv",
    "policy_decisions.csv.gz",
    "frontier_decisions.csv.gz",
    "policy_frontier.csv",
    "random_schedules.csv.gz",
    "random_draw_metrics.csv.gz",
    "uncertainty_summary.csv",
    "summary.csv",
)


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1"})


def continuous_cooldown_violations(frame: pd.DataFrame, cooldown_days: int, *, random: bool = False) -> pd.DataFrame:
    """Audit streams over all years, never resetting on outer_fold."""
    keys = [key for key in ("model", "strategy", "corridor", "variant", "frontier_point_id", "baseline", "random_mode") if key in frame]
    if random:
        keys.append("draw_id")
    elif "selected_signal" in frame:
        frame = frame.loc[_as_bool(frame["selected_signal"])].copy()
    rows = []
    for key, group in frame.groupby(keys, observed=True, dropna=False):
        ordered = group.sort_values("date").copy()
        ordered["previous_send"] = ordered["date"].shift(1)
        ordered["gap_days"] = (ordered["date"] - ordered["previous_send"]).dt.days
        rows.append(ordered.loc[ordered["gap_days"].le(cooldown_days)])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def audit_continuous_schedules(decisions: pd.DataFrame, random: pd.DataFrame, cooldown_days: int) -> dict:
    for frame, is_random in ((decisions, False), (random, True)):
        violations = continuous_cooldown_violations(frame, cooldown_days, random=is_random)
        if len(violations):
            raise AssertionError(f"Continuous cooldown violation: random={is_random}, rows={len(violations)}")
    return {"status": "pass", "continuous_model_and_random_cooldown": True}


def audit_result_bundle(path: Path) -> dict[str, object]:
    missing = [name for name in REQUIRED_ARTIFACTS if not (path / name).exists()]
    if missing:
        raise FileNotFoundError("Missing temporal_v3 artifacts: " + ", ".join(missing))
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("evaluation_protocol_version") != EVALUATION_PROTOCOL_VERSION:
        raise AssertionError("Manifest is not temporal_v3")
    if manifest.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise AssertionError("Manifest artifact schema is not v3")

    boundaries = pd.read_csv(path / "fold_boundaries.csv", parse_dates=[
        "calibration_end_exclusive", "policy_start", "policy_end_exclusive", "test_start"
    ])
    for row in boundaries.itertuples(index=False):
        gap = pd.Timedelta(days=int(row.horizon_days))
        if row.calibration_end_exclusive + gap > row.policy_start:
            raise AssertionError(f"Calibration purge fails in {row.outer_fold}")
        if row.policy_end_exclusive + gap > row.test_start:
            raise AssertionError(f"Policy purge fails in {row.outer_fold}")

    scores = pd.read_csv(path / "oot_scores.csv.gz", parse_dates=["date"])
    decisions = pd.read_csv(path / "policy_decisions.csv.gz", parse_dates=["date"])
    keys = ["outer_fold", "date", "corridor"]
    require_columns(scores, [*keys, "raw_score", "calibrated_score"], "OOT scores")
    require_columns(
        decisions,
        [*keys, "candidate", "selected_signal", "message_hit"],
        "policy decisions",
    )
    if scores.duplicated(keys).any() or decisions.duplicated(keys).any():
        raise AssertionError("OOT score/decision keys are not unique")
    if set(scores[keys].itertuples(index=False, name=None)) != set(
        decisions[keys].itertuples(index=False, name=None)
    ):
        raise AssertionError("Every frozen OOT score must have exactly one policy decision")
    if (_as_bool(decisions["selected_signal"]) & ~_as_bool(decisions["candidate"])).any():
        raise AssertionError("A delivered signal is not a threshold candidate")
    cooldown_days = int(manifest["config"]["policy"]["cooldown_days"])
    selected = decisions.loc[_as_bool(decisions["selected_signal"])]
    for key, group in selected.groupby(["corridor"], observed=True):
        gaps = group.sort_values("date")["date"].diff().dt.days.dropna()
        if gaps.le(cooldown_days).any():
            raise AssertionError(f"Cooldown violation in {key}")

    random = pd.read_csv(path / "random_schedules.csv.gz", parse_dates=["date"])
    require_columns(random, [*keys, "draw_id", "message_hit"], "random schedules")
    labels = decisions[[*keys, "message_hit"]]
    checked = random.merge(
        labels,
        on=keys,
        how="left",
        suffixes=("_random", "_model"),
        validate="many_to_one",
    )
    if checked["message_hit_model"].isna().any():
        raise AssertionError("Random selected a date outside the model eligible universe")
    if not checked["message_hit_random"].eq(checked["message_hit_model"]).all():
        raise AssertionError("Random and model universes disagree on labels")
    audit_continuous_schedules(decisions, random, cooldown_days)
    frontier = pd.read_csv(path / "frontier_decisions.csv.gz", parse_dates=["date"])
    frontier_violations = continuous_cooldown_violations(frontier, cooldown_days)
    if len(frontier_violations):
        raise AssertionError("Continuous frontier cooldown violation")
    model_quotas = (
        selected.assign(month=selected["date"].dt.to_period("M").astype(str))
        .groupby(["outer_fold", "corridor", "month"], observed=True)
        .size()
    )
    random_quotas = (
        random.assign(month=random["date"].dt.to_period("M").astype(str))
        .groupby(["draw_id", "outer_fold", "corridor", "month"], observed=True)
        .size()
    )
    for draw_id in random["draw_id"].unique():
        observed = random_quotas.loc[draw_id]
        if not observed.reindex(model_quotas.index, fill_value=0).equals(model_quotas):
            raise AssertionError(f"Calendar-month quotas differ for random draw {draw_id}")

    for name in ("summary.csv", "policy_frontier.csv", "uncertainty_summary.csv"):
        frame = pd.read_csv(path / name)
        require_columns(
            frame,
            ["artifact_schema_version", "evaluation_protocol_version"],
            name,
        )
        if not frame["artifact_schema_version"].eq(ARTIFACT_SCHEMA_VERSION).all():
            raise AssertionError(f"Wrong artifact schema in {name}")
    return {
        "status": "pass",
        "run_id": manifest.get("run_id"),
        "outer_rows": len(scores),
        "signals": len(selected),
        "random_rows": len(random),
        "checks": 12,
    }
