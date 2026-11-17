"""Recommend credit cards from monthly spending by category.

Card definitions live in ``data/cards.json``. Every rate is a percent
cash-equivalent return, so cash-back and points cards can be compared directly.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from .rules import CATEGORIES

DEFAULT_CARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "cards.json"

# Short names people are likely to type, mapped to analyzer categories.
CATEGORY_ALIASES: dict[str, str] = {
    "grocery": "Groceries",
    "groceries": "Groceries",
    "food": "Groceries",
    "restaurant": "Restaurants",
    "restaurants": "Restaurants",
    "dining": "Restaurants",
    "eating out": "Restaurants",
    "takeout": "Restaurants",
    "coffee": "Coffee",
    "gas": "Gas / EV Charging",
    "fuel": "Gas / EV Charging",
    "ev": "Gas / EV Charging",
    "ev charging": "Gas / EV Charging",
    "car": "Car / Insurance",
    "insurance": "Car / Insurance",
    "rent": "Rent / Housing",
    "housing": "Rent / Housing",
    "mortgage": "Rent / Housing",
    "utilities": "Utilities",
    "hydro": "Utilities",
    "phone": "Phone / Internet",
    "internet": "Phone / Internet",
    "shopping": "Shopping",
    "retail": "Shopping",
    "travel": "Travel",
    "transit": "Travel",
    "subscriptions": "Subscriptions",
    "streaming": "Subscriptions",
    "health": "Health",
    "pharmacy": "Health",
    "drugstore": "Health",
    "education": "Education",
    "business": "Business / Work",
    "work": "Business / Work",
    "fees": "Financial Fees",
    "other": "Other",
}


@dataclass
class CardResult:
    """Yearly value of one card (or card pair) for a spending profile."""

    name: str
    annual_rewards: float
    annual_fee: float
    eligible: bool = True
    breakdown: dict[str, float] = field(default_factory=dict)
    notes: str = ""

    @property
    def net_value(self) -> float:
        return self.annual_rewards - self.annual_fee


def resolve_category(name: str) -> str:
    """Map user input like ``gas`` or ``Restaurants`` to an analyzer category."""
    text = " ".join(name.strip().lower().replace("_", " ").split())
    for category in CATEGORIES:
        if text == category.lower():
            return category
    if text in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[text]
    matches = [category for category in CATEGORIES if category.lower().startswith(text)]
    if len(matches) == 1:
        return matches[0]
    known = ", ".join(sorted(set(CATEGORY_ALIASES) | {c.lower() for c in CATEGORIES}))
    raise ValueError(f"Unknown spending category {name!r}. Known names: {known}")


def _add_spend(spend: dict[str, float], name: str, amount: float) -> None:
    if amount < 0:
        raise ValueError(f"Monthly spend for {name!r} cannot be negative")
    category = resolve_category(name)
    spend[category] = spend.get(category, 0.0) + float(amount)


def parse_spend_string(text: str) -> dict[str, float]:
    """Parse ``"groceries=600, gas=150"`` into monthly spend by category."""
    spend: dict[str, float] = {}
    for part in text.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"Expected category=amount, got {part.strip()!r}")
        name, value = part.split("=", 1)
        _add_spend(spend, name, float(value.strip().replace("$", "")))
    return spend


def load_spend_file(path: Path) -> dict[str, float]:
    """Load monthly spend from a CSV (category,monthly_amount) or ``key: value`` file."""
    text = path.read_text(encoding="utf-8")
    spend: dict[str, float] = {}
    if path.suffix.lower() == ".csv":
        for row in csv.reader(text.splitlines()):
            if len(row) < 2 or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            try:
                amount = float(row[1].strip().replace("$", "").replace(",", ""))
            except ValueError:
                continue  # header row
            _add_spend(spend, row[0], amount)
        return spend
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Expected 'category: amount', got {line!r}")
        name, value = line.split(":", 1)
        _add_spend(spend, name, float(value.strip().replace("$", "").replace(",", "")))
    return spend


def monthly_spend_from_transactions(df: pd.DataFrame) -> dict[str, float]:
    """Average monthly positive spend per category from classified transactions."""
    if df.empty:
        return {}
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    purchases = work[work["amount"] > 0]
    if purchases.empty:
        return {}
    months = max(1, purchases["date"].dt.to_period("M").nunique())
    totals = purchases.groupby("category")["amount"].sum() / months
    return {str(category): float(value) for category, value in totals.items()}


def load_cards(path: Path | None = None) -> dict[str, Any]:
    """Load card definitions from JSON."""
    return json.loads((path or DEFAULT_CARDS_PATH).read_text(encoding="utf-8"))


def _rate_for(card: Mapping[str, Any], category: str) -> float:
    """Best headline rate a card offers for a category (ignores caps)."""
    rate = float(card["base_rate"])
    for tier in card.get("tiers", []):
        if category in tier["categories"]:
            rate = max(rate, float(tier["rate"]))
    choose = card.get("choose")
    if choose:
        for categories in choose["options"].values():
            if category in categories:
                rate = max(rate, float(choose["rate"]))
    return rate


def _chosen_tiers(card: Mapping[str, Any], annual: Mapping[str, float]) -> list[dict[str, Any]]:
    """Turn a pick-your-categories card into fixed tiers using the best picks."""
    choose = card.get("choose")
    if not choose:
        return []
    ranked = sorted(
        choose["options"].items(),
        key=lambda item: sum(annual.get(category, 0.0) for category in item[1]),
        reverse=True,
    )
    picks = [(label, cats) for label, cats in ranked[: int(choose["n"])]]
    return [
        {"label": f"Chosen: {label}", "categories": cats, "rate": choose["rate"]}
        for label, cats in picks
        if sum(annual.get(category, 0.0) for category in cats) > 0
    ]


def evaluate_card(
    card: Mapping[str, Any],
    monthly_spend: Mapping[str, float],
    excluded: Iterable[str] = (),
) -> CardResult:
    """Compute yearly rewards for one card, applying tier caps in rate order."""
    excluded = set(excluded)
    annual = {
        category: amount * 12
        for category, amount in monthly_spend.items()
        if category not in excluded and amount > 0
    }
    remaining = dict(annual)
    base = float(card["base_rate"])
    breakdown: dict[str, float] = {}

    tiers = list(card.get("tiers", [])) + _chosen_tiers(card, annual)
    for tier in sorted(tiers, key=lambda t: float(t["rate"]), reverse=True):
        cap = tier.get("annual_cap")
        room = float(cap) if cap is not None else float("inf")
        rate = float(tier["rate"])
        if rate <= base:
            continue
        for category in tier["categories"]:
            amount = min(remaining.get(category, 0.0), room)
            if amount <= 0:
                continue
            remaining[category] -= amount
            room -= amount
            breakdown[tier["label"]] = breakdown.get(tier["label"], 0.0) + amount * rate / 100

    leftover = sum(remaining.values())
    if leftover > 0:
        breakdown["Everything else"] = leftover * base / 100

    total_annual = sum(annual.values())
    min_spend = float(card.get("min_annual_spend", 0))
    eligible = total_annual >= min_spend
    notes = str(card.get("notes", ""))
    if not eligible:
        notes = f"Needs ${min_spend:,.0f}/yr card spend (you have ${total_annual:,.0f}). " + notes

    return CardResult(
        name=card["name"],
        annual_rewards=round(sum(breakdown.values()), 2),
        annual_fee=float(card["annual_fee"]),
        eligible=eligible,
        breakdown={label: round(value, 2) for label, value in breakdown.items()},
        notes=notes,
    )


def recommend(
    monthly_spend: Mapping[str, float],
    cards_data: Mapping[str, Any] | None = None,
) -> list[CardResult]:
    """Rank every card by yearly net value (rewards minus annual fee)."""
    data = cards_data or load_cards()
    excluded = data.get("excluded_categories", [])
    results = [evaluate_card(card, monthly_spend, excluded) for card in data["cards"]]
    return sorted(results, key=lambda r: (r.eligible, r.net_value), reverse=True)


def best_pair(
    monthly_spend: Mapping[str, float],
    cards_data: Mapping[str, Any] | None = None,
) -> CardResult | None:
    """Best two-card combination: each category goes on the card with the higher rate."""
    data = cards_data or load_cards()
    excluded = set(data.get("excluded_categories", []))
    cards = data["cards"]
    total_annual = sum(v * 12 for k, v in monthly_spend.items() if k not in excluded and v > 0)
    best: CardResult | None = None
    for first, second in combinations(cards, 2):
        split: tuple[dict[str, float], dict[str, float]] = ({}, {})
        for category, amount in monthly_spend.items():
            target = 0 if _rate_for(first, category) >= _rate_for(second, category) else 1
            split[target][category] = amount
        a = evaluate_card(first, split[0], excluded)
        b = evaluate_card(second, split[1], excluded)
        # Minimum-spend rules apply to all spend on the card, so check against its share.
        if not (a.eligible and b.eligible):
            continue
        if not split[0] or not split[1]:
            continue  # one card would sit unused
        combo = CardResult(
            name=f"{first['name']} + {second['name']}",
            annual_rewards=round(a.annual_rewards + b.annual_rewards, 2),
            annual_fee=a.annual_fee + b.annual_fee,
            breakdown={
                **{f"{first['name']}: {k}": v for k, v in a.breakdown.items()},
                **{f"{second['name']}: {k}": v for k, v in b.breakdown.items()},
            },
            notes="Use each card for the categories it earns most on.",
        )
        if best is None or combo.net_value > best.net_value:
            best = combo
    if best is not None and total_annual <= 0:
        return None
    return best


def recommendations_table(results: list[CardResult], monthly_total: float) -> pd.DataFrame:
    """Tabulate ranked results for Excel output."""
    annual_total = monthly_total * 12
    rows = []
    for rank, result in enumerate(results, start=1):
        rows.append(
            {
                "rank": rank,
                "card": result.name,
                "annual_rewards": result.annual_rewards,
                "annual_fee": result.annual_fee,
                "net_value": round(result.net_value, 2),
                "effective_rate_pct": round(100 * result.net_value / annual_total, 2)
                if annual_total
                else 0.0,
                "eligible": result.eligible,
                "notes": result.notes,
            }
        )
    return pd.DataFrame(rows)


def eligible_spend_total(monthly_spend: Mapping[str, float], cards_data: Mapping[str, Any] | None = None) -> float:
    """Monthly spend that can go on a card (excludes rent, transfers, fees)."""
    data = cards_data or load_cards()
    excluded = set(data.get("excluded_categories", []))
    return sum(v for k, v in monthly_spend.items() if k not in excluded and v > 0)


def format_recommendations(
    monthly_spend: Mapping[str, float],
    cards_data: Mapping[str, Any] | None = None,
    top: int = 5,
) -> str:
    """Markdown summary of the best cards for a spending profile."""
    data = cards_data or load_cards()
    results = recommend(monthly_spend, data)
    pair = best_pair(monthly_spend, data)
    monthly_total = eligible_spend_total(monthly_spend, data)
    lines = [
        f"Based on about ${monthly_total:,.0f}/month of card-eligible spending "
        f"(${monthly_total * 12:,.0f}/year).",
        "",
        "| Rank | Card | Rewards/yr | Fee/yr | Net/yr |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rank, result in enumerate(results[:top], start=1):
        flag = "" if result.eligible else " (not eligible)"
        lines.append(
            f"| {rank} | {result.name}{flag} | ${result.annual_rewards:,.2f} | "
            f"${result.annual_fee:,.2f} | ${result.net_value:,.2f} |"
        )
    if results:
        top_card = results[0]
        lines += ["", f"**Best single card: {top_card.name}**", ""]
        for label, value in sorted(top_card.breakdown.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {label}: ${value:,.2f}/yr")
        if top_card.notes:
            lines += ["", f"_Note: {top_card.notes}_"]
    if pair and results and pair.net_value > results[0].net_value + 1:
        lines += [
            "",
            f"**Best two-card setup: {pair.name}** — ${pair.net_value:,.2f}/yr net "
            f"(${pair.net_value - results[0].net_value:,.2f} more than the best single card).",
        ]
    lines += [
        "",
        f"_Earn rates are approximate (card data last reviewed {data.get('last_reviewed', 'n/a')}); "
        "points are valued at 1 cent. Check the issuer's site before applying. "
        "This is an estimate, not financial advice._",
    ]
    return "\n".join(lines)
