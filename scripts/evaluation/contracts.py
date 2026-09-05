"""Typed, versioned contracts shared by evaluation protocol v3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

import pandas as pd


TARGET_CONTRACT_VERSION = 2
ELIGIBILITY_VERSION = 1
EVALUATION_PROTOCOL_VERSION = "temporal_v3"
ARTIFACT_SCHEMA_VERSION = 3
POLICY_VERSION = 3
MATCHED_RANDOM_VERSION = 3
UNCERTAINTY_VERSION = 1


class TemporalRole(StrEnum):
    INNER_TRAIN = "inner_train"
    INNER_VALIDATION = "inner_validation"
    REFIT_TRAIN = "refit_train"
    CALIBRATION = "calibration"
    POLICY = "policy"
    OUTER_TEST = "outer_test"


@dataclass(frozen=True)
class EligibilitySpec:
    version: int = ELIGIBILITY_VERSION
    require_effective_date_row: bool = True
    require_full_window: bool = True
    exclude_unchanged_rate: bool = True


@dataclass(frozen=True)
class DateBlock:
    role: TemporalRole
    start: pd.Timestamp | None
    end_exclusive: pd.Timestamp

    def contains(self, dates: pd.Series) -> pd.Series:
        before_end = dates < self.end_exclusive
        return before_end if self.start is None else dates.ge(self.start) & before_end


@dataclass(frozen=True)
class InnerFoldSpec:
    outer_test_year: int
    validation_year: int
    train: DateBlock
    validation: DateBlock


@dataclass(frozen=True)
class TemporalFoldSpec:
    fold_id: str
    test_year: int
    horizon_days: int
    refit_train: DateBlock
    calibration: DateBlock
    policy: DateBlock
    outer_test: DateBlock
    inner_folds: tuple[InnerFoldSpec, ...]
    is_partial_fold: bool = False
    data_cutoff: pd.Timestamp | None = None
    label_complete_through: pd.Timestamp | None = None


def require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{context} is missing columns: {', '.join(missing)}")


def require_role(frame: pd.DataFrame, role: TemporalRole, context: str) -> None:
    require_columns(frame, ["temporal_role"], context)
    observed = set(frame["temporal_role"].astype(str).unique())
    if observed - {role.value}:
        raise ValueError(
            f"{context} requires role={role.value}; observed={sorted(observed)}"
        )
