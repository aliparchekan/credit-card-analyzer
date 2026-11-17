import unittest
from pathlib import Path

import pandas as pd

from src.recommender import (
    best_pair,
    evaluate_card,
    format_recommendations,
    load_cards,
    load_spend_file,
    monthly_spend_from_transactions,
    parse_spend_string,
    recommend,
    resolve_category,
)

ROOT = Path(__file__).resolve().parent.parent


class RecommenderTests(unittest.TestCase):
    def test_resolve_aliases(self):
        self.assertEqual(resolve_category("gas"), "Gas / EV Charging")
        self.assertEqual(resolve_category("Dining"), "Restaurants")
        self.assertEqual(resolve_category("phone / internet"), "Phone / Internet")
        with self.assertRaises(ValueError):
            resolve_category("spaceships")

    def test_parse_spend_string_merges_aliases(self):
        spend = parse_spend_string("groceries=600, food=50, gas=$150")
        self.assertEqual(spend, {"Groceries": 650.0, "Gas / EV Charging": 150.0})

    def test_load_example_spend_file(self):
        spend = load_spend_file(ROOT / "examples" / "monthly_spend.csv")
        self.assertEqual(spend["Groceries"], 650.0)
        self.assertEqual(spend["Rent / Housing"], 2100.0)

    def test_tier_cap_overflows_to_base_rate(self):
        card = {
            "name": "Test",
            "annual_fee": 0,
            "base_rate": 1.0,
            "tiers": [{"label": "Food", "categories": ["Groceries"], "rate": 5.0, "annual_cap": 6000}],
        }
        result = evaluate_card(card, {"Groceries": 1000})  # 12,000/yr
        self.assertAlmostEqual(result.annual_rewards, 6000 * 0.05 + 6000 * 0.01)

    def test_excluded_categories_earn_nothing(self):
        card = {"name": "Flat", "annual_fee": 0, "base_rate": 2.0, "tiers": []}
        result = evaluate_card(card, {"Rent / Housing": 2000, "Other": 100}, ["Rent / Housing"])
        self.assertAlmostEqual(result.annual_rewards, 24.0)

    def test_choose_categories_picks_highest_spend(self):
        card = {
            "name": "Pick",
            "annual_fee": 0,
            "base_rate": 0.5,
            "tiers": [],
            "choose": {
                "n": 1,
                "rate": 2.0,
                "options": {"Groceries": ["Groceries"], "Gas": ["Gas / EV Charging"]},
            },
        }
        result = evaluate_card(card, {"Groceries": 100, "Gas / EV Charging": 300})
        self.assertIn("Chosen: Gas", result.breakdown)

    def test_min_spend_marks_ineligible_and_ranks_last(self):
        data = {
            "cards": [
                {"name": "Big", "annual_fee": 0, "base_rate": 3.0, "tiers": [], "min_annual_spend": 100000},
                {"name": "Small", "annual_fee": 0, "base_rate": 1.0, "tiers": []},
            ]
        }
        results = recommend({"Other": 500}, data)
        self.assertEqual(results[0].name, "Small")
        self.assertFalse(results[1].eligible)

    def test_fee_reduces_net_value(self):
        data = {
            "cards": [
                {"name": "Fee", "annual_fee": 200, "base_rate": 2.0, "tiers": []},
                {"name": "Free", "annual_fee": 0, "base_rate": 1.0, "tiers": []},
            ]
        }
        self.assertEqual(recommend({"Other": 500}, data)[0].name, "Free")

    def test_best_pair_splits_categories(self):
        data = {
            "cards": [
                {"name": "Food", "annual_fee": 0, "base_rate": 0.5,
                 "tiers": [{"label": "Food", "categories": ["Groceries"], "rate": 5.0}]},
                {"name": "Flat", "annual_fee": 0, "base_rate": 2.0, "tiers": []},
            ]
        }
        pair = best_pair({"Groceries": 100, "Other": 100}, data)
        self.assertAlmostEqual(pair.annual_rewards, 1200 * 0.05 + 1200 * 0.02)

    def test_monthly_average_from_transactions(self):
        df = pd.DataFrame(
            {
                "date": ["2026-01-05", "2026-02-05", "2026-02-10"],
                "amount": [100.0, 300.0, -50.0],
                "category": ["Groceries", "Groceries", "Transfer / Payment"],
            }
        )
        self.assertEqual(monthly_spend_from_transactions(df), {"Groceries": 200.0})

    def test_bundled_card_data_is_valid(self):
        data = load_cards()
        self.assertGreater(len(data["cards"]), 5)
        for card in data["cards"]:
            for key in ("id", "name", "annual_fee", "base_rate", "tiers"):
                self.assertIn(key, card, card.get("id"))
        text = format_recommendations({"Groceries": 600, "Other": 400}, data)
        self.assertIn("Best single card", text)


if __name__ == "__main__":
    unittest.main()
