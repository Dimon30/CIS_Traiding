"""Apply the preregistered ten-day gates and publish the final ML decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.audit import audit_result_bundle
from evaluation.comparison import load_compatible_runs


FULL_OUTER_YEARS = (2022, 2023, 2024, 2025)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--catboost", type=Path, required=True)
    parser.add_argument("--h015", type=Path, required=True)
    parser.add_argument("--rf-catboost-comparison", type=Path, required=True)
    parser.add_argument("--rf-h015-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def _summary(path: Path) -> dict[str, Any]:
    return pd.read_csv(path / "summary.csv").iloc[0].to_dict()


def _metric(comparison: Path, name: str) -> dict[str, Any]:
    frame = pd.read_csv(comparison / "paired_comparisons.csv")
    return frame.loc[frame["metric"].eq(name)].iloc[0].to_dict()


def _probability_regret_decreases(comparison: Path) -> float:
    replicates = pd.read_csv(comparison / "paired_bootstrap_replicates.csv.gz")
    return float(replicates["delta_mean_regret_bps"].lt(0).mean())


def _active_cells(path: Path) -> tuple[int, dict[int, int]]:
    frame = pd.read_csv(path / "corridor_year_metrics.csv")
    active = frame["signals"].fillna(0).gt(0)
    by_year = (
        frame.assign(active=active)
        .groupby("test_year", observed=True)["active"]
        .sum()
        .astype(int)
        .to_dict()
    )
    return int(active.sum()), {int(year): int(count) for year, count in by_year.items()}


def _frontier_majority(comparison: Path) -> tuple[bool, int, int]:
    common = pd.read_csv(comparison / "policy_frontier_common_count.csv")
    aligned = pd.read_csv(comparison / "policy_frontier_comparison.csv")
    keys = ["outer_fold", "corridor"]
    budgets = aligned[[*keys, "requested_signals_per_week"]].copy()
    budgets["frontier_point_id"] = (
        budgets.groupby(keys, observed=True).cumcount().map(lambda value: f"budget_{value:02d}")
    )
    evaluated = common.merge(budgets, on=[*keys, "frontier_point_id"], how="left")
    evaluated = evaluated.loc[
        evaluated["comparison_status"].eq("active")
        & evaluated["requested_signals_per_week"].between(0.25, 1.25)
    ]
    wins = int(
        (
            evaluated["delta_hit_rate"].gt(0)
            | (
                evaluated["delta_hit_rate"].eq(0)
                & evaluated["delta_mean_regret_bps"].lt(0)
            )
        ).sum()
    )
    total = len(evaluated)
    return bool(total and wins > total / 2), wins, total


def _year_hit_deltas(left: Path, right: Path) -> dict[int, float]:
    def rates(path: Path) -> pd.Series:
        frame = pd.read_csv(path / "policy_decisions.csv.gz")
        selected = frame.loc[frame["selected_signal"].astype(str).str.lower().isin({"true", "1"})]
        return selected.groupby("test_year", observed=True)["message_hit"].mean()

    delta = rates(right).subtract(rates(left))
    return {
        year: float(delta.get(year, float("nan")))
        for year in FULL_OUTER_YEARS
    }


def _candidate_gate(
    baseline: Path,
    candidate: Path,
    comparison: Path,
    *,
    require_frontier_majority: bool,
    require_three_positive_years: bool,
) -> dict[str, Any]:
    hit = _metric(comparison, "delta_hit_rate")
    p_hit = float(hit["probability_delta_gt_zero"])
    p_regret = _probability_regret_decreases(comparison)
    baseline_cells, _ = _active_cells(baseline)
    candidate_cells, active_by_year = _active_cells(candidate)
    cell_loss = baseline_cells - candidate_cells
    all_full_years_active = all(active_by_year.get(year, 0) > 0 for year in FULL_OUTER_YEARS)
    frontier_pass, frontier_wins, frontier_total = _frontier_majority(comparison)
    year_deltas = _year_hit_deltas(baseline, candidate)
    positive_years = sum(value > 0 for value in year_deltas.values())
    checks = {
        "paired_probability_hit_rate_improves": p_hit >= 0.90,
        "paired_probability_mean_regret_decreases": p_regret >= 0.80,
        "active_cell_loss_within_two": cell_loss <= 2,
        "every_full_outer_year_active": all_full_years_active,
    }
    if require_frontier_majority:
        checks["common_count_frontier_majority"] = frontier_pass
    if require_three_positive_years:
        checks["positive_hit_rate_delta_in_three_full_years"] = positive_years >= 3
    return {
        "accepted": all(checks.values()),
        "checks": checks,
        "p_delta_hit_rate_gt_zero": p_hit,
        "p_delta_mean_regret_bps_lt_zero": p_regret,
        "delta_hit_rate": float(hit["estimate"]),
        "delta_mean_regret_bps": float(_metric(comparison, "delta_mean_regret_bps")["estimate"]),
        "active_cell_loss": cell_loss,
        "active_cells": candidate_cells,
        "active_cells_by_year": active_by_year,
        "frontier_wins": frontier_wins,
        "frontier_active_points": frontier_total,
        "full_year_hit_rate_deltas": year_deltas,
        "positive_full_years": positive_years,
    }


def _annual_lifts(path: Path) -> dict[int, float]:
    frame = pd.read_csv(path / "corridor_year_metrics.csv")
    rows: dict[int, float] = {}
    for year, group in frame.loc[frame["test_year"].isin(FULL_OUTER_YEARS)].groupby("test_year"):
        signals = float(group["signals"].sum())
        hits = float(group["signal_hits"].sum())
        random_hits = float((group["matched_random_hit_rate"].fillna(0) * group["signals"]).sum())
        rows[int(year)] = (hits / signals) / (random_hits / signals) if random_hits else float("nan")
    return rows


def _lift_probability(path: Path) -> float:
    frame = pd.read_csv(path / "uncertainty_summary.csv")
    row = frame.loc[
        frame["metric"].eq("lift")
        & frame["evaluation_view"].eq("all_folds")
        & frame["block_length_days"].eq(28)
    ].iloc[0]
    return float(row["probability_lift_ge_1_3"])


def main() -> None:
    args = parse_args()
    run_paths = {
        "rf_baseline": args.baseline,
        "catboost": args.catboost,
        "h015": args.h015,
    }
    audits = {name: audit_result_bundle(path) for name, path in run_paths.items()}
    manifests = {name: _manifest(path) for name, path in run_paths.items()}
    load_compatible_runs(args.baseline, args.catboost)
    load_compatible_runs(args.baseline, args.h015)
    reproducible = all(item.get("canonical_eligible") is True for item in manifests.values())

    cat_gate = _candidate_gate(
        args.baseline,
        args.catboost,
        args.rf_catboost_comparison,
        require_frontier_majority=True,
        require_three_positive_years=False,
    )
    model_winner = "catboost" if cat_gate["accepted"] else "rf_baseline"
    if model_winner != "rf_baseline":
        raise ValueError("H015 is not an exact-model ablation of the accepted CatBoost winner")
    h015_gate = _candidate_gate(
        args.baseline,
        args.h015,
        args.rf_h015_comparison,
        require_frontier_majority=False,
        require_three_positive_years=True,
    )
    selected_key = "h015" if h015_gate["accepted"] else model_winner
    selected_path = run_paths[selected_key]
    selected_manifest = manifests[selected_key]
    selected_summary = _summary(selected_path)
    annual_lifts = _annual_lifts(selected_path)
    probability_lift = _lift_probability(selected_path)
    _, active_by_year = _active_cells(selected_path)
    multiple_corridors = max(active_by_year.values(), default=0) >= 2

    if not reproducible:
        status = "EVALUATION_BLOCKED"
    elif float(selected_summary["lift"]) < 1.3:
        status = "CRITERION_NOT_MET"
    elif (
        all(annual_lifts.get(year, float("-inf")) >= 1.3 for year in FULL_OUTER_YEARS)
        and multiple_corridors
        and probability_lift >= 0.95
    ):
        status = "OFFLINE_CRITERION_MET"
    else:
        status = "PROMISING_NOT_PROVEN"

    decision = {
        "status": status,
        "selected_run_id": selected_manifest["run_id"],
        "model": selected_manifest["models"][0],
        "feature_sets": selected_manifest["hypothesis"]["feature_sets"],
        "aggregate": {
            "lift": float(selected_summary["lift"]),
            "signal_hit_rate": float(selected_summary["signal_hit_rate"]),
            "matched_random_hit_rate": float(selected_summary["matched_random_hit_rate"]),
            "signals_per_week": float(selected_summary["signals_per_week"]),
            "mean_regret_bps": float(selected_summary["mean_realized_regret_bps"]),
            "p90_regret_bps": float(selected_summary["p90_realized_regret_bps"]),
            "probability_lift_ge_1_3": probability_lift,
        },
        "full_outer_year_lifts": annual_lifts,
        "candidate_gates": {"catboost": cat_gate, "h015": h015_gate},
        "audits": audits,
        "canonical_eligible": reproducible,
        "stop_program": True,
        "reasons": [
            "CatBoost accepted by all preregistered gates." if cat_gate["accepted"] else "CatBoost rejected: at least one preregistered gate failed.",
            "H015 accepted by all preregistered gates." if h015_gate["accepted"] else "H015 rejected: at least one preregistered gate failed.",
            f"Final aggregate lift is {float(selected_summary['lift']):.3f}.",
        ],
    }

    args.output.mkdir(parents=True, exist_ok=True)
    decision_path = args.output / "DECISION.json"
    results_path = args.output / "FINAL_RESULTS.md"
    if decision_path.exists() or results_path.exists():
        raise FileExistsError("Refusing to overwrite an existing ten-day decision")
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summaries = {name: _summary(path) for name, path in run_paths.items()}
    table = [
        "| Run | Model/features | Lift | Hit rate | Random | Signals/week | Mean regret bp | p90 regret bp |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in summaries.items():
        manifest = manifests[name]
        table.append(
            f"| `{manifest['run_id']}` | {manifest['models'][0]} / "
            f"{'+'.join(manifest['hypothesis']['feature_sets'])} | {summary['lift']:.3f} | "
            f"{summary['signal_hit_rate']:.3f} | {summary['matched_random_hit_rate']:.3f} | "
            f"{summary['signals_per_week']:.3f} | {summary['mean_realized_regret_bps']:.1f} | "
            f"{summary['p90_realized_regret_bps']:.1f} |"
        )
    year_text = ", ".join(f"{year}: {value:.3f}" for year, value in annual_lifts.items())
    report = "\n".join(
        [
            "# CIS Trading: итог 10-дневной ML-программы",
            "",
            f"**Статус: `{status}`.** Выбран run `{selected_manifest['run_id']}`.",
            "",
            "Все три full bundles прошли `audit_evaluation_v3.py` и имеют "
            f"`canonical_eligible=true`: **{reproducible}**.",
            "",
            "## Основные результаты",
            "",
            *table,
            "",
            "## Model-control и feature-ablation",
            "",
            f"- CatBoost: accepted={cat_gate['accepted']}; delta hit rate "
            f"{cat_gate['delta_hit_rate']:.4f}; P(improves) "
            f"{cat_gate['p_delta_hit_rate_gt_zero']:.3f}; delta mean regret "
            f"{cat_gate['delta_mean_regret_bps']:.2f} bp; frontier wins "
            f"{cat_gate['frontier_wins']}/{cat_gate['frontier_active_points']}.",
            f"- H015: accepted={h015_gate['accepted']}; delta hit rate "
            f"{h015_gate['delta_hit_rate']:.4f}; P(improves) "
            f"{h015_gate['p_delta_hit_rate_gt_zero']:.3f}; delta mean regret "
            f"{h015_gate['delta_mean_regret_bps']:.2f} bp; positive full years "
            f"{h015_gate['positive_full_years']}/4.",
            "",
            "## Финальный offline-критерий",
            "",
            f"Aggregate lift: **{selected_summary['lift']:.3f}**; full-year lifts: "
            f"{year_text}; bootstrap P(lift >= 1.3): **{probability_lift:.3f}**.",
            "",
            "Результат относится к proxy-курсам ЦБ РФ и не доказывает выгоду по "
            "историческим банковским курсам или влияние пушей на доверие клиентов.",
            "",
            "Программа остановлена согласно timebox; deferred backlog автоматически не запускается.",
        ]
    )
    results_path.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
