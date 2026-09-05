"""End-to-end orchestration for the frozen temporal_v3 evaluation protocol."""

from __future__ import annotations

import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import ParameterGrid

try:  # Running from repository root/imported by tests.
    from scripts.run_backtest import add_auxiliary_features, add_features
except ModuleNotFoundError:  # Running scripts/run_experiment.py directly.
    from run_backtest import add_auxiliary_features, add_features

from .artifacts import build_manifest, git_metadata, sha256_file, write_frame, write_json
from .audit import audit_result_bundle
from .calibration import IdentityCalibrator
from .contracts import ARTIFACT_SCHEMA_VERSION, EVALUATION_PROTOCOL_VERSION
from .metrics import aggregate_signal_metrics, score_metrics, signal_metrics
from .model_selection import (
    design_matrix,
    refit_selected_model,
    select_hyperparameters_temporal,
)
from .policy import (
    SelectedPolicy,
    apply_cooldown,
    apply_selected_policy,
    enumerate_policy_points,
    map_thresholds_to_frequency_budgets,
    select_operating_policy,
)
from .random_baseline import (
    RandomDrawBank,
    RandomDrawKey,
    draw_metrics,
    schedule_quotas,
    summarize_draw_metrics,
)
from .temporal import (
    build_v3_outer_folds,
    slice_role,
    validate_corridor_synchronization,
)
from .uncertainty import (
    model_vs_random_bootstrap,
    summarize_model_vs_random_bootstrap,
)
from .universe import (
    build_eligible_universe,
    common_label_complete_through,
    compute_universe_id,
    eligible_rows,
)


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def resolve_feature_columns(config: dict[str, Any], names: list[str]) -> list[str]:
    resolved: list[str] = []
    for name in names:
        section = config["sets"][name]
        resolved.extend(section.get("columns", []))
        if section.get("include"):
            resolved.extend(resolve_feature_columns(config, section["include"]))
    return list(dict.fromkeys(resolved))


def _load_universe_and_features(
    data_dir: Path,
    currencies: list[str],
    horizon: int,
    epsilon_bps: int,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, list[Path]]:
    needs_auxiliary = any(name.startswith(("usd_", "eur_")) for name in feature_columns)
    featured_frames: list[pd.DataFrame] = []
    universe_frames: list[pd.DataFrame] = []
    paths: list[Path] = []
    for currency in currencies:
        prefix = f"rub_{currency.lower()}"
        observation_path = data_dir / f"{prefix}_observations.csv"
        label_path = data_dir / f"{prefix}_labels_h{horizon}_e{epsilon_bps}bp.csv"
        paths.extend([observation_path, label_path])
        observations = pd.read_csv(observation_path, parse_dates=["date"])
        labels = pd.read_csv(label_path, parse_dates=["date"])
        label_columns = [
            "date",
            "corridor",
            "horizon_calendar_days",
            "has_full_window",
            "message_hit",
            "target_good_now",
            "future_regret_bps",
            "moment_advantage_bps",
        ]
        frame = add_features(observations).merge(
            labels[label_columns], on=["date", "corridor"], validate="one_to_one"
        )
        universe = build_eligible_universe(frame)
        universe_frames.append(universe)
        featured = eligible_rows(universe)
        featured["message_hit"] = featured["message_hit"].astype(int)
        if needs_auxiliary:
            featured = add_auxiliary_features(featured, data_dir, ("USD", "EUR"))
            paths.extend(
                [data_dir / "rub_usd_observations.csv", data_dir / "rub_eur_observations.csv"]
            )
        missing = sorted(set(feature_columns) - set(featured.columns))
        if missing:
            raise ValueError(f"Missing features for {currency}: {missing}")
        featured_frames.append(featured)
    return (
        pd.concat(universe_frames, ignore_index=True),
        pd.concat(featured_frames, ignore_index=True).sort_values(
            ["date", "corridor"], kind="stable"
        ),
        list(dict.fromkeys(paths)),
    )


def _score(
    model: Any,
    frame: pd.DataFrame,
    feature_columns: list[str],
    model_columns: list[str],
    *,
    include_corridor_feature: bool,
    corridor_categories: list[str],
) -> pd.DataFrame:
    result = frame.copy()
    matrix = design_matrix(
        result,
        feature_columns,
        include_corridor_feature=include_corridor_feature,
        corridor_categories=corridor_categories,
    ).reindex(columns=model_columns, fill_value=0)
    result["raw_score"] = model.predict_proba(matrix)[:, 1]
    return result


