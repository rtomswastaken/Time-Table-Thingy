"""Automated test suite for CSV and Excel academic data importing."""

import os
import tempfile
from pathlib import Path
import pytest
import openpyxl

from core.exceptions import ImportExportError, ValidationError
from exchange.importers import (
    ClassesImporter,
    DepartmentsImporter,
    RoomsImporter,
    SubjectsImporter,
    TeachersImporter,
    TeacherAvailabilityImporter,
    parse_csv_file,
    parse_excel_file,
)
from exchange.models import DatasetType, ImportMode
from exchange.security import (
    desanitize_spreadsheet_value,
    sanitize_filename,
    sanitize_spreadsheet_value,
    validate_import_file_path,
)
from exchange.service import ImportExportServiceImpl


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


# ---------------------------------------------------------------------------
# CSV & Excel File Parsing Tests
# ---------------------------------------------------------------------------


def test_parse_valid_csv(temp_dir):
    csv_file = temp_dir / "teachers.csv"
    csv_file.write_text(
        "employee_id,name,department_code,email\n"
        "T101,Dr. Alan Turing,CSE,alan@univ.edu\n"
        "T102,Prof. Ada Lovelace,CSE,ada@univ.edu\n",
        encoding="utf-8",
    )
    headers, rows = parse_csv_file(csv_file)
    assert headers == ["employee_id", "name", "department_code", "email"]
    assert len(rows) == 2
    assert rows[0]["employee_id"] == "T101"
    assert rows[0]["name"] == "Dr. Alan Turing"
    assert rows[1]["employee_id"] == "T102"


def test_parse_csv_delimiter_sniffing(temp_dir):
    tsv_file = temp_dir / "subjects.tsv"
    tsv_file.write_text(
        "code\tname\tdepartment_code\tcredits\n"
        "CS101\tIntro CS\tCSE\t4.0\n",
        encoding="utf-8",
    )
    headers, rows = parse_csv_file(tsv_file)
    assert headers == ["code", "name", "department_code", "credits"]
    assert len(rows) == 1
    assert rows[0]["code"] == "CS101"


def test_parse_empty_csv_raises_error(temp_dir):
    empty_file = temp_dir / "empty.csv"
    empty_file.write_text("   \n\n", encoding="utf-8")
    with pytest.raises(ImportExportError, match="empty"):
        parse_csv_file(empty_file)


def test_parse_valid_excel(temp_dir):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["code", "name", "capacity"])
    ws.append(["R101", "Hall 101", 60])
    ws.append(["R102", "Hall 102", 40])
    xlsx_file = temp_dir / "rooms.xlsx"
    wb.save(xlsx_file)
    wb.close()

    headers, rows = parse_excel_file(xlsx_file)
    assert headers == ["code", "name", "capacity"]
    assert len(rows) == 2
    assert rows[0]["code"] == "R101"
    assert rows[0]["capacity"] == 60


def test_unsupported_file_extension(temp_dir):
    bad_file = temp_dir / "data.json"
    bad_file.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(ImportExportError, match="Unsupported file format"):
        validate_import_file_path(bad_file)


# ---------------------------------------------------------------------------
# Column Mapping & Alias Detection Tests
# ---------------------------------------------------------------------------


def test_column_auto_mapping():
    importer = TeachersImporter()
    headers = ["Faculty ID", "Faculty Name", "Dept", "Email Address"]
    mapping, missing = importer.get_mapper().auto_map(headers)

    assert mapping["Faculty ID"] == "employee_id"
    assert mapping["Faculty Name"] == "name"
    assert mapping["Dept"] == "department_code"
    assert mapping["Email Address"] == "email"
    assert len(missing) == 0


def test_missing_required_column_detection():
    importer = TeachersImporter()
    # Missing department_code
    headers = ["employee_id", "name", "email"]
    mapping, missing = importer.get_mapper().auto_map(headers)
    assert "department_code" in missing


