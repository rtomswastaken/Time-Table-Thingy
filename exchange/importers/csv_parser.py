"""Robust CSV parser with delimiter sniffing, multi-encoding support, and malformed row recovery."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.exceptions import ImportExportError
from exchange.security import validate_import_file_path


def parse_csv_file(file_path: str | Path) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Reads a CSV file into column headers and row dictionaries.

    Supports:
    - Multiple encodings (UTF-8, UTF-8 with BOM, Latin-1, CP1252).
    - Delimiter auto-detection (comma, semicolon, tab, pipe).
    - Stripping trailing/leading whitespace from headers and values.
    - Skipping completely empty lines.
    """
    path = validate_import_file_path(file_path)

    # Detect encoding
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    content: str = ""
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not content:
        # If all strict decodings failed, read with replacement
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as exc:
            raise ImportExportError(f"Could not read CSV file {path.name}: {exc}") from exc

    if not content.strip():
        raise ImportExportError(f"The CSV file '{path.name}' is empty.")

    # Sniff delimiter on first few lines
    sample = content[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        # Default to comma if sniffing fails
        delimiter = ","

    f_io = io.StringIO(content)
    reader = csv.reader(f_io, delimiter=delimiter)

    # Extract header
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ImportExportError(f"CSV file '{path.name}' contains no rows.")

    # Clean headers (strip, remove BOM if present)
    headers = [str(h).strip().lstrip("\ufeff") for h in raw_headers]
    headers = [h for h in headers if h]  # Remove empty trailing column headers

    if not headers:
        raise ImportExportError(f"CSV file '{path.name}' contains no valid column headers.")

    # Extract rows
    rows: List[Dict[str, Any]] = []
    line_num = 1
    for row in reader:
        line_num += 1
        # Skip blank lines
        if not row or not any(str(cell).strip() for cell in row):
            continue

        row_dict: Dict[str, Any] = {}
        for i, header in enumerate(headers):
            val = row[i].strip() if i < len(row) else ""
            row_dict[header] = val

        rows.append(row_dict)

    return headers, rows
