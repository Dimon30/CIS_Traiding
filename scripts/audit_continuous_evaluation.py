"""Audit old OOT bundles and optionally replay delivery/random without model refits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from evaluation.artifacts import sha256_file, write_frame, write_json, git_metadata
from evaluation.audit import continuous_cooldown_violations, audit_continuous_schedules
from evaluation.metrics import signal_metrics, aggregate_signal_metrics
from evaluation.policy import SelectedPolicy
from evaluation.weekly import DeliveryState, continuous_draws


def audit_and_repair(source: Path, output: Path, repair: bool, draws: int | None):
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    cooldown = int(manifest["config"]["policy"]["cooldown_days"])
    original = pd.read_csv(source / "policy_decisions.csv.gz", parse_dates=["date"])
    random = pd.read_csv(source / "random_schedules.csv.gz", parse_dates=["date"])
    frontier = pd.read_csv(source / "frontier_decisions.csv.gz", parse_dates=["date"])
    violations = {
        "model": continuous_cooldown_violations(original, cooldown),
        "frontier": continuous_cooldown_violations(frontier, cooldown),
        "random": continuous_cooldown_violations(random, cooldown, random=True),
    }
    output.mkdir(parents=True, exist_ok=False)
    report = {"source": str(source), "source_manifest_sha256": sha256_file(source / "manifest.json"),
              "violations": {key: len(value) for key, value in violations.items()},
              "source_overwritten": False}
    for key, value in violations.items():
        if len(value):
            write_frame(output / f"{key}_violations.csv.gz", value)
    write_json(output / "historical_audit.json", report)
    if not repair or not any(len(value) for value in violations.values()):
        return report
    state = DeliveryState()
    replays = []
    frontier["variant"] = frontier["frontier_point_id"]
    for variant, frame in [("operating", original), *list(frontier.groupby("variant", observed=True))]:
        for _, group in frame.groupby(["outer_fold", "corridor"], sort=True, observed=True):
            threshold = group["threshold"].iloc[0]
            policy = SelectedPolicy(float(threshold), "active") if pd.notna(threshold) else SelectedPolicy(None, "inactive")
            replays.append(state.apply(group, policy, str(variant), cooldown, gated=False).assign(variant=variant))
    replay = pd.concat(replays, ignore_index=True)
    boundaries = pd.read_csv(source / "fold_boundaries.csv", parse_dates=["test_start", "test_end_exclusive"])
    mode = manifest["config"]["random"]["primary_stratification"]
    random_frames, cells = [], []
    repeats = draws or manifest.get("random_draws", manifest["config"]["random"]["draws"])
    for (variant, corridor), group in replay.groupby(["variant", "corridor"], observed=True):
        print(f"[repair] {source.name} {variant} {corridor}", flush=True)
        sampled = continuous_draws(group, group.loc[group["selected_signal"]], mode=mode, draws=repeats,
            seed=manifest["config"]["random"]["seed"], cooldown_days=cooldown, stream_id=f"repair:{source.name}:{variant}:{corridor}")
        random_frames.append(sampled.assign(variant=variant))
        for fold_id, fold in group.groupby("outer_fold", observed=True):
            dates = boundaries.loc[boundaries["outer_fold"].eq(fold_id)].iloc[0]
            rate = sampled.loc[sampled["outer_fold"].eq(fold_id)].groupby("draw_id")["message_hit"].mean().mean()
            cells.append({"variant": variant, "corridor": corridor, "outer_fold": fold_id,
                **signal_metrics(fold, exposure_start=dates["test_start"], exposure_end_exclusive=dates["test_end_exclusive"], random_hit_rate=rate, cooldown_days=cooldown)})
    random_new = pd.concat(random_frames, ignore_index=True)
    audit_continuous_schedules(replay, random_new, cooldown)
    cells = pd.DataFrame(cells)
    summary = pd.DataFrame([{"variant": variant, **aggregate_signal_metrics(group)} for variant, group in cells.groupby("variant")])
    corrected = replay.loc[replay["variant"].eq("operating")]
    keys = ["outer_fold", "corridor", "date"]
    compared = original[keys + ["selected_signal"]].merge(corrected[keys + ["selected_signal"]], on=keys, suffixes=("_old", "_new"), validate="one_to_one")
    report["model_decisions_changed"] = int(compared["selected_signal_old"].ne(compared["selected_signal_new"]).sum())
    report["retrained"] = False
    report["draws"] = repeats
    write_frame(output / "policy_decisions.csv.gz", corrected)
    write_frame(output / "frontier_decisions.csv.gz", replay.loc[~replay["variant"].eq("operating")])
    write_frame(output / "random_schedules.csv.gz", random_new)
    write_frame(output / "signal_policy_metrics.csv", cells)
    write_frame(output / "summary.csv", summary)
    write_json(output / "historical_audit.json", report)
    write_json(output / "manifest.json", {**manifest, **git_metadata(), "run_id": output.name,
        "policy_version": 4, "matched_random_version": 4, "canonical_eligible": False,
        "bundle_kind": "continuous_cooldown_repair", "source_bundle": str(source),
        "source_manifest_sha256": report["source_manifest_sha256"], "retrained": False,
        "random_draws": repeats, "uncertainty_recomputed": False,
        "artifacts": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir()) if p.is_file()]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--draws", type=int)
    args = parser.parse_args()
    print(json.dumps(audit_and_repair(args.source, args.output, args.repair, args.draws), indent=2))


if __name__ == "__main__":
    main()
