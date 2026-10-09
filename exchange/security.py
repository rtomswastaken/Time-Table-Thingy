"""Security and file safety utilities for import, export, and reporting operations.

Mitigates:
- CSV/Excel formula injection (DDE / Command execution attacks).
- Directory traversal and arbitrary file overwrite.
- Dangerous or oversized file uploads.
- Untrusted string evaluation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from core.exceptions import ImportExportError

# Characters that trigger formula execution in spreadsheet applications if at start of cell
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Maximum allowed import file size (50 MB)
MAX_IMPORT_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Allowed file extensions
ALLOWED_IMPORT_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}
ALLOWED_EXPORT_EXTENSIONS = {".csv", ".xlsx", ".pdf"}


def sanitize_spreadsheet_value(val: Any) -> Any:
    """Sanitizes a string or scalar value to prevent CSV/Excel formula injection.

    If a text value begins with formula characters (=, +, -, @, tab, newline),
    it is prepended with a single quote (') so that spreadsheet programs treat
    it as literal text rather than an executable expression.
    """
    if val is None:
        return ""
    if isinstance(val, (int, float, bool)):
        return val

    s = str(val)
    if not s:
        return ""

    # Check for formula injection triggers
    if s.startswith(FORMULA_PREFIXES):
        # Escape with a single quote prefix
        return f"'{s}"

    return s


def desanitize_spreadsheet_value(val: Any) -> Any:
    """Removes single quote escaping added to prevent formula injection."""
    if isinstance(val, str) and val.startswith("'"):
        # If followed by a formula prefix, strip the leading single quote
        if len(val) > 1 and val[1] in FORMULA_PREFIXES:
            return val[1:]
    return val


def sanitize_filename(filename: str, default: str = "export") -> str:
    """Produces a safe, filesystem-friendly base filename.

    Removes path separators, directory traversal sequences (../), and
    characters invalid on Windows, macOS, and Linux.
    """
    if not filename or not filename.strip():
        return default

    # Remove path directory separators to prevent traversal
    name = os.path.basename(filename)

    # Replace forbidden filename characters (< > : " / \ | ? *) with underscores
    clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    clean_name = clean_name.strip(". ")

    if not clean_name:
        return default

    # Limit length
    if len(clean_name) > 200:
        clean_name = clean_name[:200]

    return clean_name


def validate_import_file_path(file_path: str | Path) -> Path:
    """Validates that a file path exists, is a regular file, has an allowed extension,

    and does not exceed the maximum allowed size.
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise ImportExportError(f"File not found: {file_path}")

    if not path.is_file():
        raise ImportExportError(f"Path is not a regular file: {file_path}")

    ext = path.suffix.lower()
    if ext not in ALLOWED_IMPORT_EXTENSIONS:
        raise ImportExportError(
            f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_IMPORT_EXTENSIONS))}"
        )

    file_size = path.stat().st_size
    if file_size > MAX_IMPORT_FILE_SIZE_BYTES:
        raise ImportExportError(
            f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds maximum allowed limit of "
            f"{MAX_IMPORT_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB."
        )

    return path


def validate_export_file_path(output_path: str | Path, expected_ext: Optional[str] = None) -> Path:
    """Validates and prepares a safe destination path for an exported file."""
    path = Path(output_path).resolve()

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    if expected_ext:
        expected = expected_ext.lower()
        if not expected.startswith("."):
            expected = f".{expected}"
        if path.suffix.lower() != expected:
            path = path.with_suffix(expected)

    ext = path.suffix.lower()
    if ext not in ALLOWED_EXPORT_EXTENSIONS:
        raise ImportExportError(
            f"Unsupported export format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXPORT_EXTENSIONS))}"
        )

    return path
