"""Best-effort PDF statement table extraction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import ensure_dir


PDF_REVIEW_WARNING = (
    "PDF extraction is best-effort and requires manual review. "
    "Inspect extracted CSV files before relying on the analysis."
)


def _make_unique_headers(headers: list[object], width: int) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        raw = headers[index] if index < len(headers) else None
        name = str(raw).strip() if raw not in (None, "") else f"column_{index + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}_{count + 1}"
        names.append(name)
    return names


def extract_pdf_tables(pdf_path: Path, extracted_dir: Path) -> list[Path]:
    """Extract tables from one PDF statement into CSV files."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "pdfplumber is required for PDF extraction. Install dependencies with "
            "'pip install -r requirements.txt'."
        ) from exc

    ensure_dir(extracted_dir)
    output_paths: list[Path] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            for table_number, table in enumerate(tables, start=1):
                rows = [
                    [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    for row in table
                    if row and any(cell not in (None, "") for cell in row)
                ]
                if len(rows) < 2:
                    continue
                width = max(len(row) for row in rows)
                padded_rows = [row + [None] * (width - len(row)) for row in rows]
                headers = _make_unique_headers(padded_rows[0], width)
                df = pd.DataFrame(padded_rows[1:], columns=headers)
                output_path = (
                    extracted_dir / f"{pdf_path.stem}_page{page_number}_table{table_number}.csv"
                )
                df.to_csv(output_path, index=False)
                output_paths.append(output_path)

    return output_paths


def extract_pdfs(input_dir: Path, output_dir: Path) -> list[Path]:
    """Extract all PDF files from input_dir into output/extracted_csv."""
    return extract_pdfs_to_csv(input_dir, output_dir, recursive=False)


def extract_pdfs_to_csv(input_dir: Path, output_dir: Path, recursive: bool = False) -> list[Path]:
    """Extract PDF files into output/extracted_csv, optionally preserving subfolders."""
    extracted_dir = ensure_dir(output_dir / "extracted_csv")
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_paths = sorted(path for path in input_dir.glob(pattern) if path.is_file())
    output_paths: list[Path] = []
    for pdf_path in pdf_paths:
        target_dir = extracted_dir
        if recursive:
            try:
                relative_parent = pdf_path.parent.relative_to(input_dir)
            except ValueError:
                relative_parent = Path()
            if str(relative_parent) != ".":
                target_dir = extracted_dir / relative_parent
        output_paths.extend(extract_pdf_tables(pdf_path, target_dir))
    return output_paths
