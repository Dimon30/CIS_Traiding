from datetime import date
from decimal import Decimal
import unittest

from scripts.build_dataset import RateObservation, build_label_rows


def observation(day: int, rate: str) -> RateObservation:
    value = Decimal(rate)
    return RateObservation(
        effective_date=date(2026, 1, day),
        nominal=1,
        value_rub=value,
        rub_per_unit=value,
    )


class BuildLabelRowsTest(unittest.TestCase):
    def test_good_day_when_future_improvement_is_within_epsilon(self) -> None:
        observations = [
            observation(1, "10.0"),
            observation(2, "9.8"),
            observation(3, "9.7"),
            observation(4, "9.66"),
            observation(5, "9.7"),
        ]

        rows = build_label_rows(
            observations,
            horizon=1,
            epsilon=Decimal("0.005"),
            corridor="RUB_TJS",
        )

        self.assertEqual(rows[2]["target_good_now"], 1)
        self.assertEqual(rows[2]["message_hit"], 1)

    def test_false_message_when_future_rate_is_more_than_epsilon_better(self) -> None:
        observations = [
            observation(1, "10.0"),
            observation(2, "9.9"),
            observation(3, "9.8"),
            observation(4, "9.0"),
            observation(5, "9.1"),
        ]

        rows = build_label_rows(
            observations,
            horizon=1,
            epsilon=Decimal("0.005"),
            corridor="RUB_TJS",
        )

        self.assertEqual(rows[2]["target_good_now"], 0)
        self.assertEqual(rows[2]["message_hit"], 0)

    def test_edge_rows_are_not_labeled_without_full_window(self) -> None:
        observations = [observation(1, "10"), observation(2, "9"), observation(3, "8")]

        rows = build_label_rows(
            observations,
            horizon=1,
            epsilon=Decimal("0.005"),
            corridor="RUB_TJS",
        )

        self.assertFalse(rows[0]["has_full_window"])
        self.assertEqual(rows[0]["target_good_now"], "")
        self.assertFalse(rows[-1]["has_full_window"])


if __name__ == "__main__":
    unittest.main()
