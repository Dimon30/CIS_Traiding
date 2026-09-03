"""Show the recorded point-in-time decision for a corridor and historical date."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Historical date in YYYY-MM-DD format")
    parser.add_argument("--corridor", default="RUB_TJS")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--signals", type=Path, default=Path("results/backtest/signals.csv"))
    args = parser.parse_args()

    signals = pd.read_csv(args.signals)
    selected = signals.loc[
        (signals["date"] == args.date)
        & (signals["corridor"] == args.corridor.upper())
        & (signals["horizon_days"] == args.horizon)
    ]
    if selected.empty:
        result = {
            "date": args.date,
            "corridor": args.corridor.upper(),
            "horizon_days": args.horizon,
            "send": False,
            "reason_code": "no_recorded_signal",
        }
    else:
        row = selected.iloc[-1]
        result = {
            "date": row["date"],
            "corridor": row["corridor"],
            "horizon_days": int(row["horizon_days"]),
            "rate": float(row["rub_per_unit"]),
            "score": float(row["score"]),
            "threshold": float(row["threshold"]),
            "send": True,
            "indicator": row["indicator"],
            "direction": row["direction"],
            "strength": row["signal_strength"],
            "speed": row["signal_speed"],
            "recommended_scenario": row["recommended_scenario"],
            "reason_code": row["reason_code"],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
