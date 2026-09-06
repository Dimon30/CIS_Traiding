"""Export one saved OOT prediction policy into the demo's stable JSON contract."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
CORRIDOR_COUNTRY_CODES = {
    "RUB_TJS": "TJ",
    "RUB_UZS": "UZ",
    "RUB_KGS": "KG",
    "RUB_AMD": "AM",
    "RUB_KZT": "KZ",
}
SELECTORS = {
    "hypothesis_id": "hypothesis-id",
    "model": "model",
    "strategy": "strategy",
    "horizon_days": "horizon-days",
    "epsilon_bps": "epsilon-bps",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fx-push-demo/public/model-signals.json"),
    )
    parser.add_argument("--hypothesis-id")
    parser.add_argument("--model")
    parser.add_argument("--strategy")
    parser.add_argument("--horizon-days", type=int)
    parser.add_argument("--epsilon-bps", type=int)
    return parser.parse_args()


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def resolve_slice(rows: list[dict[str, str]], selectors: dict[str, object | None]) -> tuple[list[dict[str, str]], dict[str, str]]:
    selected = rows
    resolved: dict[str, str] = {}
    for column, cli_name in SELECTORS.items():
        requested = selectors.get(column)
        values = sorted({row[column] for row in selected})
        if requested is None:
            if len(values) != 1:
                rendered = ", ".join(values)
                raise ValueError(
                    f"Prediction bundle has multiple {column} values ({rendered}); "
                    f"pass --{cli_name}."
                )
            value = values[0]
        else:
            value = str(requested)
            if value not in values:
                raise ValueError(f"Unknown {column}={value!r}; available: {', '.join(values)}")
        selected = [row for row in selected if row[column] == value]
        resolved[column] = value
    return selected, resolved


def export_payload(run_dir: Path, selectors: dict[str, object | None]) -> dict[str, Any]:
    predictions_path = run_dir / "predictions.csv"
    policy_decisions_path = run_dir / "policy_decisions.csv.gz"
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if predictions_path.is_file():
        with predictions_path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
    elif policy_decisions_path.is_file():
        import gzip

        with gzip.open(policy_decisions_path, "rt", encoding="utf-8-sig", newline="") as source:
            temporal_rows = list(csv.DictReader(source))
        target_contract = manifest.get("target_contract", {})
        rows = [
            {
                **row,
                "score": row["calibrated_score"],
                "model": row["model_id"],
                "horizon_days": str(target_contract.get("horizon_calendar_days", "")),
                "epsilon_bps": str(target_contract.get("epsilon_bps", "")),
            }
            for row in temporal_rows
        ]
    else:
        raise FileNotFoundError(
            f"Neither {predictions_path.name} nor {policy_decisions_path.name} exists in {run_dir}"
        )

    if not rows:
        raise ValueError(f"No policy decisions found in {run_dir}")

    required = {
        "date", "corridor", "rub_per_unit", "score", "candidate", "selected_signal",
        "threshold", *SELECTORS,
    }
    missing = required - rows[0].keys()
    if missing:
        raise ValueError(f"predictions.csv is missing columns: {', '.join(sorted(missing))}")

    rows, resolved = resolve_slice(rows, selectors)
    if not rows:
        raise ValueError("Selected prediction slice is empty")
    rows.sort(key=lambda row: (row["date"], row["corridor"]))

    seen: set[tuple[str, str]] = set()
    signals: list[dict[str, Any]] = []
    for row in rows:
        corridor = row["corridor"]
        if corridor not in CORRIDOR_COUNTRY_CODES:
            raise ValueError(f"Demo does not map corridor {corridor!r}")
        key = (row["date"], corridor)
        if key in seen:
            raise ValueError(f"Duplicate decision for date/corridor: {key}")
        seen.add(key)

        candidate = parse_bool(row["candidate"])
        send = parse_bool(row["selected_signal"])
        if send and not candidate:
            raise ValueError(f"Selected signal is not a candidate: {key}")
        score = float(row["score"])
        threshold = float(row["threshold"])
        decision = {
            "date": row["date"],
            "corridor": corridor,
            "countryCode": CORRIDOR_COUNTRY_CODES[corridor],
            "rateRubPerUnit": float(row["rub_per_unit"]),
            "score": score,
            "threshold": threshold,
            "signalType": "good_now",
            "signalSpeed": "fast",
            "candidate": candidate,
            "send": send,
            "reasonCode": "send" if send else "cooldown" if candidate else "below_threshold",
            "priority": score - threshold,
        }
        if send:
            signals.append(decision)

    dates = [row["date"] for row in rows]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(),
        "source": {
            "runId": manifest.get("run_id", run_dir.name),
            "datasetVersion": manifest.get("dataset_version"),
            "gitCommit": manifest.get("git_commit"),
            "hypothesisId": resolved["hypothesis_id"],
            "model": resolved["model"],
            "strategy": resolved["strategy"],
            "horizonDays": int(resolved["horizon_days"]),
            "epsilonBps": int(resolved["epsilon_bps"]),
        },
        "coverage": {
            "from": min(dates),
            "to": max(dates),
            "decisionCount": len(rows),
            "signalCount": len(signals),
        },
        "signals": signals,
    }


def main() -> None:
    args = parse_args()
    payload = export_payload(
        args.run_dir,
        {
            "hypothesis_id": args.hypothesis_id,
            "model": args.model,
            "strategy": args.strategy,
            "horizon_days": args.horizon_days,
            "epsilon_bps": args.epsilon_bps,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Exported {payload['coverage']['decisionCount']} decisions and "
        f"{payload['coverage']['signalCount']} final signals to {args.output}"
    )


if __name__ == "__main__":
    main()