def _project(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    selected = list(
        dict.fromkeys(column for column in columns if column in frame.columns)
    )
    return frame[selected].copy()


SCORE_ARTIFACT_COLUMNS = [
    "date", "corridor", "rub_per_unit", "message_hit", "target_good_now",
    "future_regret_bps", "moment_advantage_bps", "raw_score", "calibrated_score",
    "calibration_method", "temporal_role",
]

DECISION_ARTIFACT_COLUMNS = [
    *SCORE_ARTIFACT_COLUMNS, "candidate", "selected_signal", "policy_status",
    "inactive_reason", "threshold", "frontier_point_id",
    "requested_signals_per_week",
]


def _random_evaluation(
    universe: pd.DataFrame,
    schedule: pd.DataFrame,
    *,
    universe_id: str,
    corridor: str,
    outer_fold: str,
    mode: str,
    cooldown_days: int,
    draws: int,
    bank: RandomDrawBank,
    materialize_schedules: bool,
) -> tuple[dict[str, float], pd.DataFrame, pd.DataFrame]:
    if schedule.empty:
        return (
            {"random_hit_rate": np.nan, "random_hit_rate_mcse": np.nan},
            pd.DataFrame(),
            pd.DataFrame(),
        )
    quotas = tuple(sorted(schedule_quotas(schedule, mode).items()))
    key = RandomDrawKey(universe_id, corridor, outer_fold, mode, quotas)
    sampled = [bank.draw(universe, key, draw_id, cooldown_days) for draw_id in range(draws)]
    metrics = draw_metrics(sampled)
    summary = summarize_draw_metrics(metrics)
    metrics["corridor"] = corridor
    metrics["outer_fold"] = outer_fold
    metrics["random_mode"] = mode
    metrics["quota_vector"] = json.dumps(dict(quotas), sort_keys=True)
    schedules = (
        _project(
            pd.concat(sampled, ignore_index=True),
            [
                "date", "corridor", "message_hit", "future_regret_bps",
                "moment_advantage_bps", "draw_id", "random_mode",
            ],
        )
        if materialize_schedules
        else pd.DataFrame()
    )
    return summary, metrics, schedules


def _add_identity(frame: pd.DataFrame, identity: dict[str, object]) -> pd.DataFrame:
    result = frame.copy()
    for key, value in identity.items():
        result[key] = value
    result["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
    result["evaluation_protocol_version"] = EVALUATION_PROTOCOL_VERSION
    return result


def _score_frontier(
    frame: pd.DataFrame,
    identity: dict[str, object],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for coverage in (0.01, 0.02, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 1.0):
        count = max(1, int(np.ceil(len(frame) * coverage)))
        selected = frame.sort_values(
            ["calibrated_score", "date"], ascending=[False, True], kind="stable"
        ).head(count)
        rows.append(
            {
                **identity,
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
                "score_coverage_requested": coverage,
                "score_coverage_realized": count / len(frame),
                "rows": count,
                "hit_rate": float(selected["message_hit"].mean()),
                "mean_realized_regret_bps": float(selected["future_regret_bps"].mean()),
            }
        )
    return pd.DataFrame(rows)


def run_v3(args: Any) -> Path:
    initial_git_state = git_metadata()
    hypotheses = [item.strip() for item in args.hypotheses.split(",") if item.strip()]
    if len(hypotheses) != 1:
        raise ValueError("temporal_v3 currently requires exactly one hypothesis per run")
    hypothesis_path = args.hypotheses_dir / f"{hypotheses[0]}.toml"
    hypothesis = read_toml(hypothesis_path)
    if hypothesis.get("evaluation_protocol") != EVALUATION_PROTOCOL_VERSION:
        raise ValueError("Hypothesis must explicitly declare evaluation_protocol=temporal_v3")
    evaluation_path = args.config_dir / "evaluation_v3.toml"
    feature_path = args.config_dir / "features.toml"
    model_path = args.config_dir / "models.toml"
    evaluation = read_toml(evaluation_path)
    features_config = read_toml(feature_path)
    models_config = read_toml(model_path)
    horizons = [int(item) for item in args.horizons.split(",") if item.strip()]
    if len(horizons) != 1:
        raise ValueError("temporal_v3 requires one target horizon per run")
    horizon = horizons[0]
    epsilon = (
        int(args.epsilon_bps.split(",")[0]) if args.epsilon_bps else 50
    )
    currencies = list(hypothesis["corridors"])
    corridor_categories = [f"RUB_{item}" for item in currencies]
    feature_columns = resolve_feature_columns(features_config, hypothesis["feature_sets"])
    universe, frame, input_paths = _load_universe_and_features(
        args.data_dir, currencies, horizon, epsilon, feature_columns
    )
    universe_id = compute_universe_id(
        universe, extra_contract={"horizon_days": horizon, "epsilon_bps": epsilon}
    )
    label_cutoff = common_label_complete_through(universe, corridor_categories)
    data_cutoff = pd.Timestamp(universe["date"].max()).normalize()
    folds = build_v3_outer_folds(
        int(evaluation["temporal"]["first_outer_year"]),
        int(label_cutoff.year),
        horizon,
        first_selection_year=int(evaluation["temporal"]["first_selection_year"]),
        observed_data_cutoff=data_cutoff,
        label_complete_through=label_cutoff,
    )
    selected_models = [item.strip() for item in args.models.split(",") if item.strip()]
    selected_strategies = [item.strip() for item in args.strategies.split(",") if item.strip()]
    allowed_models = [item for item in hypothesis["models"] if item in selected_models]
    allowed_strategies = [item for item in hypothesis["strategies"] if item in selected_strategies]
    if not allowed_models or not allowed_strategies:
        raise ValueError("No model/strategy remains after hypothesis filtering")
    unsupported = set(allowed_strategies) - {
        "pooled_with_corridor_thresholds",
        "pooled_without_corridor_feature",
    }
    if unsupported:
        raise ValueError(f"temporal_v3 pooled engine does not support yet: {sorted(unsupported)}")
    if len(allowed_models) != 1 or len(allowed_strategies) != 1:
        raise ValueError(
            "temporal_v3 writes one model/strategy per bundle so paired runs share immutable artifacts"
        )

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_v3")
    output = args.output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    smoke = bool(getattr(args, "smoke_evaluation", False))
    random_draws = int(evaluation["random"]["smoke_draws" if smoke else "draws"])
    bootstrap_replicates = int(
        evaluation["bootstrap"]["smoke_replicates" if smoke else "replicates"]
    )
    cooldown_days = int(evaluation["policy"]["cooldown_days"])
    budgets = [float(item) for item in evaluation["policy"]["frequency_grid"]]
    primary_random_mode = str(evaluation["random"]["primary_stratification"])
    sensitivity_random_modes = [
        str(item) for item in evaluation["random"]["sensitivity_stratifications"]
    ]
    bank = RandomDrawBank(int(evaluation["random"]["seed"]))

    fold_boundaries: list[dict[str, object]] = []
    inner_metrics_all: list[pd.DataFrame] = []
    model_fit_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    oot_scores_all: list[pd.DataFrame] = []
    decisions_all: list[pd.DataFrame] = []
    selected_policy_rows: list[dict[str, object]] = []
    score_metric_rows: list[dict[str, object]] = []
    signal_metric_rows: list[dict[str, object]] = []
    score_frontiers: list[pd.DataFrame] = []
    policy_frontier_rows: list[dict[str, object]] = []
    candidate_policy_metrics: list[pd.DataFrame] = []
    frontier_decisions_all: list[pd.DataFrame] = []
    random_metrics_all: list[pd.DataFrame] = []
    selected_random_schedules: list[pd.DataFrame] = []
    exposures: list[dict[str, object]] = []

    for fold in folds:
        print(f"[temporal_v3] {fold.fold_id}: selection/refit", flush=True)
        fold_boundaries.append(
            {
                "outer_fold": fold.fold_id,
                "test_year": fold.test_year,
                "horizon_days": horizon,
                "refit_end_exclusive": fold.refit_train.end_exclusive,
                "calibration_start": fold.calibration.start,
                "calibration_end_exclusive": fold.calibration.end_exclusive,
                "policy_start": fold.policy.start,
                "policy_end_exclusive": fold.policy.end_exclusive,
                "test_start": fold.outer_test.start,
                "test_end_exclusive": fold.outer_test.end_exclusive,
                "inner_fold_count": len(fold.inner_folds),
                "is_partial_fold": fold.is_partial_fold,
                "data_cutoff": fold.data_cutoff,
                "label_complete_through": fold.label_complete_through,
            }
        )
        exposures.append(
            {
                "outer_fold": fold.fold_id,
                "exposure_start": fold.outer_test.start,
                "exposure_end_exclusive": fold.outer_test.end_exclusive,
            }
        )
        for strategy in allowed_strategies:
            include_corridor = strategy != "pooled_without_corridor_feature"
            global_threshold = False
            for model_name in allowed_models:
                definition = models_config["models"][model_name]
                candidates = list(ParameterGrid(definition.get("search", {}))) or [{}]
                selection, inner_metrics = select_hyperparameters_temporal(
                    frame,
                    fold.inner_folds,
                    model_name=model_name,
                    model_definition=definition,
                    candidates=candidates,
                    feature_columns=feature_columns,
                    include_corridor_feature=include_corridor,
                    corridor_categories=corridor_categories,
                    minimum_train_rows_per_corridor=int(
                        evaluation["temporal"]["minimum_train_rows_per_corridor"]
                    ),
                    minimum_validation_rows_per_corridor=int(
                        evaluation["temporal"]["minimum_role_rows_per_corridor"]
                    ),
                )
                identity = {
                    "run_id": run_id,
                    "hypothesis_id": hypothesis["id"],
                    "model_id": model_name,
                    "feature_set_id": "+".join(hypothesis["feature_sets"]),
                    "target_id": hypothesis["target"],
                    "strategy": strategy,
                    "outer_fold": fold.fold_id,
                    "test_year": fold.test_year,
                    "is_partial_fold": fold.is_partial_fold,
                    "universe_id": universe_id,
                }
                inner_metrics_all.append(_add_identity(inner_metrics, identity))
                refit = slice_role(frame, fold.refit_train)
                validate_corridor_synchronization(
                    refit,
                    corridor_categories,
                    minimum_rows_per_corridor=int(
                        evaluation["temporal"]["minimum_train_rows_per_corridor"]
                    ),
                )
                model, model_columns = refit_selected_model(
                    refit,
                    model_name=model_name,
                    model_definition=definition,
                    hyperparameters=selection.hyperparameters,
                    feature_columns=feature_columns,
                    include_corridor_feature=include_corridor,
                    corridor_categories=corridor_categories,
                )
                model_fit_rows.append(
                    {
                        **identity,
                        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
                        "hyperparameters": json.dumps(selection.hyperparameters, sort_keys=True),
                        "inner_fold_count": selection.inner_fold_count,
                        "mean_inner_pr_auc_gain": selection.mean_pr_auc_gain,
                        "worst_inner_year_pr_auc_gain": selection.worst_year_pr_auc_gain,
                        "refit_rows": len(refit),
                    }
                )
                calibration = _score(
                    model,
                    slice_role(frame, fold.calibration),
                    feature_columns,
                    model_columns,
                    include_corridor_feature=include_corridor,
                    corridor_categories=corridor_categories,
                )
                policy_block = _score(
                    model,
                    slice_role(frame, fold.policy),
                    feature_columns,
                    model_columns,
                    include_corridor_feature=include_corridor,
                    corridor_categories=corridor_categories,
                )
                test = _score(
                    model,
                    slice_role(frame, fold.outer_test),
                    feature_columns,
                    model_columns,
                    include_corridor_feature=include_corridor,
                    corridor_categories=corridor_categories,
                )
                validate_corridor_synchronization(
                    test,
                    corridor_categories,
                    minimum_rows_per_corridor=int(
                        evaluation["temporal"]["minimum_test_rows_per_corridor"]
                    ),
                )
                calibrator = IdentityCalibrator().fit(calibration)
                for scored in (calibration, policy_block, test):
                    scored["calibrated_score"] = calibrator.transform(scored["raw_score"])
                    scored["calibration_method"] = calibrator.method
                calibration_rows.append({**identity, **score_metrics(calibration, "calibrated_score")})
                threshold_groups = [("ALL", policy_block)] if global_threshold else list(policy_block.groupby("corridor", observed=True))
                thresholds: dict[str, SelectedPolicy] = {}
                for threshold_corridor, policy_group in threshold_groups:
                    exposure_weeks = (fold.outer_test.start - fold.policy.start).days / 7.0
                    points = enumerate_policy_points(
                        policy_group,
                        cooldown_days=cooldown_days,
                        exposure_weeks=exposure_weeks,
                    )
                    points["matched_random_lift"] = np.nan
                    feasible = points.loc[
                        points["signals"].ge(int(evaluation["policy"]["minimum_policy_signals"]))
                        & points["signals_per_week"].le(float(evaluation["policy"]["hard_max_signals_per_week"]))
                    ]
                    if len(feasible):
                        top_wilson = feasible["hit_rate_wilson_lower"].max()
                        ties = feasible.index[feasible["hit_rate_wilson_lower"].eq(top_wilson)]
                        for point_index in ties:
                            threshold = float(points.loc[point_index, "threshold"])
                            group_random_rates: list[tuple[int, float]] = []
                            random_groups = list(policy_group.groupby("corridor", observed=True))
                            for corridor, subgroup in random_groups:
                                schedule = apply_cooldown(subgroup, threshold, cooldown_days)
                                summary, _, _ = _random_evaluation(
                                    subgroup,
                                    schedule,
                                    universe_id=universe_id,
                                    corridor=str(corridor),
                                    outer_fold=f"{fold.fold_id}_policy",
                                    mode=primary_random_mode,
                                    cooldown_days=cooldown_days,
                                    draws=min(random_draws, 200),
                                    bank=bank,
                                    materialize_schedules=False,
                                )
                                if len(schedule):
                                    group_random_rates.append((len(schedule), summary["random_hit_rate"]))
                            total = sum(count for count, _ in group_random_rates)
                            random_rate = sum(count * rate for count, rate in group_random_rates) / total if total else np.nan
                            hit = float(points.loc[point_index, "signal_hit_rate"])
                            points.loc[point_index, "matched_random_lift"] = hit / random_rate if random_rate else np.nan
                    candidate_policy_metrics.append(
                        _add_identity(
                            points,
                            {**identity, "corridor": threshold_corridor},
                        )
                    )
                    selected = select_operating_policy(
                        points,
                        minimum_signals=int(evaluation["policy"]["minimum_policy_signals"]),
                        maximum_signals_per_week=float(evaluation["policy"]["hard_max_signals_per_week"]),
                    )
                    targets = corridor_categories if threshold_corridor == "ALL" else [str(threshold_corridor)]
                    for corridor in targets:
                        thresholds[corridor] = selected
                    selected_policy_rows.append(
                        {
                            **identity,
                            "corridor": threshold_corridor,
                            "threshold": selected.threshold,
                            "policy_status": selected.status,
                            "inactive_reason": selected.inactive_reason,
                        }
                    )

                for corridor, test_group in test.groupby("corridor", observed=True):
                    print(
                        f"[temporal_v3] {fold.fold_id} {corridor}: policy/random/frontier",
                        flush=True,
                    )
                    corridor_identity = {**identity, "corridor": corridor}
                    decisions = apply_selected_policy(
                        test_group,
                        thresholds[str(corridor)],
                        cooldown_days=cooldown_days,
                    )
                    decisions = _add_identity(decisions, corridor_identity)
                    decisions_all.append(
                        _project(
                            decisions,
                            DECISION_ARTIFACT_COLUMNS
                            + list(corridor_identity)
                            + ["artifact_schema_version", "evaluation_protocol_version"],
                        )
                    )
                    oot_scores_all.append(
                        _add_identity(
                            _project(test_group, SCORE_ARTIFACT_COLUMNS), corridor_identity
                        )
                    )
                    score_metric_rows.append({**corridor_identity, **score_metrics(test_group)})
                    score_frontiers.append(_score_frontier(test_group, corridor_identity))
                    delivered = decisions.loc[decisions["selected_signal"]]
                    random_summary, random_metrics, random_schedules = _random_evaluation(
                        test_group,
                        delivered,
                        universe_id=universe_id,
                        corridor=str(corridor),
                        outer_fold=fold.fold_id,
                        mode=primary_random_mode,
                        cooldown_days=cooldown_days,
                        draws=random_draws,
                        bank=bank,
                        materialize_schedules=True,
                    )
                    if len(random_metrics):
                        random_metrics_all.append(_add_identity(random_metrics, corridor_identity))
                    if len(random_schedules):
                        selected_random_schedules.append(_add_identity(random_schedules, corridor_identity))
                    for sensitivity_mode in sensitivity_random_modes:
                        _, sensitivity_metrics, _ = _random_evaluation(
                            test_group,
                            delivered,
                            universe_id=universe_id,
                            corridor=str(corridor),
                            outer_fold=fold.fold_id,
                            mode=sensitivity_mode,
                            cooldown_days=cooldown_days,
                            draws=random_draws,
                            bank=bank,
                            materialize_schedules=False,
                        )
                        if len(sensitivity_metrics):
                            random_metrics_all.append(
                                _add_identity(sensitivity_metrics, corridor_identity)
                            )
                    metrics = signal_metrics(
                        decisions,
                        exposure_start=fold.outer_test.start,
                        exposure_end_exclusive=fold.outer_test.end_exclusive,
                        random_hit_rate=random_summary["random_hit_rate"],
                        random_mcse=random_summary["random_hit_rate_mcse"],
                        cooldown_days=cooldown_days,
                    )
                    signal_metric_rows.append({**corridor_identity, **metrics})

                    policy_group = policy_block.loc[policy_block["corridor"].eq(corridor)]
                    policy_points = enumerate_policy_points(
                        policy_group,
                        cooldown_days=cooldown_days,
                        exposure_weeks=(fold.outer_test.start - fold.policy.start).days / 7.0,
                    )
                    frontier = map_thresholds_to_frequency_budgets(policy_points, budgets)
                    for point in frontier.itertuples(index=False):
                        if point.frontier_status != "active" or not np.isfinite(point.threshold):
                            inactive_decisions = apply_selected_policy(
                                test_group,
                                SelectedPolicy(None, "inactive", "unattainable_budget"),
                                cooldown_days=cooldown_days,
                            )
                            inactive_decisions["frontier_point_id"] = point.frontier_point_id
                            inactive_decisions["requested_signals_per_week"] = (
                                point.requested_signals_per_week
                            )
                            frontier_decisions_all.append(
                                _add_identity(
                                    _project(inactive_decisions, DECISION_ARTIFACT_COLUMNS),
                                    corridor_identity,
                                )
                            )
                            policy_frontier_rows.append(
                                {**corridor_identity, **point._asdict(), "signals": 0}
                            )
                            continue
                        frontier_policy = SelectedPolicy(float(point.threshold), "active")
                        frontier_decisions = apply_selected_policy(
                            test_group, frontier_policy, cooldown_days=cooldown_days
                        )
                        frontier_decisions["frontier_point_id"] = point.frontier_point_id
                        frontier_decisions["requested_signals_per_week"] = (
                            point.requested_signals_per_week
                        )
                        frontier_decisions_all.append(
                            _add_identity(
                                _project(frontier_decisions, DECISION_ARTIFACT_COLUMNS),
                                corridor_identity,
                            )
                        )
                        frontier_delivered = frontier_decisions.loc[
                            frontier_decisions["selected_signal"]
                        ]
                        frontier_random, _, _ = _random_evaluation(
                            test_group,
                            frontier_delivered,
                            universe_id=universe_id,
                            corridor=str(corridor),
                            outer_fold=f"{fold.fold_id}_{point.frontier_point_id}",
                            mode=primary_random_mode,
                            cooldown_days=cooldown_days,
                            draws=random_draws,
                            bank=bank,
                            materialize_schedules=False,
                        )
                        frontier_metrics = signal_metrics(
                            frontier_decisions,
                            exposure_start=fold.outer_test.start,
                            exposure_end_exclusive=fold.outer_test.end_exclusive,
                            random_hit_rate=frontier_random["random_hit_rate"],
                            random_mcse=frontier_random["random_hit_rate_mcse"],
                            cooldown_days=cooldown_days,
                        )
                        policy_frontier_rows.append(
                            {**corridor_identity, **point._asdict(), **frontier_metrics}
                        )

    fold_boundaries_frame = _add_identity(pd.DataFrame(fold_boundaries), {})
    oot_scores = pd.concat(oot_scores_all, ignore_index=True)
    decisions = pd.concat(decisions_all, ignore_index=True)
    frontier_decisions_frame = pd.concat(frontier_decisions_all, ignore_index=True)
    signal_metrics_frame = _add_identity(pd.DataFrame(signal_metric_rows), {})
    summary = pd.DataFrame([aggregate_signal_metrics(signal_metrics_frame)])
    delivered_all = decisions.loc[decisions["selected_signal"].astype(bool)]
    false_delivered = delivered_all.loc[delivered_all["message_hit"].eq(0)]
    summary["mean_realized_regret_bps"] = delivered_all["future_regret_bps"].mean()
    summary["p90_realized_regret_bps"] = delivered_all["future_regret_bps"].quantile(0.90)
    summary["p95_realized_regret_bps"] = delivered_all["future_regret_bps"].quantile(0.95)
    summary["false_push_regret_bps_mean"] = false_delivered["future_regret_bps"].mean()
    summary["moment_advantage_bps_mean"] = delivered_all["moment_advantage_bps"].mean()
    summary["run_id"] = run_id
    summary["evaluation_protocol_version"] = EVALUATION_PROTOCOL_VERSION
    summary["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
    random_schedules = (
        pd.concat(selected_random_schedules, ignore_index=True)
        if selected_random_schedules
        else pd.DataFrame()
    )
    exposure_frame = pd.DataFrame(exposures).drop_duplicates("outer_fold")
    random_draw_metrics = (
        pd.concat(random_metrics_all, ignore_index=True)
        if random_metrics_all
        else pd.DataFrame()
    )
    if len(random_draw_metrics):
        primary_draws = random_draw_metrics.loc[
            random_draw_metrics["random_mode"].eq(primary_random_mode)
        ]
        aggregate_random_draws = (
            primary_draws.groupby("draw_id", observed=True)
            .agg(signal_hits=("signal_hits", "sum"), signals=("signals", "sum"))
            .reset_index()
        )
        aggregate_random_draws["signal_hit_rate"] = (
            aggregate_random_draws["signal_hits"] / aggregate_random_draws["signals"]
        )
        aggregate_random_draws = _add_identity(aggregate_random_draws, {})
        aggregate_random_mcse = float(
            aggregate_random_draws["signal_hit_rate"].std(ddof=1)
            / np.sqrt(len(aggregate_random_draws))
        )
    else:
        aggregate_random_draws = pd.DataFrame()
        aggregate_random_mcse = np.nan
    summary["matched_random_mcse"] = aggregate_random_mcse

    view_rows: list[dict[str, object]] = []
    view_rows.append({"evaluation_view": "all_folds", **aggregate_signal_metrics(signal_metrics_frame)})
    full_cells = signal_metrics_frame.loc[~signal_metrics_frame["is_partial_fold"].astype(bool)]
    if len(full_cells):
        view_rows.append({"evaluation_view": "full_years_only", **aggregate_signal_metrics(full_cells)})
    for year, year_cells in signal_metrics_frame.groupby("test_year", observed=True):
        view_rows.append({"evaluation_view": f"year_{int(year)}", **aggregate_signal_metrics(year_cells)})
        other = signal_metrics_frame.loc[signal_metrics_frame["test_year"].ne(year)]
        if len(other):
            view_rows.append({"evaluation_view": f"leave_{int(year)}_out", **aggregate_signal_metrics(other)})
    evaluation_views = _add_identity(pd.DataFrame(view_rows), {"run_id": run_id})

    bootstrap_frames: list[pd.DataFrame] = []
    uncertainty_frames: list[pd.DataFrame] = []

    def add_bootstrap_view(
        view_name: str,
        view_decisions: pd.DataFrame,
        view_schedules: pd.DataFrame,
        view_exposures: pd.DataFrame,
        block_days: int,
    ) -> None:
        if view_decisions.empty or view_schedules.empty or view_exposures.empty:
            return
        sampled = model_vs_random_bootstrap(
            view_decisions,
            view_schedules,
            view_exposures,
            block_days=block_days,
            replicates=bootstrap_replicates,
            seed=int(evaluation["bootstrap"]["seed"]),
        )
        sampled["evaluation_view"] = view_name
        sampled["block_length_days"] = block_days
        bootstrap_frames.append(_add_identity(sampled, {"run_id": run_id}))
        summarized = summarize_model_vs_random_bootstrap(sampled)
        summarized["evaluation_view"] = view_name
        summarized["block_length_days"] = block_days
        uncertainty_frames.append(_add_identity(summarized, {"run_id": run_id}))

    if len(random_schedules):
        print("[temporal_v3] synchronized bootstrap", flush=True)
        primary_block_days = int(evaluation["bootstrap"]["primary_block_days"])
        add_bootstrap_view("all_folds", decisions, random_schedules, exposure_frame, primary_block_days)
        for block_days in evaluation["bootstrap"]["sensitivity_block_days"]:
            add_bootstrap_view(
                "all_folds", decisions, random_schedules, exposure_frame, int(block_days)
            )
        full_fold_ids = set(
            fold_boundaries_frame.loc[
                ~fold_boundaries_frame["is_partial_fold"].astype(bool), "outer_fold"
            ]
        )
        if full_fold_ids:
            add_bootstrap_view(
                "full_years_only",
                decisions.loc[decisions["outer_fold"].isin(full_fold_ids)],
                random_schedules.loc[random_schedules["outer_fold"].isin(full_fold_ids)],
                exposure_frame.loc[exposure_frame["outer_fold"].isin(full_fold_ids)],
                primary_block_days,
            )
        for omitted_year in sorted(decisions["test_year"].unique()):
            kept_folds = set(
                decisions.loc[decisions["test_year"].ne(omitted_year), "outer_fold"]
            )
            add_bootstrap_view(
                f"leave_{int(omitted_year)}_out",
                decisions.loc[decisions["outer_fold"].isin(kept_folds)],
                random_schedules.loc[random_schedules["outer_fold"].isin(kept_folds)],
                exposure_frame.loc[exposure_frame["outer_fold"].isin(kept_folds)],
                primary_block_days,
            )
    bootstrap = pd.concat(bootstrap_frames, ignore_index=True) if bootstrap_frames else pd.DataFrame()
    uncertainty = pd.concat(uncertainty_frames, ignore_index=True) if uncertainty_frames else pd.DataFrame()

    write_frame(output / "fold_boundaries.csv", fold_boundaries_frame)
    write_frame(output / "eligible_universe.csv.gz", _add_identity(universe, {}))
    write_frame(output / "inner_selection_metrics.csv", pd.concat(inner_metrics_all, ignore_index=True))
    write_frame(output / "model_fits.csv", _add_identity(pd.DataFrame(model_fit_rows), {}))
    write_frame(output / "calibration_metrics.csv", _add_identity(pd.DataFrame(calibration_rows), {}))
    write_frame(output / "oot_scores.csv.gz", oot_scores)
    write_frame(output / "candidate_policy_metrics.csv", pd.concat(candidate_policy_metrics, ignore_index=True))
    write_frame(output / "selected_policies.csv", _add_identity(pd.DataFrame(selected_policy_rows), {}))
    write_frame(output / "policy_decisions.csv.gz", decisions)
    write_frame(output / "frontier_decisions.csv.gz", frontier_decisions_frame)
    write_frame(output / "score_frontier.csv", pd.concat(score_frontiers, ignore_index=True))
    write_frame(output / "policy_frontier.csv", _add_identity(pd.DataFrame(policy_frontier_rows), {}))
    write_frame(output / "model_metrics.csv", _add_identity(pd.DataFrame(score_metric_rows), {}))
    write_frame(output / "signal_policy_metrics.csv", signal_metrics_frame)
    write_frame(output / "corridor_year_metrics.csv", signal_metrics_frame)
    write_frame(output / "summary.csv", summary)
    write_frame(output / "evaluation_views.csv", evaluation_views)
    write_frame(
        output / "random_draw_metrics.csv.gz",
        random_draw_metrics,
    )
    write_frame(output / "random_schedules.csv.gz", random_schedules)
    write_frame(output / "random_aggregate_draws.csv.gz", aggregate_random_draws)
    write_frame(output / "uncertainty_summary.csv", uncertainty)
    write_frame(output / "bootstrap_replicates.csv.gz", bootstrap)
    random_registry = {
        "version": evaluation["random"]["version"],
        "draws": random_draws,
        "seed": evaluation["random"]["seed"],
        "primary_stratification": evaluation["random"]["primary_stratification"],
        "sensitivity_stratifications": sensitivity_random_modes,
        "universe_id": universe_id,
        "aggregate_mcse": aggregate_random_mcse,
        "maximum_aggregate_mcse": evaluation["random"]["maximum_aggregate_mcse"],
    }
    write_json(output / "random_draw_registry.json", random_registry)
    manifest = build_manifest(
        run_id=run_id,
        command=sys.argv,
        config=evaluation,
        input_paths=[hypothesis_path, evaluation_path, feature_path, model_path, *input_paths],
        universe_ids={"all_corridors": universe_id},
        git_state=initial_git_state,
        extra={
            "hypothesis": hypothesis,
            "target_contract": {
                "target": "message_hit",
                "horizon_calendar_days": horizon,
                "epsilon_bps": epsilon,
                "future_window": "T+1_through_T+h_calendar_days_forward_filled",
                "positive_rule": "future_regret_bps_le_epsilon_bps",
            },
            "eligibility_contract": {
                "requires_full_label_window": True,
                "effective_date_rows_only": True,
                "exclude_same_rate_as_previous": True,
                "common_label_complete_through": str(label_cutoff.date()),
            },
            "feature_columns": feature_columns,
            "models": allowed_models,
            "strategies": allowed_strategies,
            "random_draws": random_draws,
            "bootstrap_replicates": bootstrap_replicates,
            "smoke_evaluation": smoke,
        },
    )
    manifest["quality_gates"] = {
        "not_smoke": not smoke,
        "aggregate_random_mcse_pass": bool(
            np.isfinite(aggregate_random_mcse)
            and aggregate_random_mcse
            <= float(evaluation["random"]["maximum_aggregate_mcse"])
        ),
        "all_policy_cells_materialized": len(signal_metrics_frame)
        == len(folds) * len(corridor_categories),
    }
    manifest["canonical_eligible"] = bool(
        manifest["canonical_eligible"]
        and all(manifest["quality_gates"].values())
    )
    manifest["artifacts"] = [
        {
            "path": artifact.name,
            "sha256": sha256_file(artifact),
            "bytes": artifact.stat().st_size,
        }
        for artifact in sorted(output.iterdir())
        if artifact.is_file()
    ]
    write_json(output / "manifest.json", manifest)
    audit_report = audit_result_bundle(output)
    write_json(output / "audit_report.json", audit_report)
    report = (
        "# Wave 0 temporal_v3 result\n\n"
        f"Run: `{run_id}`. Protocol: `{EVALUATION_PROTOCOL_VERSION}`. "
        f"Outer folds: {len(folds)}; random draws: {random_draws}; "
        f"bootstrap replicates: {bootstrap_replicates}.\n\n"
        "Canonical metrics are stored in `summary.csv`, `policy_frontier.csv`, "
        "and `uncertainty_summary.csv`.\n"
    )
    (output / "RESULTS.md").write_text(report, encoding="utf-8")
    return output