# ---------------------------------------------------------------------------
# Entity Validation Tests
# ---------------------------------------------------------------------------


def test_teachers_validation_success():
    importer = TeachersImporter()
    raw_rows = [
        {"employee_id": "T101", "name": "Alan Turing", "department_code": "CSE", "max_weekly_hours": 18, "min_weekly_hours": 8},
        {"employee_id": "T102", "name": "Ada Lovelace", "department_code": "CSE", "max_weekly_hours": 20, "min_weekly_hours": 10},
    ]
    mapping = {k: k for k in ["employee_id", "name", "department_code", "max_weekly_hours", "min_weekly_hours"]}
    context = {"valid_department_codes": {"CSE"}}

    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, context)
    assert summary.can_proceed is True
    assert summary.total_rows == 2
    assert summary.valid_rows == 2
    assert summary.to_create_count == 2
    assert len(summary.errors) == 0


def test_teachers_validation_missing_required():
    importer = TeachersImporter()
    raw_rows = [
        {"employee_id": "", "name": "No ID Teacher", "department_code": "CSE"},
        {"employee_id": "T102", "name": "", "department_code": "CSE"},
    ]
    mapping = {"employee_id": "employee_id", "name": "name", "department_code": "department_code"}
    context = {"valid_department_codes": {"CSE"}}

    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, context)
    assert summary.can_proceed is False
    assert len(summary.errors) == 2
    assert summary.errors[0].field == "employee_id"
    assert summary.errors[1].field == "name"


def test_teachers_validation_duplicate_in_file():
    importer = TeachersImporter()
    raw_rows = [
        {"employee_id": "T101", "name": "Alan Turing", "department_code": "CSE"},
        {"employee_id": "T101", "name": "Duplicate Alan", "department_code": "CSE"},
    ]
    mapping = {"employee_id": "employee_id", "name": "name", "department_code": "department_code"}
    context = {"valid_department_codes": {"CSE"}}

    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, context)
    assert summary.can_proceed is False
    assert any(e.error_type == "DUPLICATE_IN_FILE" for e in summary.errors)


def test_teachers_validation_missing_department_reference():
    importer = TeachersImporter()
    raw_rows = [
        {"employee_id": "T101", "name": "Alan Turing", "department_code": "UNKNOWN_DEPT"},
    ]
    mapping = {"employee_id": "employee_id", "name": "name", "department_code": "department_code"}
    context = {"valid_department_codes": {"CSE", "ECE"}}  # UNKNOWN_DEPT not present

    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, context)
    assert summary.can_proceed is False
    assert summary.errors[0].error_type == "FOREIGN_KEY_NOT_FOUND"
    assert "UNKNOWN_DEPT" in summary.errors[0].message


def test_teachers_validation_workload_bounds():
    importer = TeachersImporter()
    raw_rows = [
        {"employee_id": "T101", "name": "Teacher", "department_code": "CSE", "max_weekly_hours": 5, "min_weekly_hours": 10},
    ]
    mapping = {"employee_id": "employee_id", "name": "name", "department_code": "department_code", "max_weekly_hours": "max_weekly_hours", "min_weekly_hours": "min_weekly_hours"}
    context = {"valid_department_codes": {"CSE"}}

    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, context)
    assert summary.can_proceed is False
    assert any(e.error_type == "LOGICAL_CONFLICT" for e in summary.errors)


def test_rooms_validation_capacity_bounds():
    importer = RoomsImporter()
    raw_rows = [
        {"code": "R101", "name": "Valid Room", "capacity": 50},
        {"code": "R102", "name": "Invalid Room", "capacity": -5},
    ]
    mapping = {"code": "code", "name": "name", "capacity": "capacity"}
    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, {})
    assert len(valid_rows) == 1
    assert len(summary.errors) == 1
    assert summary.errors[0].field == "capacity"


