import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.evaluation.comparison import load_compatible_runs


class ComparisonV3Test(unittest.TestCase):
    def test_different_universes_are_rejected_before_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            base = {
                "evaluation_protocol_version": "temporal_v3",
                "artifact_schema_version": 3,
            }
            (left / "manifest.json").write_text(
                json.dumps({**base, "universe_ids": {"all_corridors": "a"}}),
                encoding="utf-8",
            )
            (right / "manifest.json").write_text(
                json.dumps({**base, "universe_ids": {"all_corridors": "b"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "different eligible universes"):
                load_compatible_runs(left, right)


if __name__ == "__main__":
    unittest.main()
