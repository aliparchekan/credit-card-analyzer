"""Excel and Markdown report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .config import AppConfig
from .recommender import (
    format_recommendations,
    load_cards,
    monthly_spend_from_transactions,
    recommend,
    recommendations_table,
    eligible_spend_total,
)
from .utils import ensure_dir, format_money


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared["month"] = prepared["date"].dt.to_period("M").astype(str)
    prepared["spend_amount"] = prepared["amount"].where(prepared["amount"] > 0, 0.0)
    return prepared


def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize spend and net amount by category."""
    return (
        df.groupby("category", dropna=False)
        .agg(
            transactions=("amount", "size"),
            total_spend=("spend_amount", "sum"),
            net_amount=("amount", "sum"),
            average_transaction=("amount", "mean"),
        )
        .reset_index()
        .sort_values(["total_spend", "transactions"], ascending=[False, False])
    )


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize spend and net amount by month and category."""
    return (
        df.groupby(["month", "category"], dropna=False)
        .agg(
            transactions=("amount", "size"),
            total_spend=("spend_amount", "sum"),
            net_amount=("amount", "sum"),
        )
        .reset_index()
        .sort_values(["month", "total_spend"], ascending=[True, False])
    )


def merchant_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize spend and net amount by normalized merchant."""
    return (
        df.groupby(["merchant_key", "category"], dropna=False)
        .agg(
            example_description=("description", "first"),
            transactions=("amount", "size"),
            total_spend=("spend_amount", "sum"),
            net_amount=("amount", "sum"),
            average_amount=("amount", "mean"),
        )
        .reset_index()
        .sort_values(["total_spend", "transactions"], ascending=[False, False])
    )


def recurring_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Find merchants that appear repeatedly across months."""
    positive = df[df["amount"] > 0].copy()
    if positive.empty:
        return pd.DataFrame(
            columns=[
                "merchant_key",
                "category",
                "transactions",
                "active_months",
                "median_amount",
                "total_spend",
                "example_description",
            ]
        )

    grouped = (
        positive.groupby(["merchant_key", "category"], dropna=False)
        .agg(
            transactions=("amount", "size"),
            active_months=("month", "nunique"),
            median_amount=("amount", "median"),
            amount_std=("amount", "std"),
            total_spend=("spend_amount", "sum"),
            example_description=("description", "first"),
        )
        .reset_index()
    )
    candidates = grouped[
        ((grouped["transactions"] >= 2) & (grouped["active_months"] >= 2))
        | ((grouped["category"] == "Subscriptions") & (grouped["transactions"] >= 2))
    ]
    return candidates.sort_values(
        ["active_months", "transactions", "total_spend"], ascending=[False, False, False]
    )


def review_needed(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Return low-confidence or fallback classifications for manual review."""
    return df[(df["confidence"] < threshold) | (df["category"] == "Other")].sort_values(
        ["confidence", "date"], ascending=[True, False]
    )


def _autosize_workbook(writer: pd.ExcelWriter) -> None:
    for worksheet in writer.book.worksheets:
        worksheet.freeze_panes = "A2"
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
        for column_cells in worksheet.columns:
            values = [str(cell.value) for cell in column_cells if cell.value is not None]
            max_length = min(max([len(value) for value in values] + [10]) + 2, 60)
            worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = max_length


def generate_excel_report(df: pd.DataFrame, config: AppConfig) -> Path:
    """Generate the requested Excel workbook."""
    output_dir = ensure_dir(config.output_dir)
    prepared = _prepare(df)

    transactions = prepared.drop(columns=["spend_amount"], errors="ignore")
    cat = category_summary(prepared)
    monthly = monthly_summary(prepared)
    merchant = merchant_summary(prepared)
    review = review_needed(prepared, config.low_confidence_threshold)
    recurring = recurring_candidates(prepared)

    path = output_dir / "credit_card_report.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        transactions.to_excel(writer, sheet_name="Transactions", index=False)
        cat.to_excel(writer, sheet_name="Category Summary", index=False)
        monthly.to_excel(writer, sheet_name="Monthly Summary", index=False)
        merchant.to_excel(writer, sheet_name="Merchant Summary", index=False)
        review.to_excel(writer, sheet_name="Review Needed", index=False)
        recurring.to_excel(writer, sheet_name="Recurring Candidates", index=False)
        cards_data = load_cards(config.cards_file)
        spend = monthly_spend_from_transactions(df)
        recommendations_table(
            recommend(spend, cards_data), eligible_spend_total(spend, cards_data)
        ).to_excel(writer, sheet_name="Card Recommendations", index=False)
        _autosize_workbook(writer)
    return path


