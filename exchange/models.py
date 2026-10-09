"""Domain models, enums, and data transfer objects for the exchange package.

Defines parameters, validation structures, preview objects, and report models
for CSV/Excel importing, PDF/Excel/CSV exporting, and academic analytics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ImportMode(str, Enum):
    """Execution mode for importing records."""
    CREATE = "CREATE"              # Insert new records only, fail/skip on duplicates
    UPDATE = "UPDATE"              # Update existing records matching stable identifiers
    UPSERT = "UPSERT"              # Create new or update existing records
    VALIDATE_ONLY = "VALIDATE_ONLY"# Dry-run validation without database mutations


class DatasetType(str, Enum):
    """Supported academic datasets for import and export."""
    DEPARTMENTS = "DEPARTMENTS"
    ACADEMIC_PERIODS = "ACADEMIC_PERIODS"
    CLASSES = "CLASSES"
    TEACHERS = "TEACHERS"
    TEACHER_QUALIFICATIONS = "TEACHER_QUALIFICATIONS"
    SUBJECTS = "SUBJECTS"
    SUBJECT_OFFERINGS = "SUBJECT_OFFERINGS"
    CLASS_ASSIGNMENTS = "CLASS_ASSIGNMENTS"
    ROOMS = "ROOMS"
    TEACHER_AVAILABILITY = "TEACHER_AVAILABILITY"


class ExportFormat(str, Enum):
    """Supported export publication formats."""
    CSV = "CSV"
    EXCEL = "EXCEL"
    PDF = "PDF"


class TimetableLayout(str, Enum):
    """Layout perspective for schedule exports."""
    CLASS_GRID = "CLASS_GRID"            # Timetable matrix per Class / Section
    TEACHER_GRID = "TEACHER_GRID"        # Timetable matrix per Faculty member
    ROOM_GRID = "ROOM_GRID"              # Occupancy matrix per Room
    DEPARTMENT_SUMMARY = "DEPARTMENT_SUMMARY" # Aggregated department schedule
    MASTER_TABULAR = "MASTER_TABULAR"    # Flat master list of all scheduled sessions


@dataclass
class ImportRowError:
    """Represents a validation failure for an imported row."""
    row_number: int
    field: Optional[str]
    error_type: str
    message: str
    value: Any = None


@dataclass
class ImportRowWarning:
    """Represents a non-fatal warning for an imported row."""
    row_number: int
    field: Optional[str]
    message: str


@dataclass
class ColumnMapping:
    """Mapping between source file column name and canonical entity field."""
    target_field: str
    source_column: str
    is_required: bool = True
    display_label: str = ""


@dataclass
class ImportPreview:
    """Preview of uploaded file contents prior to executing import."""
    file_name: str
    dataset_type: DatasetType
    total_rows: int
    column_names: List[str]
    sample_rows: List[Dict[str, Any]]
    empty_field_counts: Dict[str, int]
    detected_mapping: Dict[str, str] = field(default_factory=dict) # source_col -> target_field
    missing_required_columns: List[str] = field(default_factory=list)
    duplicate_identifiers: List[str] = field(default_factory=list)
    is_valid_format: bool = True
    format_error: Optional[str] = None


@dataclass
class ImportValidationSummary:
    """Validation report generated before committing imported records."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    to_create_count: int
    to_update_count: int
    errors: List[ImportRowError] = field(default_factory=list)
    warnings: List[ImportRowWarning] = field(default_factory=list)
    can_proceed: bool = True


@dataclass
class ImportResult:
    """Outcome of an executed import operation."""
    success: bool
    mode: ImportMode
    dataset_type: DatasetType
    total_processed: int
    created_count: int
    updated_count: int
    skipped_count: int
    errors: List[ImportRowError] = field(default_factory=list)
    warnings: List[ImportRowWarning] = field(default_factory=list)
    created_ids: List[str] = field(default_factory=list)
    updated_ids: List[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ExportResult:
    """Outcome of an export operation."""
    success: bool
    format: ExportFormat
    file_path: str
    file_size_bytes: int = 0
    records_exported: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Report Data Models
# ---------------------------------------------------------------------------


@dataclass
class WorkloadReportRow:
    """Structured faculty workload evaluation."""
    teacher_id: str
    teacher_name: str
    employee_id: str
    department_name: str
    assigned_periods: int
    assigned_contact_hours: float
    min_periods: Optional[int]
    max_periods: Optional[int]
    remaining_capacity: Optional[int]
    daily_periods: Dict[int, int] = field(default_factory=dict) # day_index -> count
    max_consecutive_observed: int = 0
    is_overloaded: bool = False
    is_underloaded: bool = False
    has_workload_rule: bool = True
    warning_message: str = ""


@dataclass
class RoomUtilizationRow:
    """Room scheduling efficiency evaluation."""
    room_id: str
    room_code: str
    room_name: str
    room_type: str
    capacity: int
    building: str
    scheduled_sessions_count: int
    occupied_periods: int
    available_periods: int
    utilization_rate: float  # Percentage, 0.0 to 100.0%
    notes: str = ""


@dataclass
class ConflictReportRow:
    """Constraint violation or conflict notification."""
    violation_type: str
    severity: str  # "ERROR" or "WARNING"
    is_hard: bool
    description: str
    involved_teachers: List[str] = field(default_factory=list)
    involved_rooms: List[str] = field(default_factory=list)
    involved_classes: List[str] = field(default_factory=list)
    involved_sessions: List[str] = field(default_factory=list)
    remediation_suggestion: str = ""


@dataclass
class UnscheduledSessionRow:
    """Curricular requirement that could not be placed in the timetable."""
    offering_id: str
    subject_code: str
    subject_name: str
    class_name: str
    teacher_name: str
    required_sessions: int
    placed_sessions: int
    missing_count: int
    reason: str


@dataclass
class TimetableSummary:
    """High-level institutional timetable overview."""
    timetable_id: str
    name: str
    academic_year: str
    semester: str
    version: int
    status: str
    total_classes: int
    total_teachers: int
    total_rooms: int
    total_sessions: int
    total_periods_placed: int
    total_hours_scheduled: float
    conflict_count: int
    unscheduled_count: int
    average_room_utilization: float
    is_valid: bool
