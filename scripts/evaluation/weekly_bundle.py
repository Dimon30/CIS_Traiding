"""Version-4 policy artifacts, random controls and exploratory acceptance."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import write_frame, write_json, sha256_file
from .audit import audit_continuous_schedules
from .metrics import signal_metrics, aggregate_signal_metrics
from .policy import enumerate_policy_points, map_thresholds_to_frequency_budgets, SelectedPolicy, thin_to_common_count
from .random_baseline import draw_metrics, summarize_draw_metrics, schedule_quotas
from .uncertainty import model_vs_random_bootstrap, summarize_model_vs_random_bootstrap, paired_policy_bootstrap, summarize_paired_bootstrap
from .weekly import DeliveryState, quality_points, select_weekly_policy, continuous_draws, baseline_frames, cadence


class WeeklyBundle:
    def __init__(self, config: dict, smoke: bool):
        self.config, self.smoke = config, smoke
        self.state = DeliveryState()
        self.decisions, self.points, self.policies, self.scores, self.policy_scores, self.exposures = [], [], [], [], [], []

    def add_fold(self, policy_block, test, fold, identity):
        config = self.config["policy"]
        self.exposures.append({"outer_fold": fold.fold_id, "exposure_start": fold.outer_test.start,
                               "exposure_end_exclusive": fold.outer_test.end_exclusive,
                               "is_partial_fold": fold.is_partial_fold})
        self.scores.append(test.assign(**identity))
        self.policy_scores.append(policy_block.assign(**identity))
        for corridor, group in policy_block.groupby("corridor", observed=True):
            print(f"[weekly_v4] {fold.fold_id} {corridor}: quality policy", flush=True)
            exposure = (fold.outer_test.start - fold.policy.start).days / 7
            points = quality_points(group, exposure, config)
            self.points.append(points.assign(**identity, corridor=corridor))
            variants = {"operating": select_weekly_policy(points, config["hard_max_signals_per_week"])}
            for index, budget in enumerate(config["frequency_grid"]):
                variants[f"budget_{index:02d}"] = select_weekly_policy(points, float(budget))
            # A prespecified ungated RF frequency control chosen on policy only.
            raw_points = enumerate_policy_points(group, cooldown_days=config["cooldown_days"], exposure_weeks=exposure)
            control = map_thresholds_to_frequency_budgets(raw_points, [1.0]).iloc[0]
            variants["rf_frequency_control"] = SelectedPolicy(float(control["threshold"]), "active")
            test_group = test.loc[test["corridor"].eq(corridor)]
            for variant, policy in variants.items():
                decision = self.state.apply(test_group, policy, variant, config["cooldown_days"], gated=variant != "rf_frequency_control")
                self.decisions.append(decision.assign(**identity, variant=variant))
                self.policies.append({**identity, "corridor": corridor, "variant": variant,
                                      "threshold": policy.threshold, "policy_status": policy.status,
                                      "inactive_reason": policy.inactive_reason})

    def finish(self, output: Path, manifest: dict) -> Path:
        decisions = pd.concat(self.decisions, ignore_index=True)
        exposures = pd.DataFrame(self.exposures).drop_duplicates("outer_fold")
        operating = decisions.loc[decisions["variant"].eq("operating")].copy()
        write_frame(output / "oot_scores.csv.gz", pd.concat(self.scores, ignore_index=True))
        write_frame(output / "policy_scores.csv.gz", pd.concat(self.policy_scores, ignore_index=True))
        write_frame(output / "candidate_policy_metrics.csv", pd.concat(self.points, ignore_index=True))
        write_frame(output / "selected_policies.csv", pd.DataFrame(self.policies))
        write_frame(output / "policy_decisions.csv.gz", operating)
        write_frame(output / "frontier_decisions.csv.gz", decisions.loc[~decisions["variant"].eq("operating")])
        write_frame(output / "exposures.csv", exposures)
        return evaluate_weekly_decisions(output, manifest, decisions, exposures, self.smoke)


def evaluate_weekly_decisions(output, manifest, decisions, exposures, smoke):
    config = manifest["config"]
    cooldown = int(config["policy"]["cooldown_days"])
    repeats = int(config["random"]["smoke_draws" if smoke else "draws"])
    bootstrap_repeats = int(config["bootstrap"]["smoke_replicates" if smoke else "replicates"])
    modes = [config["random"]["primary_stratification"], *config["random"]["sensitivity_stratifications"]]
    cells, schedules, draw_rows, uncertainty, baseline_summary = [], [], [], [], []
    universe_id = manifest["universe_ids"]["all_corridors"]
    for (variant, corridor), group in decisions.groupby(["variant", "corridor"], observed=True):
        delivered = group.loc[group["selected_signal"]]
        # Frontier streams get their own random schedules; three baselines apply to operating.
        baselines = ["future_safety", "product", "conditional"] if variant == "operating" else (["future_safety"] if variant == "rf_frequency_control" else [])
        for baseline in baselines:
            universe, universe_kind, outcome_id = baseline_frames(group, baseline)
            baseline_universe_id = f"{universe_id}:{universe_kind}"
            outcome_schedule = universe.loc[universe["selected_signal"]]
            for mode in modes if variant == "operating" else modes[:1]:
                print(f"[weekly_v4] random {corridor} {variant} {baseline} {mode}", flush=True)
                random = continuous_draws(universe, outcome_schedule, mode=mode, draws=repeats,
                    seed=config["random"]["seed"], cooldown_days=cooldown,
                    stream_id=f"{universe_id}:{corridor}:{variant}:{baseline}")
                tags = {"variant": variant, "corridor": corridor, "baseline": baseline,
                        "random_mode": mode, "universe_id": baseline_universe_id, "outcome_id": outcome_id}
                random = random.assign(**tags)
                if len(random):
                    # Assert complete quota equality, including absence of extra strata.
                    for _, draw in random.groupby("draw_id", observed=True):
                        for fold_id, original in outcome_schedule.groupby("outer_fold", observed=True):
                            if schedule_quotas(draw.loc[draw["outer_fold"].eq(fold_id)], mode) != schedule_quotas(original, mode):
                                raise AssertionError("Random quotas differ")
                    schedules.append(random)
                    metrics = draw_metrics(draw for _, draw in random.groupby("draw_id", observed=True)).assign(**tags)
                    draw_rows.append(metrics)
                    summary = summarize_draw_metrics(metrics)
                    baseline_summary.append({**tags, **summary,
                        "model_hit_rate": outcome_schedule["message_hit"].mean(),
                        "delta_hit_rate": outcome_schedule["message_hit"].mean() - summary["random_hit_rate"],
                        "lift": outcome_schedule["message_hit"].mean() / summary["random_hit_rate"] if summary["random_hit_rate"] else np.nan,
                        "random_mean_regret_bps": metrics["future_regret_bps_mean"].mean(),
                        "random_p90_regret_bps": metrics["future_regret_bps_p90"].mean()})
                    if variant == "operating":
                        boot = model_vs_random_bootstrap(universe, random, exposures,
                            block_days=config["bootstrap"]["primary_block_days"], replicates=bootstrap_repeats,
                            seed=config["bootstrap"]["seed"])
                        uncertainty.append(summarize_model_vs_random_bootstrap(boot).assign(**tags))
                if baseline == "future_safety" and mode == modes[0]:
                    for fold_id, fold_group in group.groupby("outer_fold", observed=True):
                        dates = exposures.loc[exposures["outer_fold"].eq(fold_id)].iloc[0]
                        fold_random = random.loc[random["outer_fold"].eq(fold_id)]
                        rates = fold_random.groupby("draw_id", observed=True)["message_hit"].mean()
                        metric = signal_metrics(fold_group, exposure_start=dates["exposure_start"],
                            exposure_end_exclusive=dates["exposure_end_exclusive"],
                            random_hit_rate=rates.mean(), cooldown_days=cooldown)
                        cells.append({"variant": variant, "corridor": corridor, "outer_fold": fold_id,
                                      "is_partial_fold": dates["is_partial_fold"], **metric})
        if not baselines:
            for fold_id, fold_group in group.groupby("outer_fold", observed=True):
                dates = exposures.loc[exposures["outer_fold"].eq(fold_id)].iloc[0]
                metric = signal_metrics(fold_group, exposure_start=dates["exposure_start"],
                    exposure_end_exclusive=dates["exposure_end_exclusive"], cooldown_days=cooldown)
                cells.append({"variant": variant, "corridor": corridor, "outer_fold": fold_id,
                              "is_partial_fold": dates["is_partial_fold"], **metric})
    random_all = pd.concat(schedules, ignore_index=True) if schedules else decisions.head(0).assign(draw_id=pd.Series(dtype=int))
    audit = audit_continuous_schedules(decisions, random_all, cooldown)
    cells = pd.DataFrame(cells)
    summarized_cells = cells.loc[cells["variant"].isin(["operating", "rf_frequency_control"])]
    summaries = pd.DataFrame([{"variant": variant, **aggregate_signal_metrics(group)} for variant, group in summarized_cells.groupby("variant", observed=True)])
    operating = decisions.loc[decisions["variant"].eq("operating")]
    start, end = exposures["exposure_start"].min(), exposures["exposure_end_exclusive"].max()
    cadences = []
    comparisons = []
    baseline_table = pd.DataFrame(baseline_summary)
    for corridor, group in operating.groupby("corridor", observed=True):
        row = {"corridor": corridor, **cadence(group, start, end)}
        full = cells.loc[cells["variant"].eq("operating") & cells["corridor"].eq(corridor) & ~cells["is_partial_fold"].astype(bool)]
        row["every_full_year_active"] = bool(len(full) and full["signals"].gt(0).all())
        row["direction_pass"] = bool(.8 <= row["signals_per_week"] <= 1.0 and row["every_full_year_active"]
            and row["inter_signal_gap_days_median"] <= 10 and row["inter_signal_gap_days_p90"] <= 14
            and row["longest_no_signal_gap_days"] <= 28 and row["active_week_share"] >= .7
            and row["signal_hit_rate"] >= .75 and row["mean_regret_bps"] <= 40 and row["p90_regret_bps"] <= 100)
        control = decisions.loc[decisions["variant"].eq("rf_frequency_control") & decisions["corridor"].eq(corridor)]
        # Equal realized counts per fold; thinning uses frozen scores, never outcomes.
        paired_model, paired_control = [], []
        for fold_id, model_fold in group.groupby("outer_fold", observed=True):
            control_fold = control.loc[control["outer_fold"].eq(fold_id)]
            n = min(int(model_fold["selected_signal"].sum()), int(control_fold["selected_signal"].sum()))
            for frame, destination in ((model_fold, paired_model), (control_fold, paired_control)):
                selected = thin_to_common_count(frame, n)
                destination.append(frame.assign(selected_signal=frame.index.isin(selected.index)))
        left, right = pd.concat(paired_model), pd.concat(paired_control)
        ls, rs = left.loc[left["selected_signal"]], right.loc[right["selected_signal"]]
        comparison = {"corridor": corridor, "common_count": len(ls),
            "model_original_count": int(group["selected_signal"].sum()),
            "control_covers_model_count": len(ls) == int(group["selected_signal"].sum()),
            "delta_safety": ls["message_hit"].mean() - rs["message_hit"].mean(),
            "delta_mean_regret_bps": ls["future_regret_bps"].mean() - rs["future_regret_bps"].mean(),
            "delta_p90_regret_bps": ls["future_regret_bps"].quantile(.9) - rs["future_regret_bps"].quantile(.9)}
        comparisons.append(comparison)
        row["control_pass"] = bool(comparison["control_covers_model_count"] and comparison["delta_safety"] >= -.05 and comparison["delta_mean_regret_bps"] <= 10 and comparison["delta_p90_regret_bps"] <= 25)
        conditional = baseline_table.loc[baseline_table["corridor"].eq(corridor) & baseline_table["baseline"].eq("conditional") & baseline_table["random_mode"].eq(modes[0])] if len(baseline_table) else pd.DataFrame()
        row["conditional_value_pass"] = bool(len(conditional) and conditional["delta_hit_rate"].iloc[0] > 0)
        row["acceptance_pass"] = row["direction_pass"] and row["control_pass"] and row["conditional_value_pass"]
        cadences.append(row)
        if len(ls):
            paired = paired_policy_bootstrap(right, left, exposures, block_days=config["bootstrap"]["primary_block_days"], replicates=bootstrap_repeats, seed=config["bootstrap"]["seed"])
            uncertainty.append(summarize_paired_bootstrap(paired).assign(corridor=corridor, baseline="rf_equal_count", variant="operating"))
    passed = [row["corridor"] for row in cadences if row["acceptance_pass"]]
    decision = {"status": "exploratory_pass" if len(passed) == len(cadences) else "limited" if passed else "failed",
                "accepted_corridors": passed, "full_monte_carlo_allowed": any(row["direction_pass"] for row in cadences),
                "independent_confirmation": False, "policy_frozen": True, "confirmation_after_cutoff": manifest.get("data_cutoff")}
    for name, frame in {"signal_policy_metrics.csv": cells, "summary.csv": summaries,
        "cadence_metrics.csv": pd.DataFrame(cadences), "equal_count_control.csv": pd.DataFrame(comparisons),
        "baseline_summary.csv": baseline_table, "random_schedules.csv.gz": random_all,
        "random_draw_metrics.csv.gz": pd.concat(draw_rows, ignore_index=True) if draw_rows else pd.DataFrame(),
        "uncertainty_summary.csv": pd.concat(uncertainty, ignore_index=True) if uncertainty else pd.DataFrame()}.items():
        write_frame(output / name, frame.assign(artifact_schema_version=3, evaluation_protocol_version="temporal_v3", policy_version=4, matched_random_version=4))
    write_json(output / "audit_report.json", audit)
    write_json(output / "DECISION.json", decision)
    manifest["decision"] = decision
    manifest["artifacts"] = [{"path": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file()]
    write_json(output / "manifest.json", manifest)
    refresh_weekly_outputs(output)
    return output


def refresh_weekly_outputs(output: Path) -> None:
    """Create derived registries/report and refresh their manifest hashes."""
    metrics = pd.read_csv(output / "signal_policy_metrics.csv")
    write_frame(
        output / "policy_frontier.csv",
        metrics.loc[metrics["variant"].str.startswith("budget_")].copy(),
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    random_metrics = pd.read_csv(output / "random_draw_metrics.csv.gz")
    registry = {
        "version": 4,
        "draws": int(random_metrics["draw_id"].nunique()) if len(random_metrics) else 0,
        "seed": manifest["config"]["random"]["seed"],
        "primary_stratification": manifest["config"]["random"]["primary_stratification"],
        "sensitivity_stratifications": manifest["config"]["random"]["sensitivity_stratifications"],
        "outcome_ids": sorted(random_metrics["outcome_id"].dropna().unique().tolist()),
        "universe_ids": sorted(random_metrics["universe_id"].dropna().unique().tolist()),
        "continuous_cooldown": True,
    }
    write_json(output / "random_draw_registry.json", registry)
    canonical_path = output.parent / manifest["config"]["canonical_baseline_run_id"] / "summary.csv"
    if canonical_path.exists():
        canonical = pd.read_csv(canonical_path)
        canonical["comparison_role"] = "separate_rare_canonical_reference"
        canonical["equal_frequency_control"] = False
        write_frame(output / "canonical_reference.csv", canonical)
    render_weekly_report(output)
    manifest["artifacts"] = [
        {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    ]
    write_json(output / "manifest.json", manifest)


def render_weekly_report(output: Path) -> None:
    """Render the human-readable report from immutable tabular artifacts."""
    decision = json.loads((output / "DECISION.json").read_text(encoding="utf-8"))
    cadence_frame = pd.read_csv(output / "cadence_metrics.csv")
    baseline = pd.read_csv(output / "baseline_summary.csv")
    primary = baseline.loc[
        baseline["random_mode"].eq("calendar_month_weekday")
        & baseline["variant"].eq("operating")
    ]
    lines = [
        "# H017: attractiveness gate + future-safety RF",
        "",
        f"Decision: **{decision['status']}**. Full Monte Carlo allowed: "
        f"**{decision['full_monte_carlo_allowed']}**. Accepted corridors: "
        f"{', '.join(decision['accepted_corridors']) or 'none'}.",
        "",
        "| Corridor | Push/week | Safety | Mean regret, bp | P90 regret, bp | P90 gap, days | Active weeks |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cadence_frame.itertuples(index=False):
        lines.append(
            f"| {row.corridor} | {row.signals_per_week:.3f} | {row.signal_hit_rate:.1%} | "
            f"{row.mean_regret_bps:.1f} | {row.p90_regret_bps:.1f} | "
            f"{row.inter_signal_gap_days_p90:.1f} | {row.active_week_share:.1%} |"
        )
    lines += [
        "",
        "The policy misses the preregistered cadence and quality guardrails in every corridor. "
        "The full Monte Carlo/model-zoo branch is therefore stopped.",
        "",
        "| Corridor | Baseline | Model | Random | Delta | Lift |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in primary.itertuples(index=False):
        lines.append(
            f"| {row.corridor} | {row.baseline} | {row.model_hit_rate:.1%} | "
            f"{row.random_hit_rate:.1%} | {row.delta_hit_rate:+.1%} | {row.lift:.3f} |"
        )
    lines += [
        "",
        "The product baseline can show lift while the conditional baseline is negative; acceptance "
        "therefore correctly uses incremental value among gate-days.",
        "",
        "Canonical frozen RF remains a separate reference: 0.426 push/week, 84.7% safety, "
        "23.4 bp mean regret, 70.5 bp p90 regret, lift 1.214. It is not the equal-frequency control.",
        "",
        "This run is exploratory because its historical outer years were already inspected. "
        "Smoke uncertainty uses reduced draws/replicates and is diagnostic only. The CBR rate is "
        "a market proxy; bank-transfer benefit remains unverified.",
    ]
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
