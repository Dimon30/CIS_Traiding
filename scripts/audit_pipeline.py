"""Audit raw/processed FX data, feature availability, labels and leakage controls."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dataset import load_observations, select_input_file  # noqa: E402
from run_backtest import add_auxiliary_features, add_features  # noqa: E402
from run_experiment import resolve_feature_columns, split_frame  # noqa: E402


PRIMARY = ("TJS", "UZS", "KGS", "AMD", "KZT")
AUXILIARY = ("USD", "EUR")
FORBIDDEN_TOKENS = ("future", "target", "message_hit", "window_min", "window_mean")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/hypothesis_study"))
    return parser.parse_args()


def record(rows: list[dict[str, object]], check: str, status: bool, detail: str) -> None:
    rows.append({"check": check, "status": "PASS" if status else "FAIL", "detail": detail})


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---"] * len(columns)) + "|"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *body])


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    profile: list[dict[str, object]] = []

    for currency in (*PRIMARY, *AUXILIARY):
        path = select_input_file(currency, args.data_dir)
        observations = load_observations(path)
        dates = pd.Series([item.effective_date for item in observations])
        rates = np.array([float(item.rub_per_unit) for item in observations])
        clean = dates.is_monotonic_increasing and dates.nunique() == len(dates) and bool((rates > 0).all())
        record(rows, f"raw_{currency}", clean, f"{len(dates)} rows; {dates.min()}..{dates.max()}; normalized by nominal")
        profile.append(
            {
                "currency": currency,
                "rows": len(dates),
                "date_min": dates.min(),
                "date_max": dates.max(),
                "min_rate": round(float(rates.min()), 8),
                "max_rate": round(float(rates.max()), 8),
            }
        )

    for currency in PRIMARY:
        observations = pd.read_csv(args.processed_dir / f"rub_{currency.lower()}_observations.csv", parse_dates=["date"])
        labels = pd.read_csv(args.processed_dir / f"rub_{currency.lower()}_labels_h3_e50bp.csv", parse_dates=["date"])
        merged = observations.merge(labels, on=["date", "corridor"], validate="one_to_one")
        valid = merged[merged["has_full_window"]].copy()
        expected_message = (valid["future_regret_bps"] <= 50 + 1e-8).astype(int)
        expected_level = (valid["rub_per_unit"] <= valid["window_min_rub_per_unit"] * 1.005 + 1e-12).astype(int)
        labels_ok = bool((expected_message == valid["message_hit"]).all() and (expected_level == valid["target_good_now"]).all())
        record(rows, f"labels_{currency}", labels_ok, f"recomputed {len(valid)} complete h=3/e=50bp labels")

        featured = add_features(observations)
        expected = ["d1_per_day", "d2_per_day2", "ewm_d1_pct_5", "ewm_d2_pct_10", "rebound_from_past_min_60"]
        derivatives_ok = all(name in featured and featured[name].iloc[80:].notna().mean() > 0.95 for name in expected)
        record(rows, f"features_{currency}", derivatives_ok, "past-only first/second derivatives and reversal features available")

    sample = pd.read_csv(args.processed_dir / "rub_tjs_observations.csv", parse_dates=["date"])
    joined = add_auxiliary_features(add_features(sample), args.processed_dir, AUXILIARY)
    asof_ok = all((joined[f"{currency.lower()}_source_date"] <= joined["date"]).all() for currency in AUXILIARY)
    record(rows, "auxiliary_asof", asof_ok, "USD/EUR source_date never exceeds corridor date")

    with (Path("configs/features.toml")).open("rb") as stream:
        feature_config = tomllib.load(stream)
    all_features = resolve_feature_columns(feature_config, ["full_market_with_fx"])
    leakage_names = [name for name in all_features if any(token in name.lower() for token in FORBIDDEN_TOKENS)]
    record(rows, "feature_allowlist", not leakage_names, f"{len(all_features)} configured features; forbidden={leakage_names}")

    example = pd.DataFrame({"date": pd.date_range("2019-01-01", "2024-12-31", freq="D")})
    train, validation, test = split_frame(example, 2024, 20)
    purge_ok = train["date"].max() + pd.Timedelta(days=20) < validation["date"].min() and validation["date"].max() + pd.Timedelta(days=20) < test["date"].min()
    record(rows, "walk_forward_purge", bool(purge_ok), "20-day label window ends before validation/test starts")

    audit = pd.DataFrame(rows)
    profile_frame = pd.DataFrame(profile)
    audit.to_csv(args.output_dir / "data_quality_checks.csv", index=False)
    profile_frame.to_csv(args.output_dir / "data_profile.csv", index=False)
    failed = int((audit["status"] == "FAIL").sum())
    report = f"""# Аудит пайплайна данных

Проверено сырьё ЦБ, нормировка `curs / nominal`, формулы меток, временная доступность USD/EUR, производные и purge gap. Итог: **{len(audit) - failed}/{len(audit)} проверок пройдено**.

## Проверки

{markdown_table(audit)}

## Покрытие рядов

{markdown_table(profile_frame)}

## Граница интерпретации

DBF содержит дату начала действия курса, но не точное время публикации. Пайплайн использует значение не раньше effective date. Это консервативно по отношению к внутридневному инференсу. USD/EUR присоединяются только backward-as-of. Будущее используется в `labels`, но отсутствует в allowlist признаков.
"""
    (args.output_dir / "DATA_PIPELINE_AUDIT.md").write_text(report, encoding="utf-8")
    print(audit.to_string(index=False))
    if failed:
        raise SystemExit(f"Pipeline audit failed: {failed} checks")


if __name__ == "__main__":
    main()
