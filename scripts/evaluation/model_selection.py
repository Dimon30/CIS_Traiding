"""Nested temporal hyperparameter selection for protocol v3."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .contracts import InnerFoldSpec
from .temporal import slice_role


@dataclass(frozen=True)
class ModelSelectionResult:
    hyperparameters: dict[str, Any]
    mean_pr_auc_gain: float
    worst_year_pr_auc_gain: float
    mean_roc_auc: float
    inner_fold_count: int


def add_corridor_columns(frame: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    values = pd.Categorical(frame["corridor"], categories=categories)
    return pd.get_dummies(values, prefix="corridor", dtype=float)


def design_matrix(
    frame: pd.DataFrame,
    feature_columns: list[str],
    *,
    include_corridor_feature: bool,
    corridor_categories: list[str],
) -> pd.DataFrame:
    matrix = frame[feature_columns].reset_index(drop=True).astype(float)
    if include_corridor_feature:
        corridor = add_corridor_columns(frame, corridor_categories).reset_index(drop=True)
        matrix = pd.concat([matrix, corridor], axis=1)
    return matrix.replace([np.inf, -np.inf], np.nan)


def make_estimator(
    model_name: str,
    params: dict[str, Any],
    fixed: dict[str, Any],
) -> Pipeline:
    scale = False
    if model_name == "logistic":
        params = {key: (None if value == "none" else value) for key, value in params.items()}
        model = LogisticRegression(**fixed, **params)
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


def _cell_metrics(frame: pd.DataFrame, scores: np.ndarray) -> list[dict[str, object]]:
    scored = frame[["corridor", "message_hit"]].copy()
    scored["score"] = scores
    rows: list[dict[str, object]] = []
    for corridor, group in scored.groupby("corridor", observed=True):
        target = group["message_hit"].astype(int)
        if target.nunique() < 2:
            continue
        ap = float(average_precision_score(target, group["score"]))
        prevalence = float(target.mean())
        rows.append(
            {
                "corridor": corridor,
                "pr_auc": ap,
                "pr_auc_gain": ap - prevalence,
                "roc_auc": float(roc_auc_score(target, group["score"])),
            }
        )
    return rows


def select_hyperparameters_temporal(
    frame: pd.DataFrame,
    inner_folds: Iterable[InnerFoldSpec],
    *,
    model_name: str,
    model_definition: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
    feature_columns: list[str],
    include_corridor_feature: bool,
    corridor_categories: list[str],
    minimum_train_rows_per_corridor: int,
    minimum_validation_rows_per_corridor: int,
) -> tuple[ModelSelectionResult, pd.DataFrame]:
    records: list[dict[str, object]] = []
    candidate_list = list(candidates)
    for candidate_index, params in enumerate(candidate_list):
        for inner in inner_folds:
            train = slice_role(frame, inner.train)
            validation = slice_role(frame, inner.validation)
            train_counts = train.groupby("corridor", observed=True).size()
            validation_counts = validation.groupby("corridor", observed=True).size()
            required = set(corridor_categories)
            if any(train_counts.get(item, 0) < minimum_train_rows_per_corridor for item in required):
                continue
            if any(validation_counts.get(item, 0) < minimum_validation_rows_per_corridor for item in required):
                continue
            if train["message_hit"].nunique() < 2:
                continue
            x_train = design_matrix(
                train,
                feature_columns,
                include_corridor_feature=include_corridor_feature,
                corridor_categories=corridor_categories,
            )
            x_validation = design_matrix(
                validation,
                feature_columns,
                include_corridor_feature=include_corridor_feature,
                corridor_categories=corridor_categories,
            ).reindex(columns=x_train.columns, fill_value=0)
            fitted = make_estimator(
                model_name, params, model_definition.get("fixed", {})
            ).fit(x_train, train["message_hit"].astype(int))
            scores = fitted.predict_proba(x_validation)[:, 1]
            for cell in _cell_metrics(validation, scores):
                records.append(
                    {
                        "candidate_index": candidate_index,
                        "hyperparameters": json.dumps(params, sort_keys=True),
                        "validation_year": inner.validation_year,
                        **cell,
                    }
                )
    metrics = pd.DataFrame(records)
    if metrics.empty:
        raise RuntimeError("No valid inner temporal model-selection folds")
    summaries: list[dict[str, object]] = []
    for candidate_index, group in metrics.groupby("candidate_index"):
        yearly = group.groupby("validation_year")["pr_auc_gain"].mean()
        summaries.append(
            {
                "candidate_index": int(candidate_index),
                "mean_pr_auc_gain": float(group["pr_auc_gain"].mean()),
                "worst_year_pr_auc_gain": float(yearly.min()),
                "mean_roc_auc": float(group["roc_auc"].mean()),
                "inner_fold_count": int(group["validation_year"].nunique()),
            }
        )
    summary = pd.DataFrame(summaries).sort_values(
        ["mean_pr_auc_gain", "worst_year_pr_auc_gain", "mean_roc_auc", "candidate_index"],
        ascending=[False, False, False, True],
        kind="stable",
    )
    best = summary.iloc[0]
    best_index = int(best["candidate_index"])
    return (
        ModelSelectionResult(
            hyperparameters=candidate_list[best_index],
            mean_pr_auc_gain=float(best["mean_pr_auc_gain"]),
            worst_year_pr_auc_gain=float(best["worst_year_pr_auc_gain"]),
            mean_roc_auc=float(best["mean_roc_auc"]),
            inner_fold_count=int(best["inner_fold_count"]),
        ),
        metrics,
    )


def refit_selected_model(
    frame: pd.DataFrame,
    *,
    model_name: str,
    model_definition: dict[str, Any],
    hyperparameters: dict[str, Any],
    feature_columns: list[str],
    include_corridor_feature: bool,
    corridor_categories: list[str],
) -> tuple[Pipeline, list[str]]:
    matrix = design_matrix(
        frame,
        feature_columns,
        include_corridor_feature=include_corridor_feature,
        corridor_categories=corridor_categories,
    )
    model = make_estimator(
        model_name, hyperparameters, model_definition.get("fixed", {})
    ).fit(matrix, frame["message_hit"].astype(int))
    return model, list(matrix.columns)
