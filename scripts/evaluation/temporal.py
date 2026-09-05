"""Leakage-safe temporal split construction for evaluation protocol v3."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .contracts import (
    DateBlock,
    InnerFoldSpec,
    TemporalFoldSpec,
    TemporalRole,
    require_columns,
)


def year_start(year: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=1, day=1)


def purged_year_block(year: int, horizon_days: int, role: TemporalRole) -> DateBlock:
    return DateBlock(
        role=role,
        start=year_start(year),
        end_exclusive=year_start(year + 1) - pd.Timedelta(days=horizon_days),
    )


def build_inner_selection_folds(
    outer_test_year: int,
    horizon_days: int,
    *,
    first_selection_year: int = 2019,
) -> tuple[InnerFoldSpec, ...]:
    last_selection_year = outer_test_year - 3
    if last_selection_year < first_selection_year:
        return ()
    folds: list[InnerFoldSpec] = []
    gap = pd.Timedelta(days=horizon_days)
    for validation_year in range(first_selection_year, last_selection_year + 1):
        folds.append(
            InnerFoldSpec(
                outer_test_year=outer_test_year,
                validation_year=validation_year,
                train=DateBlock(
                    TemporalRole.INNER_TRAIN,
                    None,
                    year_start(validation_year) - gap,
                ),
                validation=purged_year_block(
                    validation_year,
                    horizon_days,
                    TemporalRole.INNER_VALIDATION,
                ),
            )
        )
    return tuple(folds)


def build_v3_outer_fold(
    test_year: int,
    horizon_days: int,
    *,
    first_selection_year: int = 2019,
    observed_data_cutoff: pd.Timestamp | None = None,
    label_complete_through: pd.Timestamp | None = None,
) -> TemporalFoldSpec:
    gap = pd.Timedelta(days=horizon_days)
    nominal_test_end = year_start(test_year + 1)
    partial = bool(
        label_complete_through is not None
        and label_complete_through < nominal_test_end - pd.Timedelta(days=1)
    )
    test_end = (
        label_complete_through.normalize() + pd.Timedelta(days=1)
        if partial and label_complete_through is not None
        else nominal_test_end
    )
    calibration_year = test_year - 2
    policy_year = test_year - 1
    return TemporalFoldSpec(
        fold_id=f"outer_{test_year}",
        test_year=test_year,
        horizon_days=horizon_days,
        refit_train=DateBlock(
            TemporalRole.REFIT_TRAIN,
            None,
            year_start(calibration_year) - gap,
        ),
        calibration=purged_year_block(
            calibration_year, horizon_days, TemporalRole.CALIBRATION
        ),
        policy=purged_year_block(policy_year, horizon_days, TemporalRole.POLICY),
        outer_test=DateBlock(
            TemporalRole.OUTER_TEST,
            year_start(test_year),
            test_end,
        ),
        inner_folds=build_inner_selection_folds(
            test_year,
            horizon_days,
            first_selection_year=first_selection_year,
        ),
        is_partial_fold=partial,
        data_cutoff=observed_data_cutoff,
        label_complete_through=label_complete_through,
    )


def build_v3_outer_folds(
    first_test_year: int,
    last_test_year: int,
    horizon_days: int,
    *,
    first_selection_year: int = 2019,
    observed_data_cutoff: pd.Timestamp | None = None,
    label_complete_through: pd.Timestamp | None = None,
) -> tuple[TemporalFoldSpec, ...]:
    return tuple(
        build_v3_outer_fold(
            year,
            horizon_days,
            first_selection_year=first_selection_year,
            observed_data_cutoff=observed_data_cutoff,
            label_complete_through=(
                label_complete_through if year == last_test_year else None
            ),
        )
        for year in range(first_test_year, last_test_year + 1)
    )


def slice_role(frame: pd.DataFrame, block: DateBlock) -> pd.DataFrame:
    require_columns(frame, ["date"], "temporal input")
    result = frame.loc[block.contains(frame["date"])].copy()
    result["temporal_role"] = block.role.value
    return result


def assert_label_window_before(
    frame: pd.DataFrame,
    next_block_start: pd.Timestamp,
    horizon_days: int,
    context: str,
) -> None:
    if frame.empty:
        return
    last_label_date = frame["date"].max() + pd.Timedelta(days=horizon_days)
    if last_label_date >= next_block_start:
        raise AssertionError(
            f"{context} label window reaches {last_label_date.date()}, "
            f"next block starts {next_block_start.date()}"
        )


def assert_role_disjointness(parts: Iterable[pd.DataFrame]) -> None:
    keys: set[tuple[object, ...]] = set()
    for frame in parts:
        if frame.empty:
            continue
        identity = ["date"] + (["corridor"] if "corridor" in frame else [])
        current = set(frame[identity].itertuples(index=False, name=None))
        overlap = keys.intersection(current)
        if overlap:
            raise AssertionError(f"Temporal roles overlap on {next(iter(overlap))}")
        keys.update(current)


def validate_corridor_synchronization(
    frame: pd.DataFrame,
    required_corridors: Iterable[str],
    *,
    minimum_rows_per_corridor: int,
) -> dict[str, int]:
    require_columns(frame, ["date", "corridor"], "synchronized temporal block")
    required = tuple(required_corridors)
    counts = frame.groupby("corridor", observed=True).size().to_dict()
    missing = [item for item in required if counts.get(item, 0) < minimum_rows_per_corridor]
    if missing:
        raise ValueError(
            "Temporal block fails synchronized minimum rows for: " + ", ".join(missing)
        )
    return {item: int(counts[item]) for item in required}
