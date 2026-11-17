"""CSV loading and statement normalization."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .months import source_label
from .utils import parse_amount, parse_date


DATE_CANDIDATES = (
    "date",
    "transaction date",
    "posted date",
    "post date",
    "posting date",
    "trans date",
)
DESCRIPTION_CANDIDATES = (
    "description",
    "merchant",
    "transaction details",
    "transaction detail",
    "details",
    "name",
    "payee",
    "memo",
)
AMOUNT_CANDIDATES = (
    "amount",
    "transaction amount",
    "cad$",
    "usd$",
    "charge",
    "charges",
    "purchase amount",
)
DEBIT_CANDIDATES = ("debit", "debits", "withdrawal", "withdrawals", "charge", "charges")
CREDIT_CANDIDATES = ("credit", "credits", "payment", "payments", "deposit", "deposits")


def _canonical_header(header: object) -> str:
    return " ".join(str(header).lower().replace("_", " ").replace("-", " ").split())


def _find_column(columns: Iterable[object], candidates: Iterable[str]) -> str | None:
    normalized = {_canonical_header(column): str(column) for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for normalized_name, original in normalized.items():
        for candidate in candidates:
            if candidate in normalized_name:
                return original
    return None


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    """Detect common date, description, amount, debit, and credit columns."""
    columns = df.columns
    return {
        "date": _find_column(columns, DATE_CANDIDATES),
        "description": _find_column(columns, DESCRIPTION_CANDIDATES),
        "amount": _find_column(columns, AMOUNT_CANDIDATES),
        "debit": _find_column(columns, DEBIT_CANDIDATES),
        "credit": _find_column(columns, CREDIT_CANDIDATES),
    }


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV using common encodings."""
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"Could not read CSV {path}. Encoding errors: {'; '.join(errors)}")


def normalize_dataframe(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """Normalize a raw statement DataFrame to date, description, amount, source_file."""
    if df.empty:
        return pd.DataFrame(columns=["date", "description", "amount", "source_file"])

    columns = detect_columns(df)
    missing = [name for name in ("date", "description") if not columns[name]]
    if missing:
        raise ValueError(
            f"{source_file}: missing required column(s): {', '.join(missing)}. "
            "Expected common headers like Date, Description/Merchant, and Amount."
        )

    amount_col = columns["amount"]
    debit_col = columns["debit"]
    credit_col = columns["credit"]
    if not amount_col and not (debit_col or credit_col):
        raise ValueError(
            f"{source_file}: missing amount column. Expected Amount or Debit/Credit columns."
        )

    normalized = pd.DataFrame()
    normalized["date"] = df[columns["date"]].apply(parse_date)
    normalized["description"] = df[columns["description"]].astype(str).str.strip()

    if debit_col or credit_col:
        debit = (
            df[debit_col].apply(parse_amount).fillna(0).abs()
            if debit_col
            else pd.Series(0.0, index=df.index)
        )
        credit = (
            df[credit_col].apply(parse_amount).fillna(0).abs()
            if credit_col
            else pd.Series(0.0, index=df.index)
        )
        normalized["amount"] = debit - credit
    else:
        normalized["amount"] = df[amount_col].apply(parse_amount)

    normalized["source_file"] = source_file
    normalized = normalized.dropna(subset=["date", "amount"])
    normalized = normalized[normalized["description"].str.len() > 0]
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    normalized["amount"] = normalized["amount"].astype(float)
    return normalized.reset_index(drop=True)


def csv_files_in(directory: Path) -> list[Path]:
    """Return CSV files directly inside a directory."""
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.csv") if path.is_file())


def csv_files_under(directory: Path) -> list[Path]:
    """Return CSV files anywhere under a directory."""
    if not directory.exists():
        return []
    return sorted(path for path in directory.rglob("*.csv") if path.is_file())


def load_csv_files(paths: Iterable[Path], source_root: Path | None = None) -> pd.DataFrame:
    """Load and normalize one or more CSV paths."""
    frames: list[pd.DataFrame] = []
    failures: list[str] = []
    for path in paths:
        try:
            raw = _read_csv(path)
            frames.append(normalize_dataframe(raw, source_label(path, source_root)))
        except Exception as exc:  # noqa: BLE001 - report all file-level failures clearly.
            failures.append(f"- {path}: {exc}")

    if failures:
        raise ValueError("Some CSV files could not be loaded:\n" + "\n".join(failures))
    if not frames:
        return pd.DataFrame(columns=["date", "description", "amount", "source_file"])
    return pd.concat(frames, ignore_index=True)