def _markdown_table(rows: Iterable[dict[str, object]], columns: list[str]) -> str:
    rows = list(rows)
    if not rows:
        return "_None found._"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join([header, separator, *body])


def _money_columns(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    formatted = df.copy()
    for column in columns:
        if column in formatted.columns:
            formatted[column] = formatted[column].astype(float).map(format_money)
    return formatted


def generate_markdown_report(df: pd.DataFrame, config: AppConfig) -> Path:
    """Generate the written Markdown report from computed tables only."""
    output_dir = ensure_dir(config.output_dir)
    prepared = _prepare(df)

    cat = _money_columns(category_summary(prepared).head(10), ("total_spend", "net_amount"))
    merchants = _money_columns(merchant_summary(prepared).head(10), ("total_spend", "net_amount"))
    recurring = _money_columns(
        recurring_candidates(prepared).head(10),
        ("median_amount", "total_spend"),
    )
    review = review_needed(prepared, config.low_confidence_threshold).head(25).copy()
    if not review.empty:
        review["date"] = pd.to_datetime(review["date"]).dt.date.astype(str)
        review["amount"] = review["amount"].astype(float).map(format_money)
        review["confidence"] = review["confidence"].astype(float).map(lambda value: f"{value:.2f}")

    total_spend = float(prepared["spend_amount"].sum()) if not prepared.empty else 0.0
    transaction_count = int(len(prepared))

    suggestions: list[str] = []
    if not cat.empty:
        top_category = str(cat.iloc[0]["category"])
        suggestions.append(
            f"- Largest computed spending category is {top_category}; review its top merchants first."
        )
    if not recurring.empty:
        suggestions.append(
            f"- {len(recurring)} recurring candidates were found; confirm which are active subscriptions."
        )
    if not review.empty:
        suggestions.append(
            f"- {len(review)} low-confidence transactions are listed for manual category review."
        )
    if not suggestions:
        suggestions.append("- No specific suggestions were generated from the computed tables.")

    content = "\n\n".join(
        [
            "# Credit Card Statement Report",
            (
                f"Analyzed {transaction_count} transactions with computed positive spend of "
                f"{format_money(total_spend)}."
            ),
            "## Top Spending Categories\n\n"
            + _markdown_table(
                cat[["category", "transactions", "total_spend", "net_amount"]].to_dict("records"),
                ["category", "transactions", "total_spend", "net_amount"],
            ),
            "## Top Merchants\n\n"
            + _markdown_table(
                merchants[
                    [
                        "merchant_key",
                        "category",
                        "transactions",
                        "total_spend",
                        "net_amount",
                    ]
                ].to_dict("records"),
                ["merchant_key", "category", "transactions", "total_spend", "net_amount"],
            ),
            "## Recurring / Subscription Candidates\n\n"
            + _markdown_table(
                recurring[
                    [
                        "merchant_key",
                        "category",
                        "transactions",
                        "active_months",
                        "median_amount",
                        "total_spend",
                    ]
                ].to_dict("records"),
                [
                    "merchant_key",
                    "category",
                    "transactions",
                    "active_months",
                    "median_amount",
                    "total_spend",
                ],
            ),
            "## Low-Confidence Transactions To Review\n\n"
            + _markdown_table(
                review[
                    [
                        "date",
                        "description",
                        "amount",
                        "category",
                        "confidence",
                        "reason",
                    ]
                ].to_dict("records"),
                ["date", "description", "amount", "category", "confidence", "reason"],
            ),
            "## Practical Suggestions\n\n" + "\n".join(suggestions),
            "## Credit Card Recommendations\n\n"
            + format_recommendations(
                monthly_spend_from_transactions(df), load_cards(config.cards_file)
            ),
        ]
    )

    path = output_dir / "written_report.md"
    path.write_text(content + "\n", encoding="utf-8")
    return path


def generate_reports(df: pd.DataFrame, config: AppConfig) -> tuple[Path, Path]:
    """Generate both Excel and Markdown reports."""
    return generate_excel_report(df, config), generate_markdown_report(df, config)

