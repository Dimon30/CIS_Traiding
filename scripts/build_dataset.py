"""Build point-in-time observations and future-based labels from CBR DBF data."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from dbfread import DBF


REQUIRED_FIELDS = {"nominal", "data", "curs"}
DEFAULT_HORIZONS = (1, 3, 5, 10, 20)
DEFAULT_CURRENCIES = ("TJS", "UZS", "KGS", "AMD", "KZT")
DEFAULT_AUXILIARY_CURRENCIES = ("USD", "EUR", "CNY")


@dataclass(frozen=True)
class RateObservation:
    effective_date: date
    nominal: int
    value_rub: Decimal
    rub_per_unit: Decimal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one-corridor observations and labels from a CBR DBF file."
    )
    parser.add_argument("--currency", default="TJS", help="Currency code, for example TJS")
    parser.add_argument(
        "--all-currencies",
        action="store_true",
        help="Build TJS, UZS, KGS, AMD and KZT in one run",
    )
    parser.add_argument(
        "--currencies",
        help="Comma-separated currencies; overrides --currency/--all-currencies",
    )
    parser.add_argument(
        "--include-auxiliary",
        action="store_true",
        help="Also build point-in-time observations for USD, EUR and CNY",
    )
    parser.add_argument(
        "--observations-only",
        action="store_true",
        help="Write observations without future-based labels (useful for auxiliary FX)",
    )
    parser.add_argument("--input", type=Path, help="Exact DBF path; otherwise selected by currency")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--horizon",
        type=int,
        help="Build one calendar-day horizon; overrides --horizons",
    )
    parser.add_argument(
        "--horizons",
        default=",".join(map(str, DEFAULT_HORIZONS)),
        help="Comma-separated calendar-day horizons",
    )
    parser.add_argument(
        "--epsilon",
        type=Decimal,
        default=Decimal("0.005"),
        help="Allowed relative distance from the best rate; 0.005 means 0.5%%",
    )
    return parser.parse_args()


def parse_horizons(raw: str) -> tuple[int, ...]:
    horizons = tuple(dict.fromkeys(int(value.strip()) for value in raw.split(",") if value.strip()))
    if not horizons or any(horizon <= 0 for horizon in horizons):
        raise ValueError("Horizons must contain positive integers")
    return horizons


def select_input_file(currency: str, input_dir: Path) -> Path:
    candidates = sorted(input_dir.glob(f"{currency.upper()}_RC_*.dbf"))
    if not candidates:
        raise FileNotFoundError(f"No DBF file found for {currency.upper()} in {input_dir}")
    return max(candidates, key=lambda path: (path.stat().st_size, path.name))


def load_observations(path: Path) -> list[RateObservation]:
    table = DBF(path, encoding="cp1251", lowernames=True)
    field_names = {field.name.lower() for field in table.fields}
    missing = REQUIRED_FIELDS - field_names
    if missing:
        raise ValueError(f"Missing DBF fields: {sorted(missing)}")

    by_date: dict[date, RateObservation] = {}
    for record in table:
        effective_date = record["data"]
        nominal = int(record["nominal"])
        value_rub = Decimal(str(record["curs"]))
        if nominal <= 0 or value_rub <= 0:
            raise ValueError(f"Invalid rate on {effective_date}: {nominal=}, {value_rub=}")
        by_date[effective_date] = RateObservation(
            effective_date=effective_date,
            nominal=nominal,
            value_rub=value_rub,
            rub_per_unit=value_rub / Decimal(nominal),
        )

    observations = sorted(by_date.values(), key=lambda item: item.effective_date)
    if not observations:
        raise ValueError(f"No records found in {path}")
    return observations


def build_daily_rates(observations: list[RateObservation]) -> dict[date, Decimal]:
    """Forward-fill effective rates to calendar days for calendar-day target windows."""
    rates: dict[date, Decimal] = {}
    current_index = 0
    current_date = observations[0].effective_date
    last_date = observations[-1].effective_date
    current_rate = observations[0].rub_per_unit

    while current_date <= last_date:
        while (
            current_index + 1 < len(observations)
            and observations[current_index + 1].effective_date <= current_date
        ):
            current_index += 1
            current_rate = observations[current_index].rub_per_unit
        rates[current_date] = current_rate
        current_date += timedelta(days=1)
    return rates


def iter_days(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def build_label_rows(
    observations: list[RateObservation],
    horizon: int,
    epsilon: Decimal,
    corridor: str,
) -> list[dict[str, object]]:
    if horizon <= 0:
        raise ValueError("Horizon must be positive")
    if epsilon < 0:
        raise ValueError("Epsilon must be non-negative")

    daily_rates = build_daily_rates(observations)
    first_date = observations[0].effective_date
    last_date = observations[-1].effective_date
    rows: list[dict[str, object]] = []

    for observation in observations:
        current_date = observation.effective_date
        window_start = current_date - timedelta(days=horizon)
        window_end = current_date + timedelta(days=horizon)
        has_full_window = window_start >= first_date and window_end <= last_date

        row: dict[str, object] = {
            "date": current_date.isoformat(),
            "corridor": corridor,
            "horizon_calendar_days": horizon,
            "epsilon": format_decimal(epsilon),
            "has_full_window": has_full_window,
            "window_min_rub_per_unit": "",
            "window_mean_rub_per_unit": "",
            "future_min_rub_per_unit": "",
            "target_good_now": "",
            "message_hit": "",
            "future_regret_bps": "",
            "moment_advantage_bps": "",
        }

        if has_full_window:
            window_values = [daily_rates[day] for day in iter_days(window_start, window_end)]
            future_values = [
                daily_rates[day]
                for day in iter_days(current_date + timedelta(days=1), window_end)
            ]
            current_rate = observation.rub_per_unit
            window_min = min(window_values)
            window_mean = sum(window_values) / Decimal(len(window_values))
            future_min = min(future_values)
            future_regret = max(Decimal(0), (current_rate - future_min) / current_rate)
            moment_advantage = (window_mean - current_rate) / window_mean

            row.update(
                {
                    "window_min_rub_per_unit": format_decimal(window_min),
                    "window_mean_rub_per_unit": format_decimal(window_mean),
                    "future_min_rub_per_unit": format_decimal(future_min),
                    "target_good_now": int(current_rate <= window_min * (Decimal(1) + epsilon)),
                    "message_hit": int(future_regret <= epsilon),
                    "future_regret_bps": format_decimal(future_regret * Decimal(10_000)),
                    "moment_advantage_bps": format_decimal(moment_advantage * Decimal(10_000)),
                }
            )
        rows.append(row)
    return rows


def build_observation_rows(
    observations: list[RateObservation], currency: str, source_file: str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    previous: RateObservation | None = None
    for observation in observations:
        rows.append(
            {
                "date": observation.effective_date.isoformat(),
                "corridor": f"RUB_{currency}",
                "currency": currency,
                "source": "CBR",
                "source_file": source_file,
                "nominal": observation.nominal,
                "value_rub": format_decimal(observation.value_rub),
                "rub_per_unit": format_decimal(observation.rub_per_unit),
                "units_per_rub": format_decimal(Decimal(1) / observation.rub_per_unit),
                "days_since_previous": (
                    ""
                    if previous is None
                    else (observation.effective_date - previous.effective_date).days
                ),
                "same_rate_as_previous": (
                    ""
                    if previous is None
                    else observation.rub_per_unit == previous.rub_per_unit
                ),
            }
        )
        previous = observation
    return rows


def format_decimal(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0000000001")), "f")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty dataset to {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_currency_dataset(
    *,
    currency: str,
    input_path: Path,
    output_dir: Path,
    horizons: tuple[int, ...],
    epsilon: Decimal,
    observations_only: bool = False,
) -> None:
    observations = load_observations(input_path)
    corridor = f"RUB_{currency}"
    observation_rows = build_observation_rows(observations, currency, input_path.name)
    epsilon_bps = int(epsilon * Decimal(10_000))
    observations_path = output_dir / f"rub_{currency.lower()}_observations.csv"
    write_csv(observations_path, observation_rows)
    print(f"Input: {input_path}")
    print(f"Observations: {len(observation_rows)} -> {observations_path}")

    if observations_only:
        return

    for horizon in horizons:
        label_rows = build_label_rows(observations, horizon, epsilon, corridor)
        labels_path = output_dir / (
            f"rub_{currency.lower()}_labels_h{horizon}_e{epsilon_bps}bp.csv"
        )
        write_csv(labels_path, label_rows)
        complete_labels = sum(row["has_full_window"] is True for row in label_rows)
        positives = sum(row["target_good_now"] == 1 for row in label_rows)
        hits = sum(row["message_hit"] == 1 for row in label_rows)
        print(
            f"  h={horizon}: complete={complete_labels}, "
            f"target_good_now={positives}, message_hit={hits} -> {labels_path}"
        )


def main() -> None:
    args = parse_args()
    horizons = (args.horizon,) if args.horizon else parse_horizons(args.horizons)
    if args.currencies:
        currencies = tuple(
            dict.fromkeys(item.strip().upper() for item in args.currencies.split(",") if item.strip())
        )
    elif args.all_currencies:
        currencies = DEFAULT_CURRENCIES
    else:
        currencies = (args.currency.upper(),)
    if args.include_auxiliary:
        currencies = tuple(dict.fromkeys((*currencies, *DEFAULT_AUXILIARY_CURRENCIES)))
    if args.input and len(currencies) != 1:
        raise ValueError("--input can only be used with one --currency")

    for currency in currencies:
        input_path = args.input or select_input_file(currency, args.input_dir)
        build_currency_dataset(
            currency=currency,
            input_path=input_path,
            output_dir=args.output_dir,
            horizons=horizons,
            epsilon=args.epsilon,
            observations_only=args.observations_only or currency in DEFAULT_AUXILIARY_CURRENCIES,
        )


if __name__ == "__main__":
    main()
