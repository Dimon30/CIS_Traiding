import tempfile
import unittest
from pathlib import Path

from scripts.evaluation.artifacts import build_manifest, sha256_file, validate_protocol_compatibility


class ArtifactsV3Test(unittest.TestCase):
    def test_file_hash_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.txt"
            path.write_text("stable", encoding="utf-8")
            self.assertEqual(sha256_file(path), sha256_file(path))

    def test_incompatible_protocols_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            validate_protocol_compatibility(
                [
                    {"evaluation_protocol_version": "temporal_v3", "artifact_schema_version": 3},
                    {"evaluation_schema_version": 2},
                ]
            )

    def test_manifest_can_use_cleanliness_captured_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.txt"
            path.write_text("stable", encoding="utf-8")
            manifest = build_manifest(
                run_id="test",
                command=["python", "runner.py"],
                config={},
                input_paths=[path],
                universe_ids={"all": "u"},
                git_state={
                    "git_commit": "abc",
                    "git_dirty": False,
                    "git_diff_sha256": None,
                },
            )
        self.assertTrue(manifest["canonical_eligible"])
        self.assertEqual(manifest["git_commit"], "abc")


if __name__ == "__main__":
    unittest.main()
