"""Helpers for producing reports grouped by transaction month."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import AppConfig


def config_for_month_output(config: AppConfig, month: str) -> AppConfig:
    """Return a config copy that writes reports into output/YYYY-MM."""
    month_config = config.model_copy(deep=True)
    month_config.output_dir = config.output_dir / month
    month_config.classification_cache = config.classification_cache
    return month_config


def split_by_transaction_month(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split transactions into YYYY-MM groups based on the transaction date."""
    if df.empty:
        return {}

    work = df.copy()
    work["_report_month"] = pd.to_datetime(work["date"]).dt.to_period("M").astype(str)
    grouped: dict[str, pd.DataFrame] = {}
    for month, month_df in work.groupby("_report_month", sort=True):
        grouped[str(month)] = month_df.drop(columns=["_report_month"]).reset_index(drop=True)
    return grouped


def source_label(path: Path, root: Path | None = None) -> str:
    """Return a readable source path for reports."""
    if root is not None:
        try:
            return str(path.relative_to(root))
        except ValueError:
            pass
    return path.name