def test_subjects_credits_and_contact_hours():
    importer = SubjectsImporter()
    raw_rows = [
        {"code": "CS101", "name": "Intro CS", "department_code": "CSE", "credits": 3.0, "weekly_contact_hours": 4.0},
        {"code": "CS102", "name": "Bad Hours", "department_code": "CSE", "credits": 3.0, "weekly_contact_hours": -1.0},
    ]
    mapping = {"code": "code", "name": "name", "department_code": "department_code", "credits": "credits", "weekly_contact_hours": "weekly_contact_hours"}
    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, {"valid_department_codes": {"CSE"}})
    assert len(valid_rows) == 1
    assert summary.errors[0].field == "weekly_contact_hours"


def test_availability_day_and_period_ranges():
    importer = TeacherAvailabilityImporter()
    raw_rows = [
        {"employee_id": "T101", "day_of_week": 4, "period_index": 2, "is_available": "FALSE"}, # Valid Fri Period 2
        {"employee_id": "T101", "day_of_week": 8, "period_index": 2, "is_available": "TRUE"},  # Invalid day 8
    ]
    mapping = {"employee_id": "employee_id", "day_of_week": "day_of_week", "period_index": "period_index", "is_available": "is_available"}
    valid_rows, summary = importer.validate_rows(raw_rows, mapping, ImportMode.CREATE, {"periods_per_day": 6})
    assert len(valid_rows) == 1
    assert summary.errors[0].field == "day_of_week"


# ---------------------------------------------------------------------------
# Import Modes & Service Execution Tests
# ---------------------------------------------------------------------------


def test_import_modes_create_vs_update(temp_dir):
    csv_file = temp_dir / "departments.csv"
    csv_file.write_text(
        "code,name\n"
        "CSE,Computer Science\n",
        encoding="utf-8",
    )
    service = ImportExportServiceImpl(context={"existing_department_codes": {"CSE"}})

    # CREATE mode should fail because CSE already exists
    res_create = service.execute_import(csv_file, DatasetType.DEPARTMENTS, mode=ImportMode.CREATE)
    assert res_create.success is False
    assert any(e.error_type == "ALREADY_EXISTS" for e in res_create.errors)

    # UPDATE mode should succeed
    res_update = service.execute_import(csv_file, DatasetType.DEPARTMENTS, mode=ImportMode.UPDATE)
    assert res_update.success is True
    assert res_update.updated_count == 1

    # VALIDATE_ONLY mode should succeed without persisting
    res_val = service.execute_import(csv_file, DatasetType.DEPARTMENTS, mode=ImportMode.VALIDATE_ONLY)
    assert res_val.success is True


def test_end_to_end_service_import_curriculum(temp_dir):
    csv_file = temp_dir / "curriculum.csv"
    csv_file.write_text(
        "code,name,department_code,credits,weekly_contact_hours\n"
        "CS201,Algorithms,CSE,4.0,4.0\n"
        "CS202,Databases,CSE,3.0,3.0\n",
        encoding="utf-8",
    )
    service = ImportExportServiceImpl(context={"valid_department_codes": {"CSE"}})
    counts = service.import_curriculum_from_csv(str(csv_file))
    assert counts["created"] == 2
    assert counts["errors"] == 0


def test_security_formula_injection_sanitization():
    # Dangerous formula strings
    dangerous = "=cmd|' /C calc'!A0"
    sanitized = sanitize_spreadsheet_value(dangerous)
    assert sanitized.startswith("'=")
    # Desanitization restores original value
    assert desanitize_spreadsheet_value(sanitized) == dangerous

    # Safe strings remain untouched
    safe = "Computer Science"
    assert sanitize_spreadsheet_value(safe) == "Computer Science"


def test_security_filename_sanitization():
    unsafe_name = "../../etc/passwd:report?.xlsx"
    clean = sanitize_filename(unsafe_name)
    assert "/" not in clean
    assert ".." not in clean
    assert ":" not in clean
    assert "?" not in clean
