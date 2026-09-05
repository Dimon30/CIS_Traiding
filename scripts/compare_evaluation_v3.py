"""Compare two compatible frozen temporal_v3 result bundles."""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.artifacts import write_frame
from evaluation.comparison import (
    compare_frontiers_at_common_count,
    compare_policy_frontiers,
    compare_selected_policies,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--block-days", type=int, default=28)
    parser.add_argument("--replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42029)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    replicates, summary = compare_selected_policies(
        args.left,
        args.right,
        block_days=args.block_days,
        replicates=args.replicates,
        seed=args.seed,
    )
    write_frame(args.output / "paired_bootstrap_replicates.csv.gz", replicates)
    write_frame(args.output / "paired_comparisons.csv", summary)
    write_frame(
        args.output / "policy_frontier_comparison.csv",
        compare_policy_frontiers(args.left, args.right),
    )
    write_frame(
        args.output / "policy_frontier_common_count.csv",
        compare_frontiers_at_common_count(args.left, args.right),
    )


if __name__ == "__main__":
    main()
