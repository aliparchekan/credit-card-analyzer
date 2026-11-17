"""Deterministic merchant keyword rules for transaction classification."""

from __future__ import annotations

from dataclasses import dataclass

from .utils import normalize_merchant


CATEGORIES: tuple[str, ...] = (
    "Groceries",
    "Restaurants",
    "Coffee",
    "Gas / EV Charging",
    "Car / Insurance",
    "Rent / Housing",
    "Utilities",
    "Phone / Internet",
    "Shopping",
    "Travel",
    "Subscriptions",
    "Health",
    "Education",
    "Business / Work",
    "Financial Fees",
    "Transfer / Payment",
    "Other",
)


@dataclass(frozen=True)
class RuleMatch:
    """Classification result from deterministic rules."""

    category: str
    confidence: float
    reason: str


MERCHANT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Groceries": (
        "whole foods",
        "trader joe",
        "costco",
        "walmart grocery",
        "loblaws",
        "metro",
        "safeway",
        "sobeys",
        "no frills",
        "superstore",
        "food basics",
        "farm boy",
        "freshco",
        "instacart",
        "grocery",
        "supermarket",
    ),
    "Restaurants": (
        "restaurant",
        "grill",
        "pizza",
        "burger",
        "doordash",
        "uber eats",
        "ubereats",
        "skip the dishes",
        "takeout",
        "taco",
        "sushi",
        "kitchen",
        "bar ",
        "pub ",
    ),
    "Coffee": (
        "starbucks",
        "tim hortons",
        "dunkin",
        "peets",
        "coffee",
        "espresso",
        "cafe",
    ),
    "Gas / EV Charging": (
        "shell",
        "chevron",
        "esso",
        "petro-canada",
        "petro canada",
        "mobil",
        "exxon",
        "bp ",
        "gas ",
        "fuel",
        "chargepoint",
        "tesla supercharger",
        "flo ev",
        "electrify",
    ),
    "Car / Insurance": (
        "insurance",
        "geico",
        "progressive",
        "state farm",
        "allstate",
        "td insurance",
        "auto",
        "parking",
        "toll",
        "407 etr",
        "car wash",
        "mechanic",
        "service center",
    ),
    "Rent / Housing": (
        "rent",
        "landlord",
        "property management",
        "mortgage",
        "condo fee",
        "hoa",
        "apartment",
    ),
    "Utilities": (
        "hydro",
        "electric",
        "utility",
        "utilities",
        "water",
        "gas bill",
        "enbridge",
        "aep",
        "coned",
        "pg&e",
    ),
    "Phone / Internet": (
        "verizon",
        "at&t",
        "t-mobile",
        "tmobile",
        "rogers",
        "bell",
        "telus",
        "fido",
        "comcast",
        "xfinity",
        "spectrum",
        "internet",
        "phone bill",
    ),
    "Shopping": (
        "amazon",
        "target",
        "walmart",
        "best buy",
        "apple store",
        "ikea",
        "etsy",
        "shopify",
        "paypal",
        "ebay",
        "store",
        "retail",
    ),
    "Travel": (
        "air canada",
        "delta",
        "united airlines",
        "american airlines",
        "southwest",
        "airbnb",
        "hotel",
        "marriott",
        "hilton",
        "expedia",
        "booking.com",
        "uber trip",
        "lyft",
        "transit",
        "train",
        "airport",
    ),
    "Subscriptions": (
        "netflix",
        "spotify",
        "apple.com/bill",
        "icloud",
        "youtube",
        "google storage",
        "dropbox",
        "notion",
        "github",
        "openai",
        "chatgpt",
        "adobe",
        "microsoft 365",
        "prime membership",
        "subscription",
    ),
    "Health": (
        "pharmacy",
        "cvs",
        "walgreens",
        "doctor",
        "clinic",
        "hospital",
        "dentist",
        "optical",
        "therapy",
        "medical",
    ),
    "Education": (
        "tuition",
        "university",
        "college",
        "coursera",
        "udemy",
        "edx",
        "school",
        "textbook",
    ),
    "Business / Work": (
        "office depot",
        "staples",
        "aws",
        "amazon web services",
        "google cloud",
        "slack",
        "zoom",
        "linkedin",
        "domain",
        "hosting",
        "software",
    ),
    "Financial Fees": (
        "annual fee",
        "interest charge",
        "cash advance fee",
        "foreign transaction fee",
        "late fee",
        "service fee",
        "finance charge",
        "overlimit fee",
    ),
    "Transfer / Payment": (
        "payment",
        "autopay",
        "auto pay",
        "thank you",
        "thankyou",
        "transfer",
        "bill payment",
        "online payment",
        "credit card payment",
        "refund",
        "return",
    ),
}


def match_rule(description: str) -> RuleMatch | None:
    """Return a deterministic category when a merchant keyword matches."""
    merchant = normalize_merchant(description)
    padded = f" {merchant} "
    for category, keywords in MERCHANT_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize_merchant(keyword)
            if not normalized_keyword:
                continue
            if normalized_keyword in padded or normalized_keyword in merchant:
                return RuleMatch(
                    category=category,
                    confidence=0.95,
                    reason=f"Matched keyword rule: {keyword}",
                )
    return None


def is_valid_category(category: str) -> bool:
    """Check whether a category is part of the supported taxonomy."""
    return category in CATEGORIES

