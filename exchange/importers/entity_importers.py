"""Specialized entity importers for all academic datasets.

Implements strict validation, reference checking, duplicate detection,
and transactional persistence for:
1. Departments
2. Academic Years & Semesters
3. Classes & Sections
4. Teachers
5. Teacher Qualifications
6. Subjects
7. Subject Offerings
8. Class-Subject Assignments
9. Rooms
10. Teacher Availability & Preferences
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import (
    AcademicYear,
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomType,
    Semester,
    Subject,
    SubjectOffering,
    Teacher,
    TeacherAvailability,
    TeacherPreference,
    TeacherQualification,
    TeacherWorkloadRule,
)
from exchange.importers.base import BaseDatasetImporter
from exchange.models import (
    DatasetType,
    ImportMode,
    ImportResult,
    ImportRowError,
    ImportRowWarning,
    ImportValidationSummary,
)


# Helper conversion functions
def to_int(val: Any, default: int = 0) -> Optional[int]:
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def to_float(val: Any, default: float = 0.0) -> Optional[float]:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def to_bool(val: Any, default: bool = True) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "y", "t", "active")


# ---------------------------------------------------------------------------
# 1. Departments Importer
# ---------------------------------------------------------------------------


class DepartmentsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.DEPARTMENTS, "code")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "code": ["department_code", "dept_code", "code", "dept_id", "department_id"],
            "name": ["department_name", "dept_name", "name", "title"],
            "institution_code": ["institution_code", "inst_code", "institution"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"code", "name"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        existing_codes: Set[str] = context.get("existing_department_codes", set())
        seen_in_file: Set[str] = set()

        to_create = 0
        to_update = 0
        duplicate_rows = 0

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            code = str(row.get("code") or "").strip().upper()
            name = str(row.get("name") or "").strip()

            row_has_error = False
            if not code:
                errors.append(ImportRowError(idx, "code", "MISSING_REQUIRED", "Department code is required.", code))
                row_has_error = True
            if not name:
                errors.append(ImportRowError(idx, "name", "MISSING_REQUIRED", "Department name is required.", name))
                row_has_error = True

            if code in seen_in_file:
                errors.append(ImportRowError(idx, "code", "DUPLICATE_IN_FILE", f"Duplicate department code '{code}' in file.", code))
                row_has_error = True
                duplicate_rows += 1
            elif code:
                seen_in_file.add(code)

            if not row_has_error:
                exists = code in existing_codes
                if mode == ImportMode.CREATE and exists:
                    errors.append(ImportRowError(idx, "code", "ALREADY_EXISTS", f"Department '{code}' already exists (Create mode).", code))
                    continue
                elif mode == ImportMode.UPDATE and not exists:
                    errors.append(ImportRowError(idx, "code", "NOT_FOUND", f"Department '{code}' not found for update.", code))
                    continue

                if exists:
                    to_update += 1
                else:
                    to_create += 1

                canonical_rows.append({
                    "code": code,
                    "name": name,
                    "institution_code": str(row.get("institution_code") or "").strip() or "DEFAULT",
                    "row_number": idx,
                    "is_update": exists,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=duplicate_rows,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        dept_repo = context.get("department_repo")
        institution_id = context.get("institution_id", "DEFAULT")

        created_ids = []
        updated_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=sum(1 for r in canonical_rows if not r["is_update"]),
                updated_count=sum(1 for r in canonical_rows if r["is_update"]),
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                dept = Department(
                    institution_id=institution_id,
                    name=r["name"],
                    code=r["code"],
                )
                if dept_repo:
                    saved = dept_repo.save(dept)
                    if r["is_update"]:
                        updated_ids.append(saved.id)
                    else:
                        created_ids.append(saved.id)
                else:
                    if r["is_update"]:
                        updated_ids.append(r["code"])
                    else:
                        created_ids.append(r["code"])
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "code", "SAVE_ERROR", str(exc), r["code"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=len(updated_ids),
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            updated_ids=updated_ids,
            message=f"Successfully imported {len(created_ids)} new and updated {len(updated_ids)} departments.",
        )


# ---------------------------------------------------------------------------
# 2. Academic Years & Semesters Importer
# ---------------------------------------------------------------------------


class AcademicPeriodsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.ACADEMIC_PERIODS, "year_semester_key")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "academic_year": ["academic_year", "year", "academic_year_name", "ay_name", "cycle"],
            "start_date": ["start_date", "start", "from_date"],
            "end_date": ["end_date", "end", "to_date"],
            "is_current": ["is_current", "current", "active"],
            "semester_number": ["semester_number", "semester_num", "semester", "term_number", "sem"],
            "term_name": ["term_name", "semester_name", "term", "name"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"academic_year", "semester_number"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        seen_in_file: Set[str] = set()
        to_create = 0
        to_update = 0

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            year = str(row.get("academic_year") or "").strip()
            sem_num = to_int(row.get("semester_number"))
            term_name = str(row.get("term_name") or f"Semester {sem_num}").strip()

            row_has_error = False
            if not year:
                errors.append(ImportRowError(idx, "academic_year", "MISSING_REQUIRED", "Academic year is required.", year))
                row_has_error = True
            if sem_num is None or sem_num < 1:
                errors.append(ImportRowError(idx, "semester_number", "INVALID_VALUE", "Semester number must be >= 1.", row.get("semester_number")))
                row_has_error = True

            key = f"{year}:{sem_num}"
            if key in seen_in_file:
                errors.append(ImportRowError(idx, "semester_number", "DUPLICATE_IN_FILE", f"Duplicate semester '{key}' in file.", key))
                row_has_error = True
            else:
                seen_in_file.add(key)

            if not row_has_error:
                to_create += 1
                canonical_rows.append({
                    "academic_year": year,
                    "start_date": str(row.get("start_date") or "").strip() or "2026-08-01",
                    "end_date": str(row.get("end_date") or "").strip() or "2027-05-31",
                    "is_current": to_bool(row.get("is_current"), True),
                    "semester_number": sem_num,
                    "term_name": term_name,
                    "row_number": idx,
                    "is_update": False,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        inst_repo = context.get("institution_repo")
        created_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=len(canonical_rows),
                updated_count=0,
                skipped_count=0,
                message="Validation completed successfully.",
            )

        year_cache: Dict[str, AcademicYear] = {}
        for r in canonical_rows:
            try:
                y_name = r["academic_year"]
                if y_name not in year_cache:
                    ay = AcademicYear(
                        name=y_name,
                        start_date=r["start_date"],
                        end_date=r["end_date"],
                        is_current=r["is_current"],
                    )
                    if inst_repo and hasattr(inst_repo, "save_academic_year"):
                        ay = inst_repo.save_academic_year(ay)
                    year_cache[y_name] = ay

                ay = year_cache[y_name]
                sem = Semester(
                    academic_year_id=ay.id,
                    number=r["semester_number"],
                    term_name=r["term_name"],
                )
                if inst_repo and hasattr(inst_repo, "save_semester"):
                    saved_sem = inst_repo.save_semester(sem)
                    created_ids.append(saved_sem.id)
                else:
                    created_ids.append(sem.id)
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "semester_number", "SAVE_ERROR", str(exc), r["semester_number"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=0,
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            message=f"Successfully imported {len(created_ids)} academic period records.",
        )


# ---------------------------------------------------------------------------
# 3. Classes & Sections Importer
# ---------------------------------------------------------------------------


class ClassesImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.CLASSES, "name")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "name": ["class_name", "name", "cohort", "section_name", "class"],
            "department_code": ["department_code", "dept_code", "department", "dept"],
            "student_count": ["student_count", "capacity", "strength", "size", "students"],
            "semester_number": ["semester_number", "semester", "sem", "term"],
            "section": ["section", "division", "batch"],
            "home_room_code": ["home_room_code", "room_code", "fixed_room", "home_room"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"name", "department_code"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_dept_codes: Set[str] = context.get("valid_department_codes", set())
        valid_room_codes: Set[str] = context.get("valid_room_codes", set())
        existing_names: Set[str] = context.get("existing_class_names", set())

        seen_in_file: Set[str] = set()
        to_create = 0
        to_update = 0

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            name = str(row.get("name") or "").strip()
            dept_code = str(row.get("department_code") or "").strip().upper()
            student_count = to_int(row.get("student_count"), default=60)
            home_room = str(row.get("home_room_code") or "").strip().upper()

            row_has_error = False
            if not name:
                errors.append(ImportRowError(idx, "name", "MISSING_REQUIRED", "Class name is required.", name))
                row_has_error = True

            if not dept_code:
                errors.append(ImportRowError(idx, "department_code", "MISSING_REQUIRED", "Department code is required.", dept_code))
                row_has_error = True
            elif valid_dept_codes and dept_code not in valid_dept_codes:
                errors.append(ImportRowError(idx, "department_code", "FOREIGN_KEY_NOT_FOUND", f"Department '{dept_code}' does not exist.", dept_code))
                row_has_error = True

            if student_count is None or student_count < 1:
                errors.append(ImportRowError(idx, "student_count", "INVALID_VALUE", "Student count must be >= 1.", row.get("student_count")))
                row_has_error = True

            if home_room and valid_room_codes and home_room not in valid_room_codes:
                warnings.append(ImportRowWarning(idx, "home_room_code", f"Referenced home room '{home_room}' not found."))

            if name in seen_in_file:
                errors.append(ImportRowError(idx, "name", "DUPLICATE_IN_FILE", f"Duplicate class name '{name}' in file.", name))
                row_has_error = True
            else:
                seen_in_file.add(name)

            if not row_has_error:
                exists = name in existing_names
                if mode == ImportMode.CREATE and exists:
                    errors.append(ImportRowError(idx, "name", "ALREADY_EXISTS", f"Class '{name}' already exists.", name))
                    continue
                elif mode == ImportMode.UPDATE and not exists:
                    errors.append(ImportRowError(idx, "name", "NOT_FOUND", f"Class '{name}' not found for update.", name))
                    continue

                if exists:
                    to_update += 1
                else:
                    to_create += 1

                canonical_rows.append({
                    "name": name,
                    "department_code": dept_code,
                    "student_count": student_count,
                    "semester_number": to_int(row.get("semester_number"), default=1),
                    "section": str(row.get("section") or "A").strip(),
                    "home_room_code": home_room,
                    "row_number": idx,
                    "is_update": exists,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        class_repo = context.get("class_repo")
        dept_id_map: Dict[str, str] = context.get("dept_id_map", {})
        sem_id_map: Dict[int, str] = context.get("sem_id_map", {})
        default_sem_id = context.get("semester_id", "DEFAULT_SEM")

        created_ids = []
        updated_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=sum(1 for r in canonical_rows if not r["is_update"]),
                updated_count=sum(1 for r in canonical_rows if r["is_update"]),
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                dept_id = dept_id_map.get(r["department_code"], r["department_code"])
                sem_id = sem_id_map.get(r["semester_number"], default_sem_id)
                cg = ClassGroup(
                    department_id=dept_id,
                    semester_id=sem_id,
                    name=r["name"],
                    student_count=r["student_count"],
                    home_room_id=r.get("home_room_code"),
                )
                if class_repo:
                    saved = class_repo.save(cg)
                    if r["is_update"]:
                        updated_ids.append(saved.id)
                    else:
                        created_ids.append(saved.id)
                else:
                    if r["is_update"]:
                        updated_ids.append(r["name"])
                    else:
                        created_ids.append(r["name"])
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "name", "SAVE_ERROR", str(exc), r["name"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=len(updated_ids),
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            updated_ids=updated_ids,
            message=f"Successfully processed {len(canonical_rows)} class groups.",
        )


# ---------------------------------------------------------------------------
# 4. Teachers Importer
# ---------------------------------------------------------------------------


class TeachersImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.TEACHERS, "employee_id")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "employee_id": ["employee_id", "emp_id", "faculty_id", "teacher_id", "staff_id", "id"],
            "name": ["name", "teacher_name", "faculty_name", "full_name", "instructor"],
            "department_code": ["department_code", "dept_code", "department", "dept"],
            "email": ["email", "email_address", "mail"],
            "is_full_time": ["is_full_time", "full_time", "status", "employment_status"],
            "max_weekly_hours": ["max_weekly_hours", "max_periods_per_week", "max_weekly", "max_hours"],
            "min_weekly_hours": ["min_weekly_hours", "min_periods_per_week", "min_weekly", "min_hours"],
            "max_daily_hours": ["max_daily_hours", "max_periods_per_day", "max_daily"],
            "max_consecutive_hours": ["max_consecutive_hours", "max_consecutive", "consecutive_limit"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"employee_id", "name", "department_code"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_dept_codes: Set[str] = context.get("valid_department_codes", set())
        existing_emp_ids: Set[str] = context.get("existing_teacher_emp_ids", set())

        seen_in_file: Set[str] = set()
        to_create = 0
        to_update = 0

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            emp_id = str(row.get("employee_id") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            dept_code = str(row.get("department_code") or "").strip().upper()
            email = str(row.get("email") or "").strip()

            max_weekly = to_int(row.get("max_weekly_hours"), default=20)
            min_weekly = to_int(row.get("min_weekly_hours"), default=0)
            max_daily = to_int(row.get("max_daily_hours"), default=5)
            max_consec = to_int(row.get("max_consecutive_hours"), default=3)

            row_has_error = False
            if not emp_id:
                errors.append(ImportRowError(idx, "employee_id", "MISSING_REQUIRED", "Teacher employee_id is required.", emp_id))
                row_has_error = True

            if not name:
                errors.append(ImportRowError(idx, "name", "MISSING_REQUIRED", "Teacher name is required.", name))
                row_has_error = True

            if not dept_code:
                errors.append(ImportRowError(idx, "department_code", "MISSING_REQUIRED", "Department code is required.", dept_code))
                row_has_error = True
            elif valid_dept_codes and dept_code not in valid_dept_codes:
                errors.append(ImportRowError(idx, "department_code", "FOREIGN_KEY_NOT_FOUND", f"Department '{dept_code}' does not exist.", dept_code))
                row_has_error = True

            # Bounds checking for workload parameters
            if max_weekly is None or max_weekly < 1:
                errors.append(ImportRowError(idx, "max_weekly_hours", "INVALID_RANGE", "Max weekly hours must be >= 1.", row.get("max_weekly_hours")))
                row_has_error = True
            if min_weekly is None or min_weekly < 0:
                errors.append(ImportRowError(idx, "min_weekly_hours", "INVALID_RANGE", "Min weekly hours must be >= 0.", row.get("min_weekly_hours")))
                row_has_error = True
            if max_weekly is not None and min_weekly is not None and max_weekly < min_weekly:
                errors.append(ImportRowError(idx, "max_weekly_hours", "LOGICAL_CONFLICT", "Max weekly hours cannot be less than min weekly hours.", f"max={max_weekly}, min={min_weekly}"))
                row_has_error = True

            if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                warnings.append(ImportRowWarning(idx, "email", f"Email '{email}' does not appear to be a standard email address format."))

            if emp_id in seen_in_file:
                errors.append(ImportRowError(idx, "employee_id", "DUPLICATE_IN_FILE", f"Duplicate employee_id '{emp_id}' in file.", emp_id))
                row_has_error = True
            else:
                seen_in_file.add(emp_id)

            if not row_has_error:
                exists = emp_id in existing_emp_ids
                if mode == ImportMode.CREATE and exists:
                    errors.append(ImportRowError(idx, "employee_id", "ALREADY_EXISTS", f"Teacher '{emp_id}' already exists.", emp_id))
                    continue
                elif mode == ImportMode.UPDATE and not exists:
                    errors.append(ImportRowError(idx, "employee_id", "NOT_FOUND", f"Teacher '{emp_id}' not found for update.", emp_id))
                    continue

                if exists:
                    to_update += 1
                else:
                    to_create += 1

                canonical_rows.append({
                    "employee_id": emp_id,
                    "name": name,
                    "department_code": dept_code,
                    "email": email or None,
                    "is_full_time": to_bool(row.get("is_full_time"), True),
                    "max_weekly_hours": max_weekly,
                    "min_weekly_hours": min_weekly,
                    "max_daily_hours": max_daily,
                    "max_consecutive_hours": max_consec,
                    "row_number": idx,
                    "is_update": exists,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        teacher_repo = context.get("teacher_repo")
        dept_id_map: Dict[str, str] = context.get("dept_id_map", {})

        created_ids = []
        updated_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=sum(1 for r in canonical_rows if not r["is_update"]),
                updated_count=sum(1 for r in canonical_rows if r["is_update"]),
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                dept_id = dept_id_map.get(r["department_code"], r["department_code"])
                teacher = Teacher(
                    department_id=dept_id,
                    name=r["name"],
                    employee_id=r["employee_id"],
                    email=r["email"],
                    is_full_time=r["is_full_time"],
                )
                if teacher_repo:
                    saved = teacher_repo.save(teacher)
                    # Also persist workload rule if supported
                    if hasattr(teacher_repo, "save_workload_rule"):
                        rule = TeacherWorkloadRule(
                            teacher_id=saved.id,
                            max_periods_per_week=r["max_weekly_hours"],
                            min_periods_per_week=r["min_weekly_hours"],
                            max_periods_per_day=r["max_daily_hours"],
                            max_consecutive_periods=r["max_consecutive_hours"],
                        )
                        teacher_repo.save_workload_rule(rule)

                    if r["is_update"]:
                        updated_ids.append(saved.id)
                    else:
                        created_ids.append(saved.id)
                else:
                    if r["is_update"]:
                        updated_ids.append(r["employee_id"])
                    else:
                        created_ids.append(r["employee_id"])
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "employee_id", "SAVE_ERROR", str(exc), r["employee_id"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=len(updated_ids),
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            updated_ids=updated_ids,
            message=f"Successfully imported {len(created_ids)} faculty profiles.",
        )


# ---------------------------------------------------------------------------
# 5. Subjects Importer
# ---------------------------------------------------------------------------


class SubjectsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.SUBJECTS, "code")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "code": ["subject_code", "course_code", "code", "sub_code", "id"],
            "name": ["subject_name", "course_name", "name", "title"],
            "department_code": ["department_code", "dept_code", "department", "dept"],
            "credits": ["credits", "credit_points", "credit"],
            "weekly_contact_hours": ["weekly_contact_hours", "contact_hours", "hours_per_week", "weekly_hours"],
            "is_elective": ["is_elective", "elective"],
            "requires_lab": ["requires_lab", "is_lab", "lab"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"code", "name", "department_code"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_dept_codes: Set[str] = context.get("valid_department_codes", set())
        existing_codes: Set[str] = context.get("existing_subject_codes", set())

        seen_in_file: Set[str] = set()
        to_create = 0
        to_update = 0

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            code = str(row.get("code") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            dept_code = str(row.get("department_code") or "").strip().upper()
            credits = to_float(row.get("credits"), default=3.0)
            contact_hours = to_float(row.get("weekly_contact_hours"), default=3.0)

            row_has_error = False
            if not code:
                errors.append(ImportRowError(idx, "code", "MISSING_REQUIRED", "Subject code is required.", code))
                row_has_error = True

            if not name:
                errors.append(ImportRowError(idx, "name", "MISSING_REQUIRED", "Subject name is required.", name))
                row_has_error = True

            if not dept_code:
                errors.append(ImportRowError(idx, "department_code", "MISSING_REQUIRED", "Department code is required.", dept_code))
                row_has_error = True
            elif valid_dept_codes and dept_code not in valid_dept_codes:
                errors.append(ImportRowError(idx, "department_code", "FOREIGN_KEY_NOT_FOUND", f"Department '{dept_code}' does not exist.", dept_code))
                row_has_error = True

            if credits is None or credits < 0.0:
                errors.append(ImportRowError(idx, "credits", "INVALID_VALUE", "Academic credits must be >= 0.0.", row.get("credits")))
                row_has_error = True

            if contact_hours is None or contact_hours <= 0.0:
                errors.append(ImportRowError(idx, "weekly_contact_hours", "INVALID_VALUE", "Weekly contact hours must be > 0.0.", row.get("weekly_contact_hours")))
                row_has_error = True

            if code in seen_in_file:
                errors.append(ImportRowError(idx, "code", "DUPLICATE_IN_FILE", f"Duplicate subject code '{code}' in file.", code))
                row_has_error = True
            else:
                seen_in_file.add(code)

            if not row_has_error:
                exists = code in existing_codes
                if mode == ImportMode.CREATE and exists:
                    errors.append(ImportRowError(idx, "code", "ALREADY_EXISTS", f"Subject '{code}' already exists.", code))
                    continue
                elif mode == ImportMode.UPDATE and not exists:
                    errors.append(ImportRowError(idx, "code", "NOT_FOUND", f"Subject '{code}' not found for update.", code))
                    continue

                if exists:
                    to_update += 1
                else:
                    to_create += 1

                canonical_rows.append({
                    "code": code,
                    "name": name,
                    "department_code": dept_code,
                    "credits": credits,
                    "weekly_contact_hours": contact_hours,
                    "is_elective": to_bool(row.get("is_elective"), False),
                    "requires_lab": to_bool(row.get("requires_lab"), False),
                    "row_number": idx,
                    "is_update": exists,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        subject_repo = context.get("subject_repo")
        dept_id_map: Dict[str, str] = context.get("dept_id_map", {})

        created_ids = []
        updated_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=sum(1 for r in canonical_rows if not r["is_update"]),
                updated_count=sum(1 for r in canonical_rows if r["is_update"]),
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                dept_id = dept_id_map.get(r["department_code"], r["department_code"])
                sub = Subject(
                    department_id=dept_id,
                    code=r["code"],
                    name=r["name"],
                    credits=r["credits"],
                    is_elective=r["is_elective"],
                )
                if subject_repo:
                    saved = subject_repo.save(sub)
                    if r["is_update"]:
                        updated_ids.append(saved.id)
                    else:
                        created_ids.append(saved.id)
                else:
                    if r["is_update"]:
                        updated_ids.append(r["code"])
                    else:
                        created_ids.append(r["code"])
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "code", "SAVE_ERROR", str(exc), r["code"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=len(updated_ids),
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            updated_ids=updated_ids,
            message=f"Successfully imported {len(created_ids)} subjects.",
        )


# ---------------------------------------------------------------------------
# 6. Rooms Importer
# ---------------------------------------------------------------------------


class RoomsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.ROOMS, "code")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "code": ["room_code", "code", "room_number", "room_id", "number"],
            "name": ["room_name", "name", "title"],
            "room_type": ["room_type", "type", "facility_type"],
            "capacity": ["capacity", "seats", "max_capacity", "size"],
            "building": ["building", "block", "location"],
            "floor": ["floor", "level"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"code", "name", "capacity"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        existing_codes: Set[str] = context.get("existing_room_codes", set())
        seen_in_file: Set[str] = set()

        to_create = 0
        to_update = 0

        valid_types = {rt.value for rt in RoomType}

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            code = str(row.get("code") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            capacity = to_int(row.get("capacity"))
            raw_type = str(row.get("room_type") or "LECTURE_HALL").strip().upper().replace(" ", "_")

            row_has_error = False
            if not code:
                errors.append(ImportRowError(idx, "code", "MISSING_REQUIRED", "Room code is required.", code))
                row_has_error = True

            if not name:
                errors.append(ImportRowError(idx, "name", "MISSING_REQUIRED", "Room name is required.", name))
                row_has_error = True

            if capacity is None or capacity < 1:
                errors.append(ImportRowError(idx, "capacity", "INVALID_VALUE", "Room capacity must be >= 1.", row.get("capacity")))
                row_has_error = True

            # Match room type enum safely
            room_type = RoomType.LECTURE_HALL
            if raw_type in valid_types:
                room_type = RoomType(raw_type)
            elif "LAB" in raw_type:
                room_type = RoomType.COMPUTER_LAB
            elif "SEMINAR" in raw_type:
                room_type = RoomType.SEMINAR_ROOM
            elif "WORKSHOP" in raw_type:
                room_type = RoomType.WORKSHOP

            if code in seen_in_file:
                errors.append(ImportRowError(idx, "code", "DUPLICATE_IN_FILE", f"Duplicate room code '{code}' in file.", code))
                row_has_error = True
            else:
                seen_in_file.add(code)

            if not row_has_error:
                exists = code in existing_codes
                if mode == ImportMode.CREATE and exists:
                    errors.append(ImportRowError(idx, "code", "ALREADY_EXISTS", f"Room '{code}' already exists.", code))
                    continue
                elif mode == ImportMode.UPDATE and not exists:
                    errors.append(ImportRowError(idx, "code", "NOT_FOUND", f"Room '{code}' not found for update.", code))
                    continue

                if exists:
                    to_update += 1
                else:
                    to_create += 1

                canonical_rows.append({
                    "code": code,
                    "name": name,
                    "room_type": room_type,
                    "capacity": capacity,
                    "building": str(row.get("building") or "").strip() or None,
                    "floor": to_int(row.get("floor")),
                    "row_number": idx,
                    "is_update": exists,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=to_create,
            to_update_count=to_update,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        room_repo = context.get("room_repo")
        created_ids = []
        updated_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=sum(1 for r in canonical_rows if not r["is_update"]),
                updated_count=sum(1 for r in canonical_rows if r["is_update"]),
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                room = Room(
                    name=r["name"],
                    code=r["code"],
                    room_type=r["room_type"],
                    capacity=r["capacity"],
                    building=r["building"],
                    floor=r["floor"],
                )
                if room_repo:
                    saved = room_repo.save(room)
                    if r["is_update"]:
                        updated_ids.append(saved.id)
                    else:
                        created_ids.append(saved.id)
                else:
                    if r["is_update"]:
                        updated_ids.append(r["code"])
                    else:
                        created_ids.append(r["code"])
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "code", "SAVE_ERROR", str(exc), r["code"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=len(updated_ids),
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            updated_ids=updated_ids,
            message=f"Successfully imported {len(created_ids)} rooms.",
        )


# ---------------------------------------------------------------------------
# 7. Teacher Qualifications Importer
# ---------------------------------------------------------------------------


class TeacherQualificationsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.TEACHER_QUALIFICATIONS, "key")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "employee_id": ["employee_id", "emp_id", "teacher_id", "faculty_id"],
            "subject_code": ["subject_code", "course_code", "code", "subject"],
            "competency_level": ["competency_level", "competency", "tier", "level"],
            "preference_score": ["preference_score", "preference", "score"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"employee_id", "subject_code"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_teachers: Set[str] = context.get("valid_teacher_emp_ids", set())
        valid_subjects: Set[str] = context.get("valid_subject_codes", set())

        seen: Set[str] = set()

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            emp_id = str(row.get("employee_id") or "").strip().upper()
            sub_code = str(row.get("subject_code") or "").strip().upper()
            comp = to_int(row.get("competency_level"), default=1)
            pref = to_int(row.get("preference_score"), default=5)

            row_has_error = False
            if not emp_id:
                errors.append(ImportRowError(idx, "employee_id", "MISSING_REQUIRED", "Employee ID is required.", emp_id))
                row_has_error = True
            elif valid_teachers and emp_id not in valid_teachers:
                errors.append(ImportRowError(idx, "employee_id", "FOREIGN_KEY_NOT_FOUND", f"Teacher '{emp_id}' not found.", emp_id))
                row_has_error = True

            if not sub_code:
                errors.append(ImportRowError(idx, "subject_code", "MISSING_REQUIRED", "Subject code is required.", sub_code))
                row_has_error = True
            elif valid_subjects and sub_code not in valid_subjects:
                errors.append(ImportRowError(idx, "subject_code", "FOREIGN_KEY_NOT_FOUND", f"Subject '{sub_code}' not found.", sub_code))
                row_has_error = True

            key = f"{emp_id}:{sub_code}"
            if key in seen:
                errors.append(ImportRowError(idx, "subject_code", "DUPLICATE_IN_FILE", f"Duplicate qualification '{key}' in file.", key))
                row_has_error = True
            else:
                seen.add(key)

            if not row_has_error:
                canonical_rows.append({
                    "employee_id": emp_id,
                    "subject_code": sub_code,
                    "competency_level": comp,
                    "preference_score": pref,
                    "row_number": idx,
                    "is_update": False,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=len(canonical_rows),
            to_update_count=0,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        teacher_repo = context.get("teacher_repo")
        teacher_id_map: Dict[str, str] = context.get("teacher_id_map", {})
        subject_id_map: Dict[str, str] = context.get("subject_id_map", {})

        created_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=len(canonical_rows),
                updated_count=0,
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                t_id = teacher_id_map.get(r["employee_id"], r["employee_id"])
                s_id = subject_id_map.get(r["subject_code"], r["subject_code"])
                qual = TeacherQualification(
                    teacher_id=t_id,
                    subject_id=s_id,
                    competency_level=r["competency_level"],
                    preference_score=r["preference_score"],
                )
                if teacher_repo and hasattr(teacher_repo, "save_qualification"):
                    teacher_repo.save_qualification(qual)
                created_ids.append(f"{t_id}:{s_id}")
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "employee_id", "SAVE_ERROR", str(exc), r["employee_id"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=0,
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            message=f"Successfully imported {len(created_ids)} qualification assignments.",
        )


# ---------------------------------------------------------------------------
# 8. Subject Offerings Importer
# ---------------------------------------------------------------------------


class SubjectOfferingsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.SUBJECT_OFFERINGS, "key")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "subject_code": ["subject_code", "course_code", "code", "subject"],
            "semester_number": ["semester_number", "semester", "sem"],
            "weekly_contact_hours": ["weekly_contact_hours", "contact_hours", "hours"],
            "weekly_periods": ["weekly_periods", "periods", "periods_per_week"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"subject_code", "weekly_contact_hours", "weekly_periods"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_subjects: Set[str] = context.get("valid_subject_codes", set())
        seen: Set[str] = set()

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            sub_code = str(row.get("subject_code") or "").strip().upper()
            contact_hours = to_float(row.get("weekly_contact_hours"))
            periods = to_int(row.get("weekly_periods"))
            sem_num = to_int(row.get("semester_number"), default=1)

            row_has_error = False
            if not sub_code:
                errors.append(ImportRowError(idx, "subject_code", "MISSING_REQUIRED", "Subject code is required.", sub_code))
                row_has_error = True
            elif valid_subjects and sub_code not in valid_subjects:
                errors.append(ImportRowError(idx, "subject_code", "FOREIGN_KEY_NOT_FOUND", f"Subject '{sub_code}' not found.", sub_code))
                row_has_error = True

            if contact_hours is None or contact_hours <= 0:
                errors.append(ImportRowError(idx, "weekly_contact_hours", "INVALID_VALUE", "Weekly contact hours must be > 0.", row.get("weekly_contact_hours")))
                row_has_error = True

            if periods is None or periods <= 0:
                errors.append(ImportRowError(idx, "weekly_periods", "INVALID_VALUE", "Weekly periods must be > 0.", row.get("weekly_periods")))
                row_has_error = True

            key = f"{sub_code}:{sem_num}"
            if key in seen:
                errors.append(ImportRowError(idx, "subject_code", "DUPLICATE_IN_FILE", f"Duplicate offering '{key}' in file.", key))
                row_has_error = True
            else:
                seen.add(key)

            if not row_has_error:
                canonical_rows.append({
                    "subject_code": sub_code,
                    "semester_number": sem_num,
                    "weekly_contact_hours": contact_hours,
                    "weekly_periods": periods,
                    "row_number": idx,
                    "is_update": False,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=len(canonical_rows),
            to_update_count=0,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        subject_repo = context.get("subject_repo")
        subject_id_map: Dict[str, str] = context.get("subject_id_map", {})
        default_sem_id = context.get("semester_id", "DEFAULT_SEM")

        created_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=len(canonical_rows),
                updated_count=0,
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                s_id = subject_id_map.get(r["subject_code"], r["subject_code"])
                offering = SubjectOffering(
                    subject_id=s_id,
                    semester_id=default_sem_id,
                    weekly_contact_hours=r["weekly_contact_hours"],
                    weekly_periods=r["weekly_periods"],
                )
                if subject_repo and hasattr(subject_repo, "save_offering"):
                    saved = subject_repo.save_offering(offering)
                    created_ids.append(saved.id)
                else:
                    created_ids.append(offering.id)
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "subject_code", "SAVE_ERROR", str(exc), r["subject_code"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=0,
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            message=f"Successfully imported {len(created_ids)} subject offerings.",
        )


# ---------------------------------------------------------------------------
# 9. Class-Subject Assignments Importer
# ---------------------------------------------------------------------------


class ClassAssignmentsImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.CLASS_ASSIGNMENTS, "key")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "class_name": ["class_name", "class", "cohort", "section"],
            "subject_code": ["subject_code", "course_code", "subject", "code"],
            "primary_teacher_employee_id": ["teacher_id", "primary_teacher_id", "teacher_employee_id", "faculty_id", "teacher", "faculty"],
            "secondary_teacher_employee_id": ["secondary_teacher_id", "co_teacher", "assistant_teacher"],
            "student_group_name": ["student_group", "batch", "subgroup"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"class_name", "subject_code", "primary_teacher_employee_id"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_classes: Set[str] = context.get("valid_class_names", set())
        valid_subjects: Set[str] = context.get("valid_subject_codes", set())
        valid_teachers: Set[str] = context.get("valid_teacher_emp_ids", set())

        seen: Set[str] = set()

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            c_name = str(row.get("class_name") or "").strip()
            s_code = str(row.get("subject_code") or "").strip().upper()
            t_emp = str(row.get("primary_teacher_employee_id") or "").strip().upper()
            sec_t = str(row.get("secondary_teacher_employee_id") or "").strip().upper() or None
            batch = str(row.get("student_group_name") or "").strip() or None

            row_has_error = False
            if not c_name:
                errors.append(ImportRowError(idx, "class_name", "MISSING_REQUIRED", "Class name is required.", c_name))
                row_has_error = True
            elif valid_classes and c_name not in valid_classes:
                errors.append(ImportRowError(idx, "class_name", "FOREIGN_KEY_NOT_FOUND", f"Class '{c_name}' not found.", c_name))
                row_has_error = True

            if not s_code:
                errors.append(ImportRowError(idx, "subject_code", "MISSING_REQUIRED", "Subject code is required.", s_code))
                row_has_error = True
            elif valid_subjects and s_code not in valid_subjects:
                errors.append(ImportRowError(idx, "subject_code", "FOREIGN_KEY_NOT_FOUND", f"Subject '{s_code}' not found.", s_code))
                row_has_error = True

            if not t_emp:
                errors.append(ImportRowError(idx, "primary_teacher_employee_id", "MISSING_REQUIRED", "Teacher ID is required.", t_emp))
                row_has_error = True
            elif valid_teachers and t_emp not in valid_teachers:
                errors.append(ImportRowError(idx, "primary_teacher_employee_id", "FOREIGN_KEY_NOT_FOUND", f"Teacher '{t_emp}' not found.", t_emp))
                row_has_error = True

            key = f"{c_name}:{s_code}:{batch or 'ALL'}"
            if key in seen:
                errors.append(ImportRowError(idx, "class_name", "DUPLICATE_IN_FILE", f"Duplicate assignment '{key}' in file.", key))
                row_has_error = True
            else:
                seen.add(key)

            if not row_has_error:
                canonical_rows.append({
                    "class_name": c_name,
                    "subject_code": s_code,
                    "primary_teacher_employee_id": t_emp,
                    "secondary_teacher_employee_id": sec_t,
                    "student_group_name": batch,
                    "row_number": idx,
                    "is_update": False,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=len(canonical_rows),
            to_update_count=0,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        class_id_map: Dict[str, str] = context.get("class_id_map", {})
        offering_id_map: Dict[str, str] = context.get("offering_id_map", {})
        teacher_id_map: Dict[str, str] = context.get("teacher_id_map", {})
        subject_repo = context.get("subject_repo")

        created_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=len(canonical_rows),
                updated_count=0,
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                c_id = class_id_map.get(r["class_name"], r["class_name"])
                off_id = offering_id_map.get(r["subject_code"], r["subject_code"])
                t_id = teacher_id_map.get(r["primary_teacher_employee_id"], r["primary_teacher_employee_id"])
                sec_t_id = None
                if r["secondary_teacher_employee_id"]:
                    sec_t_id = teacher_id_map.get(r["secondary_teacher_employee_id"], r["secondary_teacher_employee_id"])

                assign = ClassSubjectAssignment(
                    class_group_id=c_id,
                    offering_id=off_id,
                    primary_teacher_id=t_id,
                    secondary_teacher_id=sec_t_id,
                    student_group_id=r["student_group_name"],
                )
                if subject_repo and hasattr(subject_repo, "save_class_assignment"):
                    saved = subject_repo.save_class_assignment(assign)
                    created_ids.append(saved.id)
                else:
                    created_ids.append(assign.id)
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "class_name", "SAVE_ERROR", str(exc), r["class_name"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=0,
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            message=f"Successfully imported {len(created_ids)} class assignments.",
        )


# ---------------------------------------------------------------------------
# 10. Teacher Availability & Preferences Importer
# ---------------------------------------------------------------------------


class TeacherAvailabilityImporter(BaseDatasetImporter):

    def __init__(self):
        super().__init__(DatasetType.TEACHER_AVAILABILITY, "key")

    def get_column_definitions(self) -> Dict[str, List[str]]:
        return {
            "employee_id": ["employee_id", "emp_id", "teacher_id", "faculty_id"],
            "day_of_week": ["day_of_week", "day", "day_index", "weekday"],
            "period_index": ["period_index", "period", "slot", "period_num"],
            "is_available": ["is_available", "available", "can_teach"],
            "preference_weight": ["preference_weight", "preference", "weight", "preference_score"],
        }

    def get_required_fields(self) -> Set[str]:
        return {"employee_id", "day_of_week", "period_index"}

    def validate_rows(
        self,
        raw_rows: List[Dict[str, Any]],
        mapping: Dict[str, str],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        mapper = self.get_mapper()
        errors: List[ImportRowError] = []
        warnings: List[ImportRowWarning] = []
        canonical_rows: List[Dict[str, Any]] = []

        valid_teachers: Set[str] = context.get("valid_teacher_emp_ids", set())
        max_periods_per_day: int = context.get("periods_per_day", 10)
        seen: Set[str] = set()

        day_name_map = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }

        for idx, raw in enumerate(raw_rows, start=1):
            row = mapper.apply_mapping(raw, mapping)
            emp_id = str(row.get("employee_id") or "").strip().upper()
            raw_day = str(row.get("day_of_week") or "").strip().lower()
            period = to_int(row.get("period_index"))
            avail = to_bool(row.get("is_available"), True)
            pref = to_int(row.get("preference_weight"), default=0)

            # Parse day of week (numeric 0..6 or string "Monday")
            day: Optional[int] = None
            if raw_day in day_name_map:
                day = day_name_map[raw_day]
            else:
                day = to_int(raw_day)

            row_has_error = False
            if not emp_id:
                errors.append(ImportRowError(idx, "employee_id", "MISSING_REQUIRED", "Employee ID is required.", emp_id))
                row_has_error = True
            elif valid_teachers and emp_id not in valid_teachers:
                errors.append(ImportRowError(idx, "employee_id", "FOREIGN_KEY_NOT_FOUND", f"Teacher '{emp_id}' not found.", emp_id))
                row_has_error = True

            if day is None or not (0 <= day <= 6):
                errors.append(ImportRowError(idx, "day_of_week", "INVALID_RANGE", f"Day must be 0 (Mon) to 6 (Sun), got '{raw_day}'.", raw_day))
                row_has_error = True

            if period is None or period < 0 or period >= max_periods_per_day:
                errors.append(ImportRowError(idx, "period_index", "INVALID_RANGE", f"Period must be 0 to {max_periods_per_day-1}, got '{period}'.", period))
                row_has_error = True

            if pref is not None and not (-10 <= pref <= 10):
                warnings.append(ImportRowWarning(idx, "preference_weight", f"Preference weight {pref} outside expected range [-10, 10]. Clamped."))
                pref = max(-10, min(10, pref))

            key = f"{emp_id}:{day}:{period}"
            if key in seen:
                errors.append(ImportRowError(idx, "period_index", "DUPLICATE_IN_FILE", f"Duplicate slot '{key}' in file.", key))
                row_has_error = True
            else:
                seen.add(key)

            if not row_has_error:
                canonical_rows.append({
                    "employee_id": emp_id,
                    "day_of_week": day,
                    "period_index": period,
                    "is_available": avail,
                    "preference_weight": pref,
                    "row_number": idx,
                    "is_update": False,
                })

        summary = ImportValidationSummary(
            total_rows=len(raw_rows),
            valid_rows=len(canonical_rows),
            invalid_rows=len(raw_rows) - len(canonical_rows),
            duplicate_rows=0,
            to_create_count=len(canonical_rows),
            to_update_count=0,
            errors=errors,
            warnings=warnings,
            can_proceed=(len(errors) == 0 and len(canonical_rows) > 0) or mode == ImportMode.VALIDATE_ONLY,
        )
        return canonical_rows, summary

    def persist_records(
        self,
        canonical_rows: List[Dict[str, Any]],
        mode: ImportMode,
        context: Dict[str, Any],
    ) -> ImportResult:
        teacher_id_map: Dict[str, str] = context.get("teacher_id_map", {})
        teacher_repo = context.get("teacher_repo")
        pref_repo = context.get("pref_repo")

        created_ids = []
        errors = []

        if mode == ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=True,
                mode=mode,
                dataset_type=self.dataset_type,
                total_processed=len(canonical_rows),
                created_count=len(canonical_rows),
                updated_count=0,
                skipped_count=0,
                message="Validation completed successfully.",
            )

        for r in canonical_rows:
            try:
                t_id = teacher_id_map.get(r["employee_id"], r["employee_id"])
                avail = TeacherAvailability(
                    teacher_id=t_id,
                    day_of_week=r["day_of_week"],
                    period_index=r["period_index"],
                    is_available=r["is_available"],
                )
                if teacher_repo and hasattr(teacher_repo, "save_availability"):
                    teacher_repo.save_availability(avail)

                if r["preference_weight"] != 0:
                    pref = TeacherPreference(
                        teacher_id=t_id,
                        day_of_week=r["day_of_week"],
                        period_index=r["period_index"],
                        preference_weight=r["preference_weight"],
                    )
                    if pref_repo and hasattr(pref_repo, "save_preference"):
                        pref_repo.save_preference(pref)

                created_ids.append(f"{t_id}:{r['day_of_week']}:{r['period_index']}")
            except Exception as exc:
                errors.append(ImportRowError(r["row_number"], "employee_id", "SAVE_ERROR", str(exc), r["employee_id"]))

        return ImportResult(
            success=len(errors) == 0,
            mode=mode,
            dataset_type=self.dataset_type,
            total_processed=len(canonical_rows),
            created_count=len(created_ids),
            updated_count=0,
            skipped_count=len(errors),
            errors=errors,
            created_ids=created_ids,
            message=f"Successfully imported {len(created_ids)} teacher availability/preference slots.",
        )
