"""Time-role-safe score calibration interfaces.

Wave 0 intentionally provides only identity calibration. Future calibration
hypotheses must implement this interface without changing temporal allocation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import TemporalRole, require_columns, require_role


@dataclass
class IdentityCalibrator:
    method: str = "identity"
    fitted_: bool = False

    def fit(self, frame: pd.DataFrame) -> "IdentityCalibrator":
        require_columns(frame, ["raw_score"], "calibration frame")
        require_role(frame, TemporalRole.CALIBRATION, "calibration frame")
        scores = frame["raw_score"].to_numpy(dtype=float)
        if not np.isfinite(scores).all():
            raise ValueError("Calibration scores must be finite")
        self.fitted_ = True
        return self

    def transform(self, scores: pd.Series | np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise RuntimeError("Calibrator must be fitted before transform")
        values = np.asarray(scores, dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Scores must be finite")
        return values.copy()

    def fit_transform_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        self.fit(result)
        result["calibrated_score"] = self.transform(result["raw_score"])
        result["calibration_method"] = self.method
        return result
