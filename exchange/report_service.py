"""ReportService implementation.

Satisfies core.interfaces.ReportService protocol and provides
analytical evaluations of faculty workload, room utilization, and scheduling conflicts.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import ReportService as IReportService
from core.models import (
    ConstraintViolation,
    Institution,
    Room,
    ScheduledSession,
    Teacher,
    TeacherWorkloadRule,
    Timetable,
)
from exchange.exporters.csv_exporter import CSVExporter
from exchange.exporters.excel_exporter import ExcelExporter
from exchange.models import (
    ConflictReportRow,
    ExportFormat,
    ExportResult,
    RoomUtilizationRow,
    TimetableSummary,
    UnscheduledSessionRow,
    WorkloadReportRow,
)
from exchange.reports.conflict_report import ConflictReportGenerator
from exchange.reports.room_utilization_report import RoomUtilizationReportGenerator
from exchange.reports.timetable_summary_report import TimetableSummaryReportGenerator
from exchange.reports.workload_report import WorkloadReportGenerator


class ReportServiceImpl:
    """Core implementation of ReportService."""

    def __init__(
        self,
        repositories: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.repositories = repositories or {}
        self.context = context or {}

    def get_workload_report_data(
        self,
        timetable_id: str,
        department_filter: Optional[str] = None,
    ) -> List[WorkloadReportRow]:
        """Calculates workload metrics for all teachers based on timetable assignments."""
        teachers, sessions, rules, institution, dept_names = self._load_workload_inputs(timetable_id)
        return WorkloadReportGenerator.generate_report(
            teachers=teachers,
            sessions=sessions,
            rules=rules,
            institution=institution,
            department_filter=department_filter,
            department_names=dept_names,
        )

    def get_room_utilization_data(self, timetable_id: str) -> List[RoomUtilizationRow]:
        """Calculates room utilization rates and capacity efficiency."""
        rooms, sessions, institution, room_unavail = self._load_room_inputs(timetable_id)
        return RoomUtilizationReportGenerator.generate_report(
            rooms=rooms,
            sessions=sessions,
            institution=institution,
            room_availabilities=room_unavail,
        )

    def get_conflict_report_data(self, timetable_id: str) -> List[ConflictReportRow]:
        """Retrieves and classifies scheduling conflicts and constraint warnings."""
        violations = self.context.get("violations", [])
        result = self.context.get("scheduling_result")
        return ConflictReportGenerator.generate_conflict_report(result=result, violations=violations)

    def get_unscheduled_report_data(self, timetable_id: str) -> List[UnscheduledSessionRow]:
        """Identifies curricular requirements that could not be placed."""
        required_units = self.context.get("required_units", [])
        sessions = self._load_sessions(timetable_id)
        metadata = self.context.get("metadata", {})
        return ConflictReportGenerator.generate_unscheduled_report(
            required_units=required_units,
            scheduled_sessions=sessions,
            metadata=metadata,
        )

    def get_timetable_summary_data(self, timetable_id: str) -> TimetableSummary:
        """Compiles executive summary statistics for a timetable."""
        sessions = self._load_sessions(timetable_id)
        tt = self._load_timetable(timetable_id)
        violations = self.context.get("violations", [])
        unscheduled = self.get_unscheduled_report_data(timetable_id)
        room_rows = self.get_room_utilization_data(timetable_id)
        metadata = self.context.get("metadata", {})

        return TimetableSummaryReportGenerator.generate_summary(
            timetable=tt,
            sessions=sessions,
            violations=violations,
            unscheduled_count=len(unscheduled),
            room_utilization_rows=room_rows,
            metadata=metadata,
        )

    def export_report(
        self,
        report_type: str,
        timetable_id: str,
        output_path: str,
        format: ExportFormat = ExportFormat.EXCEL,
    ) -> ExportResult:
        """Exports a named report (WORKLOAD, ROOM_UTILIZATION, CONFLICTS, UNSCHEDULED, FULL)

        to the specified file path.
        """
        rtype = report_type.upper()
        if rtype == "WORKLOAD":
            rows = self.get_workload_report_data(timetable_id)
            if format == ExportFormat.CSV:
                return CSVExporter.export_workload_report(rows, output_path)
            else:
                return ExcelExporter.export_full_workbook(output_path, workload_rows=rows)

        elif rtype == "ROOM_UTILIZATION":
            rows = self.get_room_utilization_data(timetable_id)
            if format == ExportFormat.CSV:
                return CSVExporter.export_room_utilization(rows, output_path)
            else:
                return ExcelExporter.export_full_workbook(output_path, room_rows=rows)

        elif rtype == "CONFLICTS":
            rows = self.get_conflict_report_data(timetable_id)
            if format == ExportFormat.CSV:
                return CSVExporter.export_conflicts(rows, output_path)
            else:
                return ExcelExporter.export_full_workbook(output_path, conflict_rows=rows)

        elif rtype == "UNSCHEDULED":
            rows = self.get_unscheduled_report_data(timetable_id)
            if format == ExportFormat.CSV:
                return CSVExporter.export_unscheduled_sessions(rows, output_path)
            else:
                return ExcelExporter.export_full_workbook(output_path, unscheduled_rows=rows)

        else:  # Full comprehensive report
            sessions = self._load_sessions(timetable_id)
            w_rows = self.get_workload_report_data(timetable_id)
            r_rows = self.get_room_utilization_data(timetable_id)
            c_rows = self.get_conflict_report_data(timetable_id)
            u_rows = self.get_unscheduled_report_data(timetable_id)
            meta = self.context.get("metadata", {})
            return ExcelExporter.export_full_workbook(
                output_path,
                sessions=sessions,
                workload_rows=w_rows,
                room_rows=r_rows,
                conflict_rows=c_rows,
                unscheduled_rows=u_rows,
                metadata=meta,
            )

    # -----------------------------------------------------------------------
    # Protocol Methods (core.interfaces.ReportService)
    # -----------------------------------------------------------------------

    def generate_workload_report(self, timetable_id: str) -> str:
        """Generates faculty workload report workbook and returns output file path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        res = self.export_report("WORKLOAD", timetable_id, tmp.name, format=ExportFormat.EXCEL)
        return res.file_path

    def generate_room_utilization_report(self, timetable_id: str) -> str:
        """Generates room utilization report workbook and returns output file path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        res = self.export_report("ROOM_UTILIZATION", timetable_id, tmp.name, format=ExportFormat.EXCEL)
        return res.file_path

    # -----------------------------------------------------------------------
    # Helper Data Loaders
    # -----------------------------------------------------------------------

    def _load_sessions(self, timetable_id: str) -> List[ScheduledSession]:
        tt_repo = self.repositories.get("tt_repo") or self.repositories.get("timetable_repo")
        if tt_repo and hasattr(tt_repo, "get_sessions"):
            return tt_repo.get_sessions(timetable_id)
        return self.context.get("sessions", [])

    def _load_timetable(self, timetable_id: str) -> Timetable:
        tt_repo = self.repositories.get("tt_repo") or self.repositories.get("timetable_repo")
        if tt_repo and hasattr(tt_repo, "get_by_id"):
            tt = tt_repo.get_by_id(timetable_id)
            if tt:
                return tt
        return Timetable(
            id=timetable_id,
            name=self.context.get("metadata", {}).get("timetable_name", "Academic Timetable"),
            academic_year_id="AY-2026",
            semester_id="SEM-1",
        )

    def _load_workload_inputs(
        self,
        timetable_id: str,
    ) -> Tuple[List[Teacher], List[ScheduledSession], Dict[str, TeacherWorkloadRule], Optional[Institution], Dict[str, str]]:
        teacher_repo = self.repositories.get("teacher_repo")
        teachers: List[Teacher] = []
        rules: Dict[str, TeacherWorkloadRule] = {}

        if teacher_repo and hasattr(teacher_repo, "list_all"):
            teachers = teacher_repo.list_all()
            if hasattr(teacher_repo, "get_workload_rule"):
                for t in teachers:
                    r = teacher_repo.get_workload_rule(t.id)
                    if r:
                        rules[t.id] = r
        else:
            teachers = self.context.get("teachers", [])
            rules = self.context.get("teacher_workload_rules", {})

        sessions = self._load_sessions(timetable_id)
        institution = self.context.get("institution")

        dept_names: Dict[str, str] = {}
        dept_repo = self.repositories.get("department_repo")
        if dept_repo and hasattr(dept_repo, "list_all"):
            for d in dept_repo.list_all():
                dept_names[d.id] = d.name

        return teachers, sessions, rules, institution, dept_names

    def _load_room_inputs(
        self,
        timetable_id: str,
    ) -> Tuple[List[Room], List[ScheduledSession], Optional[Institution], Dict[str, set]]:
        room_repo = self.repositories.get("room_repo")
        rooms: List[Room] = []
        if room_repo and hasattr(room_repo, "list_all"):
            rooms = room_repo.list_all()
        else:
            rooms = self.context.get("rooms", [])

        sessions = self._load_sessions(timetable_id)
        institution = self.context.get("institution")
        room_unavail = self.context.get("room_availability", {})
        return rooms, sessions, institution, room_unavail


# Compatibility alias
ReportService = ReportServiceImpl
