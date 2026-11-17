"""Tests for amount/date parsing and CSV normalization."""

import unittest

import pandas as pd

from src.loaders import detect_columns, normalize_dataframe
from src.utils import parse_amount, parse_date


class NormalizationTests(unittest.TestCase):
    """Amount, date, and CSV normalization tests."""

    def test_parse_amount_common_formats(self) -> None:
        self.assertEqual(parse_amount("$1,234.56"), 1234.56)
        self.assertEqual(parse_amount("(42.10)"), -42.10)
        self.assertEqual(parse_amount("25.00 CR"), -25.00)
        self.assertIsNone(parse_amount(""))

    def test_parse_date_common_format(self) -> None:
        parsed = parse_date("2024-01-31")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(str(parsed.date()), "2024-01-31")

    def test_detect_and_normalize_debit_credit_columns(self) -> None:
        raw = pd.DataFrame(
            {
                "Transaction Date": ["2024-01-01", "2024-01-02"],
                "Transaction Details": ["Coffee Shop", "Payment Thank You"],
                "Debit": ["4.50", ""],
                "Credit": ["", "100.00"],
            }
        )

        columns = detect_columns(raw)
        self.assertEqual(columns["date"], "Transaction Date")
        self.assertEqual(columns["description"], "Transaction Details")
        self.assertEqual(columns["debit"], "Debit")
        self.assertEqual(columns["credit"], "Credit")

        normalized = normalize_dataframe(raw, "sample.csv")
        self.assertEqual(list(normalized["amount"]), [4.5, -100.0])
        self.assertEqual(list(normalized["source_file"]), ["sample.csv", "sample.csv"])
