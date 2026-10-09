"""Secure Excel (.xlsx) file parser using openpyxl without macro execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from core.exceptions import ImportExportError
from exchange.security import validate_import_file_path


def parse_excel_file(
    file_path: str | Path,
    sheet_name: Optional[str] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Reads an Excel (.xlsx) spreadsheet into column headers and row dictionaries.

    Uses data_only=True so formulas are not evaluated or executed, only cached
    data values are extracted.
    """
    path = validate_import_file_path(file_path)

    try:
        # read_only=True and data_only=True for memory efficiency and safety
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ImportExportError(f"Could not open Excel file '{path.name}': {exc}") from exc

    try:
        available_sheets = workbook.sheetnames
        if not available_sheets:
            raise ImportExportError(f"Excel file '{path.name}' contains no worksheets.")

        # Determine target worksheet
        target_sheet = None
        if sheet_name and sheet_name in available_sheets:
            target_sheet = workbook[sheet_name]
        else:
            # If default sheet is named "Instructions", prefer "Data" or next sheet if available
            if len(available_sheets) > 1 and available_sheets[0].lower() in ("instructions", "readme", "help"):
                target_sheet = workbook[available_sheets[1]]
            else:
                target_sheet = workbook.active or workbook[available_sheets[0]]

        # Read rows generator
        row_iter = target_sheet.iter_rows(values_only=True)

        # Find header row (first non-empty row)
        headers: List[str] = []
        for raw_row in row_iter:
            if not raw_row or not any(cell is not None and str(cell).strip() for cell in raw_row):
                continue
            headers = [str(cell).strip() for cell in raw_row if cell is not None and str(cell).strip()]
            break

        if not headers:
            raise ImportExportError(f"Sheet '{target_sheet.title}' in '{path.name}' has no column headers.")

        num_cols = len(headers)
        rows: List[Dict[str, Any]] = []

        for raw_row in row_iter:
            # Skip empty rows
            if not raw_row or not any(cell is not None and str(cell).strip() for cell in raw_row):
                continue

            row_dict: Dict[str, Any] = {}
            for i, header in enumerate(headers):
                val = raw_row[i] if i < len(raw_row) else None
                if val is None:
                    row_dict[header] = ""
                elif isinstance(val, (int, float, bool)):
                    row_dict[header] = val
                else:
                    row_dict[header] = str(val).strip()

            rows.append(row_dict)

        return headers, rows

    finally:
        workbook.close()
