"""Shared helpers for parsing, normalization, and file IO."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dir(path: Path) -> Path:
    """Create a directory if needed and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def eprint(message: str) -> None:
    """Print a user-facing warning or status line to stderr."""
    print(message, file=sys.stderr)


def parse_amount(value: Any) -> float | None:
    """Parse a currency-like value into a signed float.

    Handles common credit-card export formats such as ``$1,234.56``,
    ``(42.10)``, ``25.00 CR``, and blank cells.
    """
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()
    negative = False
    if "(" in text and ")" in text:
        negative = True
    if re.search(r"(^|[\s])cr(edit)?\.?$", lowered):
        negative = True
    if lowered.startswith("-") or lowered.endswith("-"):
        negative = True

    cleaned = (
        text.replace("$", "")
        .replace("£", "")
        .replace("€", "")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .replace("+", "")
    )
    cleaned = re.sub(r"(?i)\b(cr|credit|dr|debit)\b\.?", "", cleaned)
    cleaned = cleaned.replace("-", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None

    amount = float(match.group(0))
    return -amount if negative else amount


def parse_date(value: Any) -> pd.Timestamp | None:
    """Parse a date-like value into a pandas Timestamp, or None on failure."""
    if value is None or pd.isna(value):
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def normalize_text(value: Any) -> str:
    """Normalize text for matching while preserving readable words."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9&+./ -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_merchant(value: Any) -> str:
    """Build a stable merchant/description key for rules and caching."""
    text = normalize_text(value)
    text = re.sub(r"\b\d{4,}\b", " ", text)
    text = re.sub(
        r"\b(pos|purchase|auth|authorization|card|visa|mastercard|mc|online|"
        r"debit|credit|transaction|txn|ref|id|web)\b",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text or normalize_text(value)


def read_json(path: Path, default: Any) -> Any:
    """Read JSON from disk, returning a default value if missing or invalid."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically enough for a small local cache."""
    ensure_dir(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def format_money(value: float) -> str:
    """Format a numeric amount for reports."""
    return f"${value:,.2f}"

