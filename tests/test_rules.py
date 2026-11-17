"""Tests for deterministic merchant rules."""

import unittest

from src.rules import match_rule


class RuleTests(unittest.TestCase):
    """Merchant keyword rule tests."""

    def test_common_merchant_rules(self) -> None:
        cases = {
            "STARBUCKS STORE 123": "Coffee",
            "SHELL OIL 0456": "Gas / EV Charging",
            "NETFLIX.COM": "Subscriptions",
            "ONLINE PAYMENT THANK YOU": "Transfer / Payment",
            "WHOLE FOODS MARKET": "Groceries",
        }

        for description, expected_category in cases.items():
            with self.subTest(description=description):
                match = match_rule(description)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(match.category, expected_category)
