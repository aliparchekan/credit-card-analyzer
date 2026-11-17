"""Tests for monthly report grouping helpers."""

import unittest

import pandas as pd

from src.months import split_by_transaction_month


class MonthGroupingTests(unittest.TestCase):
    """Transaction-month grouping tests."""

    def test_split_by_transaction_month(self) -> None:
        transactions = pd.DataFrame(
            {
                "date": ["2026-01-31", "2026-02-01", "2026-02-15"],
                "description": ["A", "B", "C"],
                "amount": [10.0, 20.0, 30.0],
                "source_file": ["jan/card.csv", "feb/card.csv", "feb/card.csv"],
            }
        )

        grouped = split_by_transaction_month(transactions)

        self.assertEqual(list(grouped), ["2026-01", "2026-02"])
        self.assertEqual(len(grouped["2026-01"]), 1)
        self.assertEqual(len(grouped["2026-02"]), 2)
