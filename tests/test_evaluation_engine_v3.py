import unittest

import pandas as pd

from scripts.evaluation.engine import _project


class EvaluationEngineV3Test(unittest.TestCase):
    def test_artifact_projection_deduplicates_identity_keys(self) -> None:
        frame = pd.DataFrame({"date": ["2025-01-01"], "corridor": ["RUB_TJS"]})
        projected = _project(frame, ["date", "corridor", "corridor"])
        self.assertEqual(projected.columns.tolist(), ["date", "corridor"])


if __name__ == "__main__":
    unittest.main()
