import csv
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from export_demo_signals import export_payload


class ExportDemoSignalsTest(unittest.TestCase):
    def test_exports_temporal_v3_policy_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text(
                json.dumps({
                    "run_id": "temporal-v3-run",
                    "target_contract": {"horizon_calendar_days": 3, "epsilon_bps": 50},
                }),
                encoding="utf-8",
            )
            fields = [
                "date", "corridor", "rub_per_unit", "calibrated_score", "candidate",
                "selected_signal", "threshold", "hypothesis_id", "strategy", "model_id",
            ]
            rows = [
                {
                    "date": "2026-05-20", "corridor": "RUB_UZS", "rub_per_unit": "0.0068",
                    "calibrated_score": "0.91", "candidate": "True", "selected_signal": "True",
                    "threshold": "0.85", "hypothesis_id": "H009_evaluation_v3",
                    "strategy": "pooled_with_corridor_thresholds", "model_id": "random_forest",
                }
            ]
            with gzip.open(run_dir / "policy_decisions.csv.gz", "wt", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            payload = export_payload(
                run_dir,
                {
                    "hypothesis_id": None, "model": None, "strategy": None,
                    "horizon_days": None, "epsilon_bps": None,
                },
            )

        self.assertEqual(payload["source"]["runId"], "temporal-v3-run")
        self.assertEqual(payload["source"]["horizonDays"], 3)
        self.assertEqual(payload["source"]["epsilonBps"], 50)
        self.assertEqual(payload["signals"][0]["countryCode"], "UZ")
        self.assertAlmostEqual(payload["signals"][0]["score"], 0.91)

    def test_exports_selected_policy_without_coupling_to_notification_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text(
                json.dumps({"run_id": "test-run", "dataset_version": "dataset-v1"}),
                encoding="utf-8",
            )
            fields = [
                "date", "corridor", "rub_per_unit", "score", "candidate",
                "selected_signal", "threshold", "hypothesis_id", "horizon_days",
                "epsilon_bps", "strategy", "model",
            ]
            rows = []
            for offset in range(12):
                rows.append(
                    {
                        "date": f"2026-01-{offset + 1:02d}",
                        "corridor": "RUB_TJS",
                        "rub_per_unit": str(9 - offset / 100),
                        "score": "0.81",
                        "candidate": "True" if offset == 11 else "False",
                        "selected_signal": "True" if offset == 11 else "False",
                        "threshold": "0.80",
                        "hypothesis_id": "H_TEST",
                        "horizon_days": "3",
                        "epsilon_bps": "50",
                        "strategy": "pooled",
                        "model": "random_forest",
                    }
                )
            with (run_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            payload = export_payload(
                run_dir,
                {
                    "hypothesis_id": None,
                    "model": None,
                    "strategy": None,
                    "horizon_days": None,
                    "epsilon_bps": None,
                },
            )

        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["coverage"]["decisionCount"], 12)
        self.assertEqual(payload["coverage"]["signalCount"], 1)
        self.assertEqual(len(payload["signals"]), 1)
        signal = payload["signals"][0]
        self.assertTrue(signal["send"])
        self.assertEqual(signal["reasonCode"], "send")
        self.assertNotIn("notification", signal)
        self.assertNotIn("message_hit", signal)

    def test_requires_selector_for_ambiguous_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
            fields = [
                "date", "corridor", "rub_per_unit", "score", "candidate",
                "selected_signal", "threshold", "hypothesis_id", "horizon_days",
                "epsilon_bps", "strategy", "model",
            ]
            rows = [
                {
                    "date": "2026-01-01", "corridor": "RUB_TJS", "rub_per_unit": "9",
                    "score": "0.5", "candidate": "False", "selected_signal": "False",
                    "threshold": "0.8", "hypothesis_id": "H_TEST", "horizon_days": "3",
                    "epsilon_bps": "50", "strategy": "pooled", "model": model,
                }
                for model in ("logistic", "random_forest")
            ]
            with (run_dir / "predictions.csv").open("w", encoding="utf-8", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            with self.assertRaisesRegex(ValueError, "pass --model"):
                export_payload(
                    run_dir,
                    {
                        "hypothesis_id": None, "model": None, "strategy": None,
                        "horizon_days": None, "epsilon_bps": None,
                    },
                )


if __name__ == "__main__":
    unittest.main()
