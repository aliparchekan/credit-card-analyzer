"""Command-line entrypoint for the local credit card analyzer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .classifier import classify_transactions
from .config import AppConfig, load_config
from .loaders import csv_files_in, csv_files_under, load_csv_files
from .months import config_for_month_output, split_by_transaction_month
from .pdf_extract import PDF_REVIEW_WARNING, extract_pdfs, extract_pdfs_to_csv
from .recommender import (
    format_recommendations,
    load_cards,
    load_spend_file,
    monthly_spend_from_transactions,
    parse_spend_string,
)
from .reports import generate_reports
from .utils import ensure_dir, eprint


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    config = load_config(args.config)
    if args.input_dir:
        config.input_dir = Path(args.input_dir)
    if args.output_dir:
        config.output_dir = Path(args.output_dir)
        config.classification_cache = config.output_dir / config.classification_cache.name
    return config


def _csv_paths_for_analysis(config: AppConfig, include_extracted: bool) -> list[Path]:
    paths = csv_files_in(config.input_dir)
    if include_extracted:
        paths.extend(csv_files_in(config.output_dir / "extracted_csv"))
    unique = sorted({path.resolve(): path for path in paths}.values())
    return unique


def _csv_paths_for_monthly_analysis(config: AppConfig, include_extracted: bool) -> list[Path]:
    paths = csv_files_under(config.input_dir)
    if include_extracted:
        paths.extend(csv_files_under(config.output_dir / "extracted_csv"))
    unique = sorted({path.resolve(): path for path in paths}.values())
    return unique


def analyze_csv(config: AppConfig, include_extracted: bool = False) -> tuple[Path, Path]:
    """Load CSVs, classify transactions, and write reports."""
    ensure_dir(config.output_dir)
    paths = _csv_paths_for_analysis(config, include_extracted=include_extracted)
    if not paths:
        locations = [str(config.input_dir)]
        if include_extracted:
            locations.append(str(config.output_dir / "extracted_csv"))
        raise SystemExit(
            "No CSV files found. Put statement CSV files in: " + ", ".join(locations)
        )

    eprint(f"Loading {len(paths)} CSV file(s).")
    normalized = load_csv_files(paths)
    if normalized.empty:
        raise SystemExit("CSV files were read, but no valid transactions were found.")

    eprint(f"Classifying {len(normalized)} transaction(s).")
    classified = classify_transactions(normalized, config)

    eprint("Generating reports.")
    return generate_reports(classified, config)


def analyze_months(config: AppConfig, include_extracted: bool = False) -> dict[str, tuple[Path, Path]]:
    """Analyze CSVs recursively and write one report pair per transaction month."""
    ensure_dir(config.output_dir)
    paths = _csv_paths_for_monthly_analysis(config, include_extracted=include_extracted)
    if not paths:
        locations = [str(config.input_dir)]
        if include_extracted:
            locations.append(str(config.output_dir / "extracted_csv"))
        raise SystemExit(
            "No CSV files found. Put monthly statement CSV files under: "
            + ", ".join(locations)
        )

    eprint(f"Loading {len(paths)} CSV file(s) recursively for monthly reports.")
    normalized = load_csv_files(paths, source_root=config.input_dir)
    if normalized.empty:
        raise SystemExit("CSV files were read, but no valid transactions were found.")

    eprint(f"Classifying {len(normalized)} transaction(s).")
    classified = classify_transactions(normalized, config)
    monthly = split_by_transaction_month(classified)
    if not monthly:
        raise SystemExit("No transaction months were found after normalization.")

    reports: dict[str, tuple[Path, Path]] = {}
    for month, month_df in monthly.items():
        month_config = config_for_month_output(config, month)
        eprint(f"Generating reports for {month} with {len(month_df)} transaction(s).")
        reports[month] = generate_reports(month_df, month_config)
    return reports


def extract_pdf(config: AppConfig) -> list[Path]:
    """Extract PDF tables to CSV for manual review."""
    ensure_dir(config.output_dir)
    eprint(PDF_REVIEW_WARNING)
    try:
        output_paths = extract_pdfs(config.input_dir, config.output_dir)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if not output_paths:
        raise SystemExit(f"No tables extracted. Put PDF statement files in {config.input_dir}.")
    return output_paths


def extract_pdf_months(config: AppConfig) -> list[Path]:
    """Extract PDF tables recursively for monthly upload folders."""
    ensure_dir(config.output_dir)
    eprint(PDF_REVIEW_WARNING)
    try:
        output_paths = extract_pdfs_to_csv(config.input_dir, config.output_dir, recursive=True)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if not output_paths:
        raise SystemExit(
            f"No tables extracted. Put PDF statement files under {config.input_dir}."
        )
    return output_paths


def recommend_cards(config: AppConfig, spend_text: str | None, spend_file: str | None, top: int) -> str:
    """Recommend cards from typed-in monthly spend, a spend file, or statements in input/."""
    try:
        if spend_text or spend_file:
            spend: dict[str, float] = {}
            if spend_file:
                spend.update(load_spend_file(Path(spend_file)))
            if spend_text:
                for category, amount in parse_spend_string(spend_text).items():
                    spend[category] = spend.get(category, 0.0) + amount
        else:
            paths = _csv_paths_for_analysis(config, include_extracted=True)
            if not paths:
                raise SystemExit(
                    "Give your monthly spending with --spend 'groceries=600,gas=150' or "
                    f"--spend-file, or put statement CSVs in {config.input_dir}."
                )
            eprint(f"Estimating monthly spending from {len(paths)} statement CSV file(s).")
            normalized = load_csv_files(paths)
            if normalized.empty:
                raise SystemExit("CSV files were read, but no valid transactions were found.")
            spend = monthly_spend_from_transactions(classify_transactions(normalized, config))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if not any(amount > 0 for amount in spend.values()):
        raise SystemExit("No positive monthly spending was found.")
    return format_recommendations(spend, load_cards(config.cards_file), top=top)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Analyze credit card statements locally from CSV and best-effort PDF tables.",
    )
    parser.add_argument("--config", default="config.example.yaml", help="Path to config YAML.")
    parser.add_argument("--input-dir", help="Override input directory.")
    parser.add_argument("--output-dir", help="Override output directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("analyze-csv", help="Analyze CSV files in input/.")
    subparsers.add_parser(
        "analyze-months",
        help="Analyze CSV files recursively and create one report per transaction month.",
    )
    subparsers.add_parser("extract-pdf", help="Extract PDF tables into output/extracted_csv/.")
    subparsers.add_parser(
        "extract-pdf-months",
        help="Extract PDF tables recursively for monthly upload folders.",
    )
    subparsers.add_parser(
        "analyze-all",
        help="Extract PDFs, then analyze input CSVs and extracted CSVs.",
    )
    subparsers.add_parser(
        "analyze-all-months",
        help="Extract PDFs recursively, then create one report per transaction month.",
    )
    recommend_parser = subparsers.add_parser(
        "recommend",
        help="Suggest credit cards from monthly spending (typed in, from a file, or from statements).",
    )
    recommend_parser.add_argument(
        "--spend",
        help="Monthly spend, e.g. 'groceries=600,restaurants=250,gas=150,other=400'.",
    )
    recommend_parser.add_argument(
        "--spend-file",
        help="CSV (category,monthly_amount) or 'category: amount' text file.",
    )
    recommend_parser.add_argument("--top", type=int, default=5, help="How many cards to list.")
    return parser


def _print_monthly_reports(reports: dict[str, tuple[Path, Path]]) -> None:
    print("Monthly reports:")
    for month, (excel_path, markdown_path) in reports.items():
        print(f"- {month}")
        print(f"  Excel report: {excel_path}")
        print(f"  Markdown report: {markdown_path}")


def main(argv: list[str] | None = None) -> int:
    """Run the selected CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _config_from_args(args)

    if args.command == "extract-pdf":
        paths = extract_pdf(config)
        print("Extracted CSV files:")
        for path in paths:
            print(f"- {path}")
        print(PDF_REVIEW_WARNING)
        return 0

    if args.command == "extract-pdf-months":
        paths = extract_pdf_months(config)
        print("Extracted CSV files:")
        for path in paths:
            print(f"- {path}")
        print(PDF_REVIEW_WARNING)
        return 0

    if args.command == "recommend":
        print(recommend_cards(config, args.spend, args.spend_file, args.top))
        return 0

    if args.command == "analyze-months":
        reports = analyze_months(config, include_extracted=False)
        _print_monthly_reports(reports)
        return 0

    if args.command == "analyze-all-months":
        try:
            extracted = extract_pdf_months(config)
            eprint(f"Extracted {len(extracted)} CSV file(s) from PDFs.")
        except SystemExit as exc:
            eprint(str(exc))
            eprint("Continuing with CSV analysis only.")
        reports = analyze_months(config, include_extracted=True)
        _print_monthly_reports(reports)
        return 0

    if args.command == "analyze-csv":
        excel_path, markdown_path = analyze_csv(config, include_extracted=False)
    elif args.command == "analyze-all":
        try:
            extracted = extract_pdf(config)
            eprint(f"Extracted {len(extracted)} CSV file(s) from PDFs.")
        except SystemExit as exc:
            eprint(str(exc))
            eprint("Continuing with CSV analysis only.")
        excel_path, markdown_path = analyze_csv(config, include_extracted=True)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    print(f"Excel report: {excel_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
