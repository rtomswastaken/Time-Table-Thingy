"""Safe CSV exporters for scheduled sessions, faculty workloads, assignments, rooms, and conflicts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import ScheduledSession
from exchange.models import (
    ConflictReportRow,
    ExportFormat,
    ExportResult,
    RoomUtilizationRow,
    UnscheduledSessionRow,
    WorkloadReportRow,
)
from exchange.security import sanitize_spreadsheet_value, validate_export_file_path

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class CSVExporter:
    """Exports timetable schedules and analytical reports to standard CSV files."""

    @classmethod
    def export_sessions(
        cls,
        sessions: List[ScheduledSession],
        output_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExportResult:
        """Exports placed sessions with stable identifiers and human-readable metadata."""
        dest = validate_export_file_path(output_path, expected_ext=".csv")
        meta = metadata or {}

        fieldnames = [
            "session_id",
            "timetable_id",
            "day_index",
            "day_name",
            "start_period",
            "duration_periods",
            "class_group_id",
            "class_name",
            "subject_id",
            "subject_code",
            "subject_name",
            "teacher_id",
            "teacher_employee_id",
            "teacher_name",
            "room_id",
            "room_code",
            "room_name",
            "session_type",
            "student_group_id",
            "is_locked",
        ]

        class_name_map = meta.get("class_name_map", {})
        sub_code_map = meta.get("sub_code_map", {})
        sub_name_map = meta.get("sub_name_map", {})
        teacher_emp_map = meta.get("teacher_emp_map", {})
        teacher_name_map = meta.get("teacher_name_map", {})
        room_code_map = meta.get("room_code_map", {})
        room_name_map = meta.get("room_name_map", {})

        count = 0
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()

            for s in sessions:
                day_name = DAY_NAMES[s.day_of_week] if 0 <= s.day_of_week < len(DAY_NAMES) else f"Day {s.day_of_week}"
                row = {
                    "session_id": sanitize_spreadsheet_value(s.id),
                    "timetable_id": sanitize_spreadsheet_value(s.timetable_id),
                    "day_index": s.day_of_week,
                    "day_name": day_name,
                    "start_period": s.start_period,
                    "duration_periods": s.duration_periods,
                    "class_group_id": sanitize_spreadsheet_value(s.class_group_id),
                    "class_name": sanitize_spreadsheet_value(class_name_map.get(s.class_group_id, "")),
                    "subject_id": sanitize_spreadsheet_value(meta.get("session_subject_id_map", {}).get(s.id, "")),
                    "subject_code": sanitize_spreadsheet_value(sub_code_map.get(s.class_group_id, "")),
                    "subject_name": sanitize_spreadsheet_value(sub_name_map.get(s.class_group_id, "")),
                    "teacher_id": sanitize_spreadsheet_value(s.teacher_id),
                    "teacher_employee_id": sanitize_spreadsheet_value(teacher_emp_map.get(s.teacher_id, "")),
                    "teacher_name": sanitize_spreadsheet_value(teacher_name_map.get(s.teacher_id, "")),
                    "room_id": sanitize_spreadsheet_value(s.room_id),
                    "room_code": sanitize_spreadsheet_value(room_code_map.get(s.room_id, "")),
                    "room_name": sanitize_spreadsheet_value(room_name_map.get(s.room_id, "")),
                    "session_type": "THEORY",
                    "student_group_id": sanitize_spreadsheet_value(s.student_group_id or ""),
                    "is_locked": 1 if s.is_locked else 0,
                }
                writer.writerow(row)
                count += 1

        file_size = dest.stat().st_size
        return ExportResult(
            success=True,
            format=ExportFormat.CSV,
            file_path=str(dest),
            file_size_bytes=file_size,
            records_exported=count,
            message=f"Exported {count} sessions to {dest.name}.",
        )

    @classmethod
    def export_workload_report(
        cls,
        rows: List[WorkloadReportRow],
        output_path: str | Path,
    ) -> ExportResult:
        """Exports teacher workload calculation rows to CSV."""
        dest = validate_export_file_path(output_path, expected_ext=".csv")
        fieldnames = [
            "teacher_id",
            "employee_id",
            "teacher_name",
            "department_name",
            "assigned_periods",
            "assigned_contact_hours",
            "min_periods",
            "max_periods",
            "remaining_capacity",
            "max_consecutive_observed",
            "is_overloaded",
            "is_underloaded",
            "has_workload_rule",
            "warning_message",
        ]

        count = 0
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()

            for r in rows:
                writer.writerow({
                    "teacher_id": sanitize_spreadsheet_value(r.teacher_id),
                    "employee_id": sanitize_spreadsheet_value(r.employee_id),
                    "teacher_name": sanitize_spreadsheet_value(r.teacher_name),
                    "department_name": sanitize_spreadsheet_value(r.department_name),
                    "assigned_periods": r.assigned_periods,
                    "assigned_contact_hours": r.assigned_contact_hours,
                    "min_periods": r.min_periods if r.min_periods is not None else "",
                    "max_periods": r.max_periods if r.max_periods is not None else "",
                    "remaining_capacity": r.remaining_capacity if r.remaining_capacity is not None else "",
                    "max_consecutive_observed": r.max_consecutive_observed,
                    "is_overloaded": 1 if r.is_overloaded else 0,
                    "is_underloaded": 1 if r.is_underloaded else 0,
                    "has_workload_rule": 1 if r.has_workload_rule else 0,
                    "warning_message": sanitize_spreadsheet_value(r.warning_message),
                })
                count += 1

        return ExportResult(
            success=True,
            format=ExportFormat.CSV,
            file_path=str(dest),
            file_size_bytes=dest.stat().st_size,
            records_exported=count,
            message=f"Exported {count} workload rows to {dest.name}.",
        )

    @classmethod
    def export_room_utilization(
        cls,
        rows: List[RoomUtilizationRow],
        output_path: str | Path,
    ) -> ExportResult:
        """Exports room utilization calculation rows to CSV."""
        dest = validate_export_file_path(output_path, expected_ext=".csv")
        fieldnames = [
            "room_id",
            "room_code",
            "room_name",
            "room_type",
            "capacity",
            "building",
            "scheduled_sessions_count",
            "occupied_periods",
            "available_periods",
            "utilization_rate_pct",
            "notes",
        ]

        count = 0
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()

            for r in rows:
                writer.writerow({
                    "room_id": sanitize_spreadsheet_value(r.room_id),
                    "room_code": sanitize_spreadsheet_value(r.room_code),
                    "room_name": sanitize_spreadsheet_value(r.room_name),
                    "room_type": sanitize_spreadsheet_value(r.room_type),
                    "capacity": r.capacity,
                    "building": sanitize_spreadsheet_value(r.building),
                    "scheduled_sessions_count": r.scheduled_sessions_count,
                    "occupied_periods": r.occupied_periods,
                    "available_periods": r.available_periods,
                    "utilization_rate_pct": f"{r.utilization_rate:.2f}",
                    "notes": sanitize_spreadsheet_value(r.notes),
                })
                count += 1

        return ExportResult(
            success=True,
            format=ExportFormat.CSV,
            file_path=str(dest),
            file_size_bytes=dest.stat().st_size,
            records_exported=count,
            message=f"Exported {count} room utilization rows to {dest.name}.",
        )

    @classmethod
    def export_conflicts(
        cls,
        rows: List[ConflictReportRow],
        output_path: str | Path,
    ) -> ExportResult:
        """Exports scheduling conflict and constraint violation records to CSV."""
        dest = validate_export_file_path(output_path, expected_ext=".csv")
        fieldnames = [
            "violation_type",
            "severity",
            "is_hard",
            "description",
            "involved_teachers",
            "involved_rooms",
            "involved_classes",
            "remediation_suggestion",
        ]

        count = 0
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()

            for r in rows:
                writer.writerow({
                    "violation_type": sanitize_spreadsheet_value(r.violation_type),
                    "severity": r.severity,
                    "is_hard": 1 if r.is_hard else 0,
                    "description": sanitize_spreadsheet_value(r.description),
                    "involved_teachers": "; ".join(r.involved_teachers),
                    "involved_rooms": "; ".join(r.involved_rooms),
                    "involved_classes": "; ".join(r.involved_classes),
                    "remediation_suggestion": sanitize_spreadsheet_value(r.remediation_suggestion),
                })
                count += 1

        return ExportResult(
            success=True,
            format=ExportFormat.CSV,
            file_path=str(dest),
            file_size_bytes=dest.stat().st_size,
            records_exported=count,
            message=f"Exported {count} conflict rows to {dest.name}.",
        )

    @classmethod
    def export_unscheduled_sessions(
        cls,
        rows: List[UnscheduledSessionRow],
        output_path: str | Path,
    ) -> ExportResult:
        """Exports unscheduled curricular session requirements to CSV."""
        dest = validate_export_file_path(output_path, expected_ext=".csv")
        fieldnames = [
            "offering_id",
            "subject_code",
            "subject_name",
            "class_name",
            "teacher_name",
            "required_sessions",
            "placed_sessions",
            "missing_count",
            "reason",
        ]

        count = 0
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()

            for r in rows:
                writer.writerow({
                    "offering_id": sanitize_spreadsheet_value(r.offering_id),
                    "subject_code": sanitize_spreadsheet_value(r.subject_code),
                    "subject_name": sanitize_spreadsheet_value(r.subject_name),
                    "class_name": sanitize_spreadsheet_value(r.class_name),
                    "teacher_name": sanitize_spreadsheet_value(r.teacher_name),
                    "required_sessions": r.required_sessions,
                    "placed_sessions": r.placed_sessions,
                    "missing_count": r.missing_count,
                    "reason": sanitize_spreadsheet_value(r.reason),
                })
                count += 1

        return ExportResult(
            success=True,
            format=ExportFormat.CSV,
            file_path=str(dest),
            file_size_bytes=dest.stat().st_size,
            records_exported=count,
            message=f"Exported {count} unscheduled session rows to {dest.name}.",
        )
