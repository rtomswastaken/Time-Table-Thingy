"""Reusable CustomTkinter Report Viewer component for Agent 8 shell integration.

Allows users to inspect:
- Faculty Workload summary & warnings
- Room Utilization rates & capacity efficiency
- Scheduling Conflicts & actionable remediation
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from exchange.models import (
    ConflictReportRow,
    ExportFormat,
    RoomUtilizationRow,
    WorkloadReportRow,
)
from exchange.report_service import ReportServiceImpl


class ReportViewerController:
    """Headless controller for fetching and filtering analytical report data."""

    def __init__(self, service: ReportServiceImpl):
        self.service = service
        self.current_report_type: str = "WORKLOAD"
        self.timetable_id: str = "DEFAULT"

    def fetch_workload(self, dept_filter: Optional[str] = None) -> List[WorkloadReportRow]:
        return self.service.get_workload_report_data(self.timetable_id, department_filter=dept_filter)

    def fetch_rooms(self) -> List[RoomUtilizationRow]:
        return self.service.get_room_utilization_data(self.timetable_id)

    def fetch_conflicts(self) -> List[ConflictReportRow]:
        return self.service.get_conflict_report_data(self.timetable_id)


class ReportViewerFrame:
    """CustomTkinter panel for viewing academic reports."""

    def __init__(
        self,
        parent: Any,
        service: ReportServiceImpl,
        timetable_id: str = "DEFAULT",
    ):
        self.parent = parent
        self.controller = ReportViewerController(service)
        self.controller.timetable_id = timetable_id

        if ctk is not None and hasattr(parent, "winfo_exists"):
            self.frame = ctk.CTkFrame(parent, corner_radius=10)
            self._build_ui()
        else:
            self.frame = None

    def _build_ui(self) -> None:
        if not self.frame or ctk is None:
            return

        self.title_label = ctk.CTkLabel(
            self.frame,
            text="Academic Timetable Reports & Analytics",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.title_label.pack(pady=(15, 10), padx=20, anchor="w")

        nav_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        nav_frame.pack(fill="x", padx=20, pady=5)

        self.report_selector = ctk.CTkSegmentedButton(
            nav_frame,
            values=["Faculty Workload", "Room Utilization", "Conflicts & Violations"],
            command=self._on_tab_changed,
        )
        self.report_selector.set("Faculty Workload")
        self.report_selector.pack(side="left")

        # Text display area
        self.text_box = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Courier", size=11))
        self.text_box.pack(fill="both", expand=True, padx=20, pady=10)

        self._refresh_content()

    def _on_tab_changed(self, value: str) -> None:
        if value == "Faculty Workload":
            self.controller.current_report_type = "WORKLOAD"
        elif value == "Room Utilization":
            self.controller.current_report_type = "ROOM_UTILIZATION"
        else:
            self.controller.current_report_type = "CONFLICTS"
        self._refresh_content()

    def _refresh_content(self) -> None:
        if not self.text_box:
            return
        self.text_box.delete("1.0", "end")

        rtype = self.controller.current_report_type
        if rtype == "WORKLOAD":
            rows = self.controller.fetch_workload()
            lines = [f"{'EMP ID':<10} {'FACULTY NAME':<25} {'HOURS':<8} {'LOAD STATUS':<15} {'WARNINGS'}"]
            lines.append("-" * 80)
            for r in rows:
                status = "OVERLOADED" if r.is_overloaded else ("UNDERLOADED" if r.is_underloaded else "NORMAL")
                lines.append(f"{r.employee_id:<10} {r.teacher_name[:24]:<25} {r.assigned_contact_hours:<8.1f} {status:<15} {r.warning_message}")
            self.text_box.insert("1.0", "\n".join(lines))

        elif rtype == "ROOM_UTILIZATION":
            rows = self.controller.fetch_rooms()
            lines = [f"{'CODE':<10} {'FACILITY NAME':<25} {'TYPE':<16} {'CAPACITY':<10} {'UTIL %':<8} {'NOTES'}"]
            lines.append("-" * 85)
            for r in rows:
                lines.append(f"{r.room_code:<10} {r.room_name[:24]:<25} {r.room_type[:15]:<16} {r.capacity:<10} {r.utilization_rate:<8.1f} {r.notes}")
            self.text_box.insert("1.0", "\n".join(lines))

        else:
            rows = self.controller.fetch_conflicts()
            if not rows:
                self.text_box.insert("1.0", "No conflicts or constraint violations detected. Schedule is 100% valid.")
            else:
                lines = [f"Found {len(rows)} conflicts or soft preference warnings:\n"]
                for i, r in enumerate(rows, start=1):
                    lines.append(f"{i}. [{r.severity}] {r.violation_type}: {r.description}")
                    if r.remediation_suggestion:
                        lines.append(f"   Remediation: {r.remediation_suggestion}")
                    lines.append("")
                self.text_box.insert("1.0", "\n".join(lines))
