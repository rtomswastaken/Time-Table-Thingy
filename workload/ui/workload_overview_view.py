"""Workload Overview CustomTkinter View.

Displays faculty workload summaries, period loads vs capacities, teaching days,
and intuitive violation warning badges. Supports filtering by department, period, and teacher.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from core.models import Department, ScheduledSession, Teacher
from workload.models import TeacherWorkloadSummary
from workload.service import WorkloadServiceImpl

logger = logging.getLogger(__name__)


class WorkloadOverviewView:
    """CustomTkinter frame providing an overview table of teacher workloads and warning alerts."""

    def __init__(
        self,
        parent: any,
        service: WorkloadServiceImpl,
        teachers: Optional[List[Teacher]] = None,
        departments: Optional[List[Department]] = None,
        timetable_id: str = "current_draft",
    ) -> None:
        self.parent = parent
        self.service = service
        self.teachers = teachers or list(service._teachers.values())
        self.departments = departments or []
        self.timetable_id = timetable_id

        self.dept_filter: Optional[str] = None
        self.search_filter: str = ""

        self.frame: Optional[any] = None
        if ctk is not None and parent is not None:
            self._build_ui()

    def _build_ui(self) -> None:
        self.frame = ctk.CTkFrame(self.parent)
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Header with Filters
        header_frame = ctk.CTkFrame(self.frame)
        header_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            header_frame,
            text="Faculty Workload Overview & Capacity",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=10, pady=5)

        # Department Filter
        dept_names = ["All Departments"] + [d.name for d in self.departments]
        self.dept_dropdown = ctk.CTkOptionMenu(
            header_frame,
            values=dept_names,
            command=self._on_dept_changed,
        )
        self.dept_dropdown.pack(side="right", padx=10, pady=5)

        # Search box
        self.search_entry = ctk.CTkEntry(
            header_frame, placeholder_text="Filter by teacher name..."
        )
        self.search_entry.pack(side="right", padx=10, pady=5)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)

        # Table Header
        table_header = ctk.CTkFrame(self.frame)
        table_header.pack(fill="x", padx=10, pady=(5, 0))

        cols = [
            ("Teacher", 160),
            ("Assigned", 70),
            ("Contact Hrs", 90),
            ("Req / Min", 80),
            ("Max Limit", 80),
            ("Capacity Left", 100),
            ("Days Active", 85),
            ("Status & Warnings", 220),
        ]
        for name, width in cols:
            ctk.CTkLabel(
                table_header,
                text=name,
                font=ctk.CTkFont(weight="bold"),
                width=width,
                anchor="w",
            ).pack(side="left", padx=5, pady=4)

        # Scrollable Table Content
        self.scroll_frame = ctk.CTkScrollableFrame(self.frame)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.refresh_table()

    def _on_dept_changed(self, dept_name: str) -> None:
        if dept_name == "All Departments":
            self.dept_filter = None
        else:
            for d in self.departments:
                if d.name == dept_name:
                    self.dept_filter = d.id
                    break
        self.refresh_table()

    def _on_search_changed(self, event: any) -> None:
        self.search_filter = self.search_entry.get().strip().lower()
        self.refresh_table()

    def refresh_table(self) -> None:
        """Renders table rows with calculated workload summaries."""
        if not hasattr(self, "scroll_frame"):
            return

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        summaries = self.service.calculate_all_workloads(self.timetable_id)

        # Build quick teacher lookup
        t_dept_map = {t.id: t.department_id for t in self.teachers}

        for summary in summaries:
            # Apply department filter
            if self.dept_filter and t_dept_map.get(summary.teacher_id) != self.dept_filter:
                continue

            # Apply search filter
            if self.search_filter and self.search_filter not in summary.teacher_name.lower():
                continue

            self._create_summary_row(summary)

    def _create_summary_row(self, s: any) -> None:
        row_frame = ctk.CTkFrame(self.scroll_frame)
        row_frame.pack(fill="x", pady=2)

        # Teacher Name
        ctk.CTkLabel(row_frame, text=s.teacher_name, width=160, anchor="w").pack(
            side="left", padx=5, pady=3
        )
        # Assigned Periods
        ctk.CTkLabel(row_frame, text=f"{s.assigned_periods_per_week} p", width=70, anchor="w").pack(
            side="left", padx=5
        )
        # Contact Hours
        ctk.CTkLabel(
            row_frame, text=f"{s.assigned_contact_hours_per_week:.1f} hrs", width=90, anchor="w"
        ).pack(side="left", padx=5)
        # Required / Min
        ctk.CTkLabel(row_frame, text=f"{s.min_periods_required} p", width=80, anchor="w").pack(
            side="left", padx=5
        )
        # Max Allowed
        ctk.CTkLabel(row_frame, text=f"{s.max_periods_allowed} p", width=80, anchor="w").pack(
            side="left", padx=5
        )
        # Remaining Capacity
        cap_val = getattr(s, "remaining_capacity_periods", max(0, s.max_periods_allowed - s.assigned_periods_per_week))
        ctk.CTkLabel(row_frame, text=f"{cap_val} periods", width=100, anchor="w").pack(
            side="left", padx=5
        )
        # Days Active
        days_cnt = getattr(s, "teaching_days_count", sum(1 for p in s.daily_periods.values() if p > 0))
        ctk.CTkLabel(row_frame, text=f"{days_cnt} days", width=85, anchor="w").pack(
            side="left", padx=5
        )

        # Warnings / Status Badge
        violations = getattr(s, "violations", [])
        if s.is_overloaded:
            badge_text = "OVERLOADED"
            badge_color = "#C62828"  # Red
        elif s.is_underloaded:
            badge_text = "UNDERLOADED"
            badge_color = "#E65100"  # Orange
        elif violations:
            badge_text = f"{len(violations)} WARNING(S)"
            badge_color = "#F57F17"  # Yellow/Amber
        else:
            badge_text = "OPTIMAL"
            badge_color = "#2E7D32"  # Green

        badge = ctk.CTkLabel(
            row_frame,
            text=badge_text,
            width=200,
            anchor="center",
            fg_color=badge_color,
            corner_radius=6,
            text_color="white",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        badge.pack(side="left", padx=5, pady=3)
