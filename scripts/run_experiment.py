"""Run hypothesis-driven FX experiments with leak-free walk-forward evaluation.

Every outer fold uses an expanding training window, the previous calendar year
for model/threshold selection, a horizon-sized purge gap, and the following year
once for final evaluation. Both pooled and per-corridor strategies use identical
dates. Auxiliary USD/EUR features are joined backward as-of their effective date.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import ParameterGrid
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_backtest import (  # noqa: E402
    add_auxiliary_features,
    apply_cooldown,
    load_model_frame,
    random_baseline,
    threshold_candidates,
    weeks_in,
    wilson_lower,
)


DEFAULT_MODELS = "logistic,catboost,random_forest,svm,knn,naive_bayes"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hypotheses", default="H007_add_usd_eur")
    parser.add_argument("--horizons", default="3")
    parser.add_argument("--epsilon-bps", help="Comma-separated values, e.g. 0,50,100")
    parser.add_argument("--models", default=DEFAULT_MODELS)
    parser.add_argument(
        "--strategies", default="per_corridor,pooled_with_corridor_thresholds"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-root", type=Path, default=Path("results/experiments"))
    parser.add_argument("--config-dir", type=Path, default=Path("configs"))
    parser.add_argument("--hypotheses-dir", type=Path, default=Path("hypotheses"))
    parser.add_argument("--run-id", help="Stable output directory name")
    parser.add_argument("--save-models", action="store_true")
    parser.add_argument("--transfer-amount-rub", type=float, default=100_000.0)
    return parser.parse_args()


def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def resolve_feature_columns(feature_config: dict[str, Any], names: list[str]) -> list[str]:
    sets = feature_config["sets"]
    resolved: list[str] = []
    for name in names:
        section = sets[name]
        if "columns" in section:
            resolved.extend(section["columns"])
        if "include" in section:
            resolved.extend(resolve_feature_columns(feature_config, section["include"]))
    return list(dict.fromkeys(resolved))


def load_frames(
    data_dir: Path,
    currencies: list[str],
    horizon: int,
    epsilon_bps: int,
    feature_columns: list[str],
) -> dict[str, pd.DataFrame]:
    needs_auxiliary = any(name.startswith(("usd_", "eur_")) for name in feature_columns)
    result: dict[str, pd.DataFrame] = {}
    for currency in currencies:
        frame = load_model_frame(data_dir, currency, horizon, epsilon_bps).assign(
            currency=currency
        )
        if needs_auxiliary:
            frame = add_auxiliary_features(frame, data_dir, ("USD", "EUR"))
        missing = sorted(set(feature_columns) - set(frame.columns))
        if missing:
            raise ValueError(f"Missing features for {currency}: {missing}")
        result[currency] = frame
    return result


def split_frame(
    frame: pd.DataFrame, test_year: int, horizon: int, validation_years: int = 1
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validation_start = pd.Timestamp(test_year - validation_years, 1, 1)
    test_start = pd.Timestamp(test_year, 1, 1)
    next_test_start = pd.Timestamp(test_year + 1, 1, 1)
    gap = pd.Timedelta(days=horizon)
    train = frame.loc[frame["date"] < validation_start - gap].copy()
    validation = frame.loc[
        (frame["date"] >= validation_start) & (frame["date"] < test_start - gap)
    ].copy()
    test = frame.loc[
        (frame["date"] >= test_start) & (frame["date"] < next_test_start)
    ].copy()
    return train, validation, test


def add_corridor_columns(frame: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    values = pd.Categorical(
        frame["corridor"], categories=[f"RUB_{item}" for item in categories]
    )
    return pd.get_dummies(values, prefix="corridor", dtype=float)


def design_matrix(
    frame: pd.DataFrame,
    feature_columns: list[str],
    pooled: bool,
    currencies: list[str],
) -> pd.DataFrame:
    matrix = frame[feature_columns].reset_index(drop=True).astype(float)
    if pooled:
        corridor = add_corridor_columns(frame, currencies).reset_index(drop=True)
        matrix = pd.concat([matrix, corridor], axis=1)
    return matrix.replace([np.inf, -np.inf], np.nan)


def safe_auc(target: pd.Series, scores: np.ndarray) -> float:
    return float(roc_auc_score(target, scores)) if target.nunique() == 2 else float("nan")


def safe_ap(target: pd.Series, scores: np.ndarray) -> float:
    return float(average_precision_score(target, scores)) if target.nunique() == 2 else float("nan")


def estimator(model_name: str, params: dict[str, Any], fixed: dict[str, Any]) -> Pipeline:
    scale = False
    if model_name == "logistic":
        cleaned = {key: (None if value == "none" else value) for key, value in params.items()}
        model = LogisticRegression(**fixed, **cleaned)
        scale = True
    elif model_name == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(**fixed, **params)
    elif model_name == "catboost":
        model = CatBoostClassifier(**fixed, **params)
    elif model_name == "random_forest":
        model = RandomForestClassifier(**fixed, **params)
    elif model_name == "svm":
        model = SVC(**fixed, **params)
        scale = True
    elif model_name == "knn":
        model = KNeighborsClassifier(**fixed, **params)
        scale = True
    elif model_name == "naive_bayes":
        model = GaussianNB(**fixed, **params)
        scale = True
    else:
        raise ValueError(f"Unknown model: {model_name}")
    steps: list[tuple[str, Any]] = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scale", StandardScaler()))
    steps.append(("model", model))
    return Pipeline(steps)


def best_model(
    model_name: str,
    config: dict[str, Any],
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> tuple[Pipeline, dict[str, Any], float, float]:
    definition = config["models"][model_name]
    candidates = list(ParameterGrid(definition.get("search", {}))) or [{}]
    fixed = definition.get("fixed", {})
    best: tuple[Pipeline, dict[str, Any], float, float] | None = None
    for params in candidates:
        fitted = estimator(model_name, params, fixed).fit(x_train, y_train)
        scores = fitted.predict_proba(x_validation)[:, 1]
        candidate_auc = safe_auc(y_validation, scores)
        candidate_ap = safe_ap(y_validation, scores)
        if best is None or (not np.isnan(candidate_ap) and candidate_ap > best[3]):
            best = fitted, params, candidate_auc, candidate_ap
    if best is None:
        raise RuntimeError("No hyperparameter candidate was fitted")
    return best


def threshold_for_group(
    validation: pd.DataFrame,
    cooldown_days: int,
    min_signals: int,
    max_signals_per_week: float,
) -> float:
    baseline = float(validation["message_hit"].mean())
    rows: list[dict[str, float]] = []
    for threshold in threshold_candidates(validation["score"].to_numpy()):
        signals = apply_cooldown(validation, float(threshold), cooldown_days)
        if signals.empty:
            continue
        hit = float(signals["message_hit"].mean())
        rows.append(
            {
                "threshold": float(threshold),
                "signals": len(signals),
                "signals_per_week": len(signals) / weeks_in(validation),
                "wilson": wilson_lower(int(signals["message_hit"].sum()), len(signals)),
                "lift_proxy": hit / baseline if baseline else float("nan"),
            }
        )
    eligible = [
        item for item in rows
        if item["signals"] >= min_signals and item["signals_per_week"] <= max_signals_per_week
    ]
    eligible = eligible or [item for item in rows if item["signals"] >= min(5, min_signals)] or rows
    if not eligible:
        raise RuntimeError("Validation period has no threshold candidates")
    return float(max(eligible, key=lambda item: (item["wilson"], item["lift_proxy"], item["signals"]))["threshold"])


def global_threshold(
    validation: pd.DataFrame,
    cooldown_days: int,
    min_signals: int,
    max_signals_per_week: float,
) -> float:
    rows: list[dict[str, float]] = []
    groups = list(validation.groupby("corridor"))
    baseline = float(validation["message_hit"].mean())
    for threshold in threshold_candidates(validation["score"].to_numpy()):
        selected = pd.concat(
            [apply_cooldown(group, float(threshold), cooldown_days) for _, group in groups],
            ignore_index=True,
        )
        if selected.empty:
            continue
        hit = float(selected["message_hit"].mean())
        rows.append(
            {
                "threshold": float(threshold),
                "signals": len(selected),
                "signals_per_week": len(selected) / sum(weeks_in(group) for _, group in groups),
                "wilson": wilson_lower(int(selected["message_hit"].sum()), len(selected)),
                "lift_proxy": hit / baseline if baseline else float("nan"),
            }
        )
    expected_min = min_signals * len(groups)
    eligible = [
        item for item in rows
        if item["signals"] >= expected_min and item["signals_per_week"] <= max_signals_per_week
    ]
    eligible = eligible or [item for item in rows if item["signals"] >= min(5 * len(groups), expected_min)] or rows
    if not eligible:
        raise RuntimeError("Validation period has no global threshold candidates")
    return float(max(eligible, key=lambda item: (item["wilson"], item["lift_proxy"], item["signals"]))["threshold"])


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return float("nan"), float("nan")
    rate = successes / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    adjustment = z * np.sqrt((rate * (1.0 - rate) + z * z / (4.0 * total)) / total)
    return (centre - adjustment) / denominator, (centre + adjustment) / denominator


def evaluate_test(
    test: pd.DataFrame,
    thresholds: dict[str, float],
    cooldown_days: int,
    random_repeats: int,
    seed: int,
    transfer_amount_rub: float,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    signals_all: list[pd.DataFrame] = []
    predictions_all: list[pd.DataFrame] = []
    for index, (corridor, group) in enumerate(test.groupby("corridor")):
        group = group.sort_values("date").copy()
        threshold = thresholds[corridor]
        group["candidate"] = group["score"] >= threshold
        signals = apply_cooldown(group, threshold, cooldown_days)
        group["selected_signal"] = group.index.isin(signals.index)
        random_mean, random_low, random_high = random_baseline(
            group, signal_count=len(signals), cooldown_days=cooldown_days,
            repeats=random_repeats, seed=seed + index,
        )
        hit = float(signals["message_hit"].mean()) if len(signals) else float("nan")
        successes = int(signals["message_hit"].sum()) if len(signals) else 0
        hit_low, hit_high = wilson_interval(successes, len(signals))
        scores = group["score"].to_numpy(dtype=float)
        labels = group["message_hit"].astype(int)
        candidate = group["candidate"].astype(int)
        rows.append(
            {
                **metadata,
                "corridor": corridor,
                "threshold": threshold,
                "test_rows": len(group),
                "target_rate": float(labels.mean()),
                "roc_auc": safe_auc(labels, scores),
                "pr_auc": safe_ap(labels, scores),
                "brier": float(brier_score_loss(labels, scores)),
                "log_loss": float(log_loss(labels, np.clip(scores, 1e-9, 1 - 1e-9))),
                "balanced_accuracy": float(balanced_accuracy_score(labels, candidate)),
                "candidate_precision": float(precision_score(labels, candidate, zero_division=0)),
                "candidate_recall": float(recall_score(labels, candidate, zero_division=0)),
                "signals": len(signals),
                "signals_per_week": len(signals) / weeks_in(group),
                "signal_hit_rate": hit,
                "hit_rate_ci_low": hit_low,
                "hit_rate_ci_high": hit_high,
                "false_push_rate": 1.0 - hit if len(signals) else float("nan"),
                "random_hit_rate": random_mean,
                "random_hit_rate_ci_low": random_low,
                "random_hit_rate_ci_high": random_high,
                "lift": hit / random_mean if random_mean and len(signals) else float("nan"),
                "moment_advantage_bps_mean": float(signals["moment_advantage_bps"].mean()) if len(signals) else float("nan"),
                "future_regret_bps_mean": float(signals["future_regret_bps"].mean()) if len(signals) else float("nan"),
                "client_advantage_rub_mean": float(signals["moment_advantage_bps"].mean() * transfer_amount_rub / 10_000) if len(signals) else float("nan"),
                "client_regret_rub_mean": float(signals["future_regret_bps"].mean() * transfer_amount_rub / 10_000) if len(signals) else float("nan"),
            }
        )
        for key, value in metadata.items():
            group[key] = value
        group["threshold"] = threshold
        identity_columns = [
            "hypothesis_id", "horizon_days", "epsilon_bps", "strategy", "model", "test_year"
        ]
        prediction_columns = [
            "date", "corridor", "rub_per_unit", "message_hit", "target_good_now",
            "future_regret_bps", "moment_advantage_bps", "score", "candidate",
            "selected_signal", "threshold", *identity_columns,
        ]
        predictions_all.append(group[prediction_columns].copy())
        if len(signals):
            signals = signals.copy()
            signals["threshold"] = threshold
            for key, value in metadata.items():
                signals[key] = value
            signal_columns = [
                "date", "corridor", "rub_per_unit", "message_hit", "target_good_now",
                "future_regret_bps", "moment_advantage_bps", "score", "threshold",
                *identity_columns,
            ]
            signals_all.append(signals[signal_columns].copy())
    return (
        rows,
        pd.concat(signals_all, ignore_index=True) if signals_all else pd.DataFrame(),
        pd.concat(predictions_all, ignore_index=True) if predictions_all else pd.DataFrame(),
    )


def run_strategy(
    *, hypothesis: dict[str, Any], feature_columns: list[str], model_name: str,
    strategy: str, frames: dict[str, pd.DataFrame], horizon: int,
    epsilon_bps: int, configs: dict[str, Any], artifact_dir: Path,
    save_models: bool, transfer_amount_rub: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[pd.DataFrame], list[pd.DataFrame], list[dict[str, Any]]]:
    validation_config = configs["validation"]
    currencies = hypothesis["corridors"]
    all_frame = pd.concat([frames[item] for item in currencies], ignore_index=True)
    last_year = int(all_frame["date"].dt.year.max())
    pooled = strategy != "per_corridor"
    fold_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    signal_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    model_records: list[dict[str, Any]] = []

    for test_year in range(int(validation_config["first_test_year"]), last_year + 1):
        sources = [(None, all_frame)] if pooled else [(item, frames[item]) for item in currencies]
        for currency, source in sources:
            train, validation, test = split_frame(
                source, test_year, horizon, int(validation_config.get("validation_years", 1))
            )
            if len(train) < 500 or len(validation) < 100 or len(test) < 40:
                continue
            if train["message_hit"].nunique() < 2 or validation["message_hit"].nunique() < 2:
                continue
            x_train = design_matrix(train, feature_columns, pooled, currencies)
            x_validation = design_matrix(validation, feature_columns, pooled, currencies).reindex(columns=x_train.columns, fill_value=0)
            x_test = design_matrix(test, feature_columns, pooled, currencies).reindex(columns=x_train.columns, fill_value=0)
            fitted, params, validation_auc, validation_ap = best_model(
                model_name, configs["models"], x_train, train["message_hit"], x_validation, validation["message_hit"]
            )
            validation = validation.copy()
            test = test.copy()
            validation["score"] = fitted.predict_proba(x_validation)[:, 1]
            test["score"] = fitted.predict_proba(x_test)[:, 1]
            if pooled and strategy == "pooled":
                threshold = global_threshold(
                    validation, validation_config["cooldown_days"],
                    validation_config["min_validation_signals"], validation_config["max_signals_per_week"]
                )
                thresholds = {corridor: threshold for corridor in test["corridor"].unique()}
            else:
                thresholds = {
                    corridor: threshold_for_group(
                        group, validation_config["cooldown_days"],
                        validation_config["min_validation_signals"], validation_config["max_signals_per_week"]
                    )
                    for corridor, group in validation.groupby("corridor")
                }
            metadata = {
                "hypothesis_id": hypothesis["id"], "horizon_days": horizon,
                "epsilon_bps": epsilon_bps, "strategy": strategy, "model": model_name,
                "test_year": test_year, "validation_auc": validation_auc,
                "validation_pr_auc": validation_ap, "train_rows": len(train),
                "validation_rows": len(validation), "feature_count": len(x_train.columns),
                "hyperparameters": json.dumps(params, sort_keys=True),
            }
            rows, signals, predictions = evaluate_test(
                test, thresholds, validation_config["cooldown_days"],
                validation_config["random_repeats"], validation_config["random_seed"] + test_year,
                transfer_amount_rub, metadata,
            )
            fold_rows.extend(rows)
            signal_frames.append(signals)
            prediction_frames.append(predictions)
            threshold_rows.extend([{**metadata, "corridor": key, "threshold": value} for key, value in thresholds.items()])
            record = {**metadata, "corridor": f"RUB_{currency}" if currency else "ALL"}
            if save_models:
                suffix = f"_{currency}" if currency else ""
                model_path = artifact_dir / "models" / f"{hypothesis['id']}_{strategy}{suffix}_{model_name}_h{horizon}_e{epsilon_bps}_{test_year}.joblib"
                model_path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump({"model": fitted, "features": list(x_train.columns), "thresholds": thresholds, "metadata": metadata}, model_path)
                record["path"] = str(model_path)
            model_records.append(record)
    return fold_rows, threshold_rows, signal_frames, prediction_frames, model_records


def summarize(folds: pd.DataFrame) -> pd.DataFrame:
    group_columns = ["hypothesis_id", "horizon_days", "epsilon_bps", "strategy", "model", "corridor"]
    rows: list[dict[str, Any]] = []
    for keys, group in folds.groupby(group_columns):
        valid = group.dropna(subset=["lift"])
        signals = int(valid["signals"].sum())
        tests = int(valid["test_rows"].sum())
        signal_weights = valid["signals"] if signals else None
        test_weights = valid["test_rows"] if tests else None
        def weighted(column: str, weights: pd.Series | None) -> float:
            return float(np.average(valid[column], weights=weights)) if len(valid) and weights is not None else float("nan")
        hit = weighted("signal_hit_rate", signal_weights)
        random = weighted("random_hit_rate", signal_weights)
        rows.append(
            {
                **dict(zip(group_columns, keys)), "folds": len(valid), "signals": signals,
                "signals_per_week": float(signals / sum(valid["signals"] / valid["signals_per_week"])) if signals else float("nan"),
                "signal_hit_rate": hit, "false_push_rate": 1.0 - hit if signals else float("nan"),
                "random_hit_rate": random, "lift": hit / random if random else float("nan"),
                "median_fold_lift": float(valid["lift"].median()) if len(valid) else float("nan"),
                "min_fold_lift": float(valid["lift"].min()) if len(valid) else float("nan"),
                "folds_lift_ge_1_3": int((valid["lift"] >= 1.3).sum()),
                "roc_auc": weighted("roc_auc", test_weights), "pr_auc": weighted("pr_auc", test_weights),
                "brier": weighted("brier", test_weights), "balanced_accuracy": weighted("balanced_accuracy", test_weights),
                "mean_advantage_bps": weighted("moment_advantage_bps_mean", signal_weights),
                "mean_regret_bps": weighted("future_regret_bps_mean", signal_weights),
                "client_advantage_rub_mean": weighted("client_advantage_rub_mean", signal_weights),
                "client_regret_rub_mean": weighted("client_regret_rub_mean", signal_weights),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["hypothesis_id", "horizon_days", "epsilon_bps", "strategy", "lift"],
        ascending=[True, True, True, True, False],
    )


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def dataset_fingerprint(data_dir: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    paths = sorted(data_dir.glob("*.csv"))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()[:16], len(paths)


def concat_nonempty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    useful = [frame for frame in frames if not frame.empty]
    return pd.concat(useful, ignore_index=True) if useful else pd.DataFrame()


def main() -> None:
    args = parse_args()
    data_config = read_toml(args.config_dir / "data.toml")
    feature_config = read_toml(args.config_dir / "features.toml")
    model_config = read_toml(args.config_dir / "models.toml")
    validation_config = read_toml(args.config_dir / "validation.toml")
    configs = {"models": model_config, "validation": validation_config}
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = args.output_root / run_id
    artifact_dir.mkdir(parents=True, exist_ok=False)

    hypothesis_names = [item.strip() for item in args.hypotheses.split(",") if item.strip()]
    requested_horizons = [int(item) for item in args.horizons.split(",") if item.strip()]
    epsilon_values = [int(item) for item in args.epsilon_bps.split(",") if item.strip()] if args.epsilon_bps else [int(data_config["epsilon_bps"])]
    selected_models = {item.strip() for item in args.models.split(",") if item.strip()}
    selected_strategies = {item.strip() for item in args.strategies.split(",") if item.strip()}
    dataset_version, dataset_file_count = dataset_fingerprint(args.data_dir)
    manifest: dict[str, Any] = {
        "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(), "hypotheses": hypothesis_names,
        "horizons": requested_horizons, "epsilon_bps": epsilon_values,
        "models": sorted(selected_models), "strategies": sorted(selected_strategies),
        "dataset_version": dataset_version, "dataset_file_count": dataset_file_count,
        "transfer_amount_rub": args.transfer_amount_rub, "data_config": data_config,
        "feature_config": feature_config, "model_config": model_config,
        "validation_config": validation_config,
        "leakage_controls": [
            "features use current/past values only",
            "auxiliary FX joined backward as-of effective date",
            "horizon-sized purge gap before validation and test",
            "test year unused for hyperparameters and threshold",
            "preprocessing fitted inside each training fold",
        ],
    }

    all_folds: list[dict[str, Any]] = []
    all_thresholds: list[dict[str, Any]] = []
    all_signals: list[pd.DataFrame] = []
    all_predictions: list[pd.DataFrame] = []
    all_models: list[dict[str, Any]] = []
    for name in hypothesis_names:
        hypothesis = read_toml(args.hypotheses_dir / f"{name}.toml")
        features = resolve_feature_columns(feature_config, hypothesis["feature_sets"])
        allowed_models = selected_models.intersection(hypothesis["models"])
        allowed_strategies = selected_strategies.intersection(hypothesis["strategies"])
        for epsilon_bps in epsilon_values:
            for horizon in requested_horizons:
                frames = load_frames(args.data_dir, hypothesis["corridors"], horizon, epsilon_bps, features)
                for strategy in hypothesis["strategies"]:
                    if strategy not in allowed_strategies:
                        continue
                    for model_name in hypothesis["models"]:
                        if model_name not in allowed_models:
                            continue
                        print(f"Running {name} h={horizon} e={epsilon_bps} {strategy} {model_name}", flush=True)
                        folds, thresholds, signals, predictions, models = run_strategy(
                            hypothesis=hypothesis, feature_columns=features, model_name=model_name,
                            strategy=strategy, frames=frames, horizon=horizon, epsilon_bps=epsilon_bps,
                            configs=configs, artifact_dir=artifact_dir, save_models=args.save_models,
                            transfer_amount_rub=args.transfer_amount_rub,
                        )
                        all_folds.extend(folds)
                        all_thresholds.extend(thresholds)
                        all_signals.extend(signals)
                        all_predictions.extend(predictions)
                        all_models.extend(models)

    folds = pd.DataFrame(all_folds)
    if folds.empty:
        raise RuntimeError("No valid folds were produced")
    summary = summarize(folds)
    folds.to_csv(artifact_dir / "fold_metrics.csv", index=False)
    summary.to_csv(artifact_dir / "summary.csv", index=False)
    pd.DataFrame(all_thresholds).to_csv(artifact_dir / "thresholds.csv", index=False)
    pd.DataFrame(all_models).to_csv(artifact_dir / "models.csv", index=False)
    concat_nonempty(all_predictions).to_csv(artifact_dir / "predictions.csv", index=False)
    concat_nonempty(all_signals).to_csv(artifact_dir / "signals.csv", index=False)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["fold_rows"] = len(folds)
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nTop results:")
    print(summary.sort_values("lift", ascending=False).head(30).to_string(index=False))
    print(f"\nArtifacts: {artifact_dir}")


if __name__ == "__main__":
    main()
