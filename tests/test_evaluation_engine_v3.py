import unittest

import pandas as pd

from scripts.evaluation.engine import _activate_target, _project, _universe_extra_contract


class EvaluationEngineV3Test(unittest.TestCase):
    def test_canonical_target_preserves_frozen_universe_contract(self) -> None:
        self.assertEqual(
            _universe_extra_contract(3, 50, "message_hit"),
            {"horizon_days": 3, "epsilon_bps": 50},
        )
        self.assertEqual(
            _universe_extra_contract(3, 50, "target_good_now")["target"],
            "target_good_now",
        )

    def test_artifact_projection_deduplicates_identity_keys(self) -> None:
        frame = pd.DataFrame({"date": ["2025-01-01"], "corridor": ["RUB_TJS"]})
        projected = _project(frame, ["date", "corridor", "corridor"])
        self.assertEqual(projected.columns.tolist(), ["date", "corridor"])

    def test_target_good_now_becomes_active_outcome_and_preserves_safety(self) -> None:
        frame = pd.DataFrame(
            {
                "message_hit": [1, 0],
                "target_good_now": [0, 1],
            }
        )
        activated = _activate_target(frame, "target_good_now")
        self.assertEqual(activated["message_hit"].tolist(), [0, 1])
        self.assertEqual(activated["future_safety_message_hit"].tolist(), [1, 0])

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported temporal_v3 target"):
            _activate_target(pd.DataFrame({"message_hit": [1]}), "unknown")

    def test_incomplete_universe_labels_remain_nullable(self) -> None:
        frame = pd.DataFrame(
            {
                "message_hit": [1, None],
                "target_good_now": [0, None],
            }
        )
        activated = _activate_target(frame, "target_good_now")
        self.assertEqual(str(activated["message_hit"].dtype), "Int64")
        self.assertTrue(pd.isna(activated.loc[1, "message_hit"]))


if __name__ == "__main__":
    unittest.main()
