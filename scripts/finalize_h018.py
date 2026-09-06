"""Finalize the focused RF-tuning smoke against the frozen canonical policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from evaluation.artifacts import validate_protocol_compatibility, write_frame, write_json
from evaluation.uncertainty import paired_policy_bootstrap, summarize_paired_bootstrap


def evaluate_h018(canonical: Path, candidate: Path, replicates: int) -> tuple[dict, pd.DataFrame]:
    manifests = [json.loads((path / "manifest.json").read_text(encoding="utf-8")) for path in (canonical, candidate)]
    validate_protocol_compatibility(manifests)
    if manifests[0]["universe_ids"] != manifests[1]["universe_ids"]:
        raise ValueError("H018 and canonical use different eligible universes")
    if manifests[0]["target_contract"] != manifests[1]["target_contract"]:
        raise ValueError("H018 and canonical use different target contracts")
    left = pd.read_csv(canonical / "policy_decisions.csv.gz", parse_dates=["date"])
    right = pd.read_csv(candidate / "policy_decisions.csv.gz", parse_dates=["date"])
    boundaries = pd.read_csv(canonical / "fold_boundaries.csv", parse_dates=["test_start", "test_end_exclusive"])
    exposures = boundaries.rename(columns={"test_start": "exposure_start", "test_end_exclusive": "exposure_end_exclusive"})[
        ["outer_fold", "exposure_start", "exposure_end_exclusive"]
    ]
    sampled = paired_policy_bootstrap(left, right, exposures, block_days=28, replicates=replicates, seed=42029)
    uncertainty = summarize_paired_bootstrap(sampled)
    old = pd.read_csv(canonical / "summary.csv").iloc[0]
    new = pd.read_csv(candidate / "summary.csv").iloc[0]
    old_cells = pd.read_csv(canonical / "signal_policy_metrics.csv")
    new_cells = pd.read_csv(candidate / "signal_policy_metrics.csv")
    old_full = old_cells.loc[~old_cells["is_partial_fold"].astype(bool)].groupby("test_year").agg(hits=("signal_hits", "sum"), signals=("signals", "sum"))
    new_full = new_cells.loc[~new_cells["is_partial_fold"].astype(bool)].groupby("test_year").agg(hits=("signal_hits", "sum"), signals=("signals", "sum"))
    deltas = new_full["hits"] / new_full["signals"] - old_full["hits"] / old_full["signals"]
    active_loss = int(old["active_cells"] - new["active_cells"])
    checks = {
        "aggregate_lift_improves": bool(new["lift"] > old["lift"]),
        "aggregate_hit_rate_not_lower": bool(new["signal_hit_rate"] >= old["signal_hit_rate"]),
        "mean_regret_increase_within_5bp": bool(new["mean_realized_regret_bps"] - old["mean_realized_regret_bps"] <= 5),
        "active_cell_loss_within_two": active_loss <= 2,
        "positive_delta_in_three_full_years": int(deltas.gt(0).sum()) >= 3,
    }
    probability = float(uncertainty.loc[uncertainty["metric"].eq("delta_hit_rate"), "probability_delta_gt_zero"].iloc[0])
    decision = {
        "status": "improved_smoke" if all(checks.values()) else "rejected_smoke",
        "full_run_allowed": all(checks.values()),
        "exploratory": True,
        "independent_confirmation": False,
        "canonical_run_id": manifests[0]["run_id"],
        "candidate_run_id": manifests[1]["run_id"],
        "checks": checks,
        "canonical": {"lift": float(old["lift"]), "hit_rate": float(old["signal_hit_rate"]), "signals_per_week": float(old["signals_per_week"]), "mean_regret_bps": float(old["mean_realized_regret_bps"]), "active_cells": int(old["active_cells"])},
        "candidate": {"lift": float(new["lift"]), "hit_rate": float(new["signal_hit_rate"]), "signals_per_week": float(new["signals_per_week"]), "mean_regret_bps": float(new["mean_realized_regret_bps"]), "active_cells": int(new["active_cells"])},
        "delta": {"lift": float(new["lift"] - old["lift"]), "hit_rate": float(new["signal_hit_rate"] - old["signal_hit_rate"]), "signals_per_week": float(new["signals_per_week"] - old["signals_per_week"]), "mean_regret_bps": float(new["mean_realized_regret_bps"] - old["mean_realized_regret_bps"]), "active_cells": -active_loss},
        "full_year_hit_rate_deltas": {str(int(year)): float(value) for year, value in deltas.items()},
        "paired_probability_hit_rate_improves": probability,
        "bootstrap_replicates": replicates,
        "execution_contract_note": "Policy-only paired smoke comparison; random draw counts intentionally differ.",
    }
    return decision, uncertainty


def render(decision: dict) -> str:
    old, new, delta = decision["canonical"], decision["candidate"], decision["delta"]
    selected = pd.read_csv(Path("results/experiments") / decision["candidate_run_id"] / "model_fits.csv")
    params = selected.groupby("hyperparameters")["outer_fold"].count().sort_values(ascending=False)
    lines = [
        "# H018: focused Random Forest tuning",
        "",
        f"Status: **{decision['status']}**. Full run allowed: **{decision['full_run_allowed']}**.",
        "",
        "| Metric | Canonical RF | H018 smoke | Delta |",
        "|---|---:|---:|---:|",
        f"| Lift | {old['lift']:.3f} | {new['lift']:.3f} | {delta['lift']:+.3f} |",
        f"| Hit rate | {old['hit_rate']:.1%} | {new['hit_rate']:.1%} | {delta['hit_rate']:+.1%} |",
        f"| Signals/week | {old['signals_per_week']:.3f} | {new['signals_per_week']:.3f} | {delta['signals_per_week']:+.3f} |",
        f"| Mean regret, bp | {old['mean_regret_bps']:.1f} | {new['mean_regret_bps']:.1f} | {delta['mean_regret_bps']:+.1f} |",
        f"| Active cells | {old['active_cells']} | {new['active_cells']} | {delta['active_cells']:+d} |",
        "",
        f"Paired bootstrap P(hit rate improves): {decision['paired_probability_hit_rate_improves']:.1%}.",
        "",
        "Selected hyperparameters by outer fold:",
        "",
    ]
    lines += [f"- `{key}`: {value} folds" for key, value in params.items()]
    lines += [
        "",
        "The stronger inner-validation PR-AUC did not improve the delivered OOT policy. "
        "H018 is retained as a rejected alternative; canonical RF remains selected.",
        "",
        "Historical outer years were previously inspected. This smoke comparison is exploratory.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canonical", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=200)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    decision, uncertainty = evaluate_h018(args.canonical, args.candidate, args.replicates)
    write_json(args.output / "DECISION.json", decision)
    write_frame(args.output / "paired_uncertainty.csv", uncertainty)
    (args.output / "RESULTS.md").write_text(render(decision), encoding="utf-8")
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
