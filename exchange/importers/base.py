"""Base classes and utilities for tabular file parsing, column mapping, and import pipelines.

Implements the 6-step import pipeline:
1. File selection & validation
2. Preview generation (column names, sample rows, stats, duplicates)
3. Column mapping (intelligent auto-mapping & manual override)
4. Row-level validation (types, ranges, duplicates, referential integrity)
5. Import confirmation summary
6. Persistence with transaction rollback support
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from exchange.models import (
    ColumnMapping,
    DatasetType,
    ImportMode,
    ImportPreview,
    ImportResult,
    ImportRowError,
    ImportRowWarning,
    ImportValidationSummary,
)
from exchange.security import desanitize_spreadsheet_value


def normalize_column_name(col: str) -> str:
    """Normalizes a column heading for fuzzy alias matching."""
    if not col:
        return ""
    # Lowercase, replace non-alphanumeric with underscore, strip
    s = str(col).lower().strip()
    s = re.sub(r"[^a-z0-9]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


class ColumnMapper:
    """Matches incoming tabular column headers to entity schema fields using alias tables."""

    def __init__(self, target_fields: Dict[str, List[str]], required_fields: Set[str]):
        """target_fields: map of canonical_field_name -> list of acceptable aliases.

        required_fields: set of canonical fields that must be present.
        """
        self.target_fields = target_fields
        self.required_fields = required_fields

        # Inverted index: normalized_alias -> canonical_field_name
        self._alias_index: Dict[str, str] = {}
        for canonical, aliases in target_fields.items():
            self._alias_index[normalize_column_name(canonical)] = canonical
            for alias in aliases:
                self._alias_index[normalize_column_name(alias)] = canonical

    def auto_map(self, source_columns: List[str]) -> Tuple[Dict[str, str], List[str]]:
        """Automatically maps source columns to canonical target fields.

        Returns:
            mapping: Dict[source_column, canonical_target_field]
            missing_required: List of required target fields that could not be mapped
        """
        mapping: Dict[str, str] = {}
        mapped_targets: Set[str] = set()

        for source_col in source_columns:
            norm = normalize_column_name(source_col)
            if norm in self._alias_index:
                canonical = self._alias_index[norm]
                if canonical not in mapped_targets:
                    mapping[source_col] = canonical
                    mapped_targets.add(canonical)

        missing_required = [f for f in sorted(self.required_fields) if f not in mapped_targets]
        return mapping, missing_required

    def apply_mapping(self, row: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Translates a raw row dict from source columns to canonical field keys."""
        translated: Dict[str, Any] = {}
        for source_col, val in row.items():
            if source_col in mapping:
                target_field = mapping[source_col]
                # Clean and desanitize spreadsheet formula quote
                clean_val = desanitize_spreadsheet_value(val)
                if isinstance(clean_val, str):
                    clean_val = clean_val.strip()
                translated[target_field] = clean_val
        return translated


class BaseDatasetImporter(ABC):
    """Abstract base class for importing specific academic datasets."""

    def __init__(self, dataset_type: DatasetType, identifier_field: str):
        self.dataset_type = dataset_type
        self.identifier_field = identifier_field

    @abstractmethod
    def get_column_definitions(self) -> Dict[str, List[str]]:
        """Returns mapping of canonical_field -> list of aliases."""
        ...

    @abstractmethod
    def get_required_fields(self) -> Set[str]:
        """Returns set of required canonical fields."""
        ...

    def get_mapper(self) -> ColumnMapper:
        return ColumnMapper(self.get_column_definitions(), self.get_required_fields())

    def generate_preview(
        self,
        file_name: str,
        column_names: List[str],
        raw_rows: List[Dict[str, Any]],
        sample_limit: int = 5,
    ) -> ImportPreview:
        """Generates a structured preview of the tabular data."""
        mapper = self.get_mapper()
        detected_mapping, missing_required = mapper.auto_map(column_names)

        # Count empty values per column
        empty_counts: Dict[str, int] = {col: 0 for col in column_names}
        for r in raw_rows:
            for col in column_names:
                v = r.get(col)
                if v is None or (isinstance(v, str) and not v.strip()):
                    empty_counts[col] += 1

        # Check for duplicate primary identifiers in preview
        id_col = None
        for s_col, t_field in detected_mapping.items():
            if t_field == self.identifier_field:
                id_col = s_col
                break

        duplicate_ids: List[str] = []
        if id_col:
            seen: Set[str] = set()
            for r in raw_rows:
                raw_id = r.get(id_col)
                if raw_id is not None and str(raw_id).strip():
                    sid = str(raw_id).strip().upper()
                    if sid in seen and sid not in duplicate_ids:
                        duplicate_ids.append(sid)
                    seen.add(sid)

        sample_rows = raw_rows[:sample_limit]

        return ImportPreview(
            file_name=file_name,
            dataset_type=self.dataset_type,
            total_rows=len(raw_rows),
            column_names=column_names,
            sample_rows=sample_rows,
            empty_field_counts=empty_counts,
            detected_mapping=detected_mapping,
            missing_required_columns=missing_required,
            duplicate_identifiers=duplicate_ids,
            is_valid_format=True,
        )

    @abstractmethod
    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        """Validates raw tabular rows, transforming them into canonical entity dictionaries.

        Returns:
            canonical_rows: List of validated and cleaned dictionaries
            summary: ImportValidationSummary detailing errors, warnings, and counts
        """
        ...

    @abstractmethod
    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        """Persists validated canonical records via repositories/services within a transaction."""
        ...
