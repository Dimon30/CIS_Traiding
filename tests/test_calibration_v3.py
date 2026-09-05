import unittest

import pandas as pd

from scripts.evaluation.calibration import IdentityCalibrator


class CalibrationV3Test(unittest.TestCase):
    def test_identity_requires_calibration_role(self) -> None:
        frame = pd.DataFrame({"raw_score": [0.2, 0.8], "temporal_role": ["policy", "policy"]})
        with self.assertRaisesRegex(ValueError, "requires role=calibration"):
            IdentityCalibrator().fit(frame)

    def test_identity_preserves_score(self) -> None:
        frame = pd.DataFrame(
            {"raw_score": [0.2, 0.8], "temporal_role": ["calibration", "calibration"]}
        )
        calibrator = IdentityCalibrator().fit(frame)
        self.assertEqual(calibrator.transform(frame["raw_score"]).tolist(), [0.2, 0.8])


if __name__ == "__main__":
    unittest.main()
