"""Main Application Shell for Timetable Thingy.

Integrates all 8 agent subsystems into a single cohesive desktop application:
- SQLite persistence and schema migrations (Agent 2)
- Academic Management view (Agent 3)
- Faculty preferences & workload analytics (Agent 4)
- Google OR-Tools CP-SAT scheduling solver (Agent 5)
- Interactive timetable grid & editor (Agent 6)
- CSV/Excel imports, PDF/Excel exports, and reports (Agent 7)
- Application shell, responsive sidebar navigation, and worker bus (Agent 8)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import customtkinter as ctk

from academic.academic_service import AcademicService
from academic.ui.academic_app import AcademicManagerView
from core.models import (
    ConstraintViolation,
    Institution,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SchedulingStatus,
    SessionType,
    Subject,
    Teacher,
    Timetable,
)
from database.connection import DatabaseManager, get_db_manager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    RoomRepository,
    ScheduledSessionRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from database.schema import check_integrity, initialize_database
from exchange.service import ImportExportServiceImpl
from exchange.ui.export_dialog import ExportDialogFrame
from exchange.ui.import_wizard import ImportWizardFrame
from exchange.ui.report_viewer import ReportViewerFrame
from gui.timetable.timetable_editor import TimetableEditor
from services.timetable_workspace_service import TimetableWorkspaceService
from solver.session_builder import SessionBuilder
from solver.solver import solve
from workload.repository import WorkloadRepository
from workload.service import WorkloadServiceImpl
from workload.ui.preferences_view import TeacherPreferencesView
from workload.ui.workload_config_view import WorkloadConfigView
from workload.ui.workload_overview_view import WorkloadOverviewView

logger = logging.getLogger("timetable_thingy")


class TimetableApp(ctk.CTk):
    """Unified CustomTkinter desktop application shell."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__()

        # Appearance & Window Configuration
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Timetable Thingy — Academic Timetable Generator")
        self.geometry("1280x820")
        self.minsize(1024, 700)

        # 1. Initialize Database & Migrations
        self.db_manager = db_manager or get_db_manager()
        initialize_database(self.db_manager)

        # 2. Initialize Repositories
        self.inst_repo = InstitutionRepository(self.db_manager)
        self.dept_repo = DepartmentRepository(self.db_manager)
        self.class_repo = ClassGroupRepository(self.db_manager)
        self.teacher_repo = TeacherRepository(self.db_manager)
        self.subject_repo = SubjectRepository(self.db_manager)
        self.room_repo = RoomRepository(self.db_manager)
        self.tt_repo = TimetableRepository(self.db_manager)
        self.session_repo = ScheduledSessionRepository(self.db_manager)

        # 3. Initialize Domain Services
        self.academic_service = AcademicService(self.db_manager)
        self.workload_service = WorkloadServiceImpl(
            repository=WorkloadRepository(self.db_manager.get_connection()),
            timetable_repo=self.tt_repo,
        )
        self.workspace_service = TimetableWorkspaceService(
            repository=self.tt_repo,
        )
        self.import_export_service = ImportExportServiceImpl(
            db_manager=self.db_manager,
        )

        # 4. Active State
        self.active_timetable: Optional[Timetable] = None
        self._current_nav_button: Optional[ctk.CTkButton] = None

        # 5. Build Layout
        self._build_shell()
        self._show_academic_view()

    def _build_shell(self) -> None:
        """Constructs sidebar, top status bar, and content container."""
        # Grid layout: 2 columns (sidebar, content)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        # App Brand Header
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="🗓️ Timetable Thingy",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Academic Scheduler",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Navigation Buttons
        self.btn_academic = ctk.CTkButton(
            self.sidebar_frame,
            text="🏛️  Academic Structure",
            anchor="w",
            command=self._show_academic_view,
        )
        self.btn_academic.grid(row=2, column=0, padx=12, pady=4, sticky="ew")

        self.btn_faculty = ctk.CTkButton(
            self.sidebar_frame,
            text="👥  Faculty & Workload",
            anchor="w",
            command=self._show_faculty_view,
        )
        self.btn_faculty.grid(row=3, column=0, padx=12, pady=4, sticky="ew")

        self.btn_workspace = ctk.CTkButton(
            self.sidebar_frame,
            text="📅  Timetable Grid",
            anchor="w",
            command=self._show_workspace_view,
        )
        self.btn_workspace.grid(row=4, column=0, padx=12, pady=4, sticky="ew")

        self.btn_exchange = ctk.CTkButton(
            self.sidebar_frame,
            text="🔄  Import / Export",
            anchor="w",
            command=self._show_exchange_view,
        )
        self.btn_exchange.grid(row=5, column=0, padx=12, pady=4, sticky="ew")

        # Solver Quick Action
        self.btn_generate = ctk.CTkButton(
            self.sidebar_frame,
            text="⚡  Generate Timetable",
            anchor="w",
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._run_solver_workflow,
        )
        self.btn_generate.grid(row=6, column=0, padx=12, pady=(16, 4), sticky="ew")

        # Sidebar Footer
        self.theme_label = ctk.CTkLabel(self.sidebar_frame, text="Appearance Mode:", font=ctk.CTkFont(size=10))
        self.theme_label.grid(row=9, column=0, padx=20, pady=(10, 0), sticky="w")

        self.theme_menu = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=["System", "Dark", "Light"],
            command=ctk.set_appearance_mode,
        )
        self.theme_menu.grid(row=10, column=0, padx=12, pady=(2, 20), sticky="ew")

        # --- Content Container ---
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

    def _clear_content(self) -> None:
        """Removes existing content widgets."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _set_active_nav(self, btn: ctk.CTkButton) -> None:
        buttons = [self.btn_academic, self.btn_faculty, self.btn_workspace, self.btn_exchange]
        for b in buttons:
            b.configure(fg_color=["#3a7ebf", "#1f538d"])
        btn.configure(fg_color=["#2b5b88", "#14375e"])

    def _show_academic_view(self) -> None:
        self._clear_content()
        self._set_active_nav(self.btn_academic)
        view = AcademicManagerView(self.content_frame, service=self.academic_service)
        view.pack(fill="both", expand=True)

    def _show_faculty_view(self) -> None:
        self._clear_content()
        self._set_active_nav(self.btn_faculty)

        tabview = ctk.CTkTabview(self.content_frame)
        tabview.pack(fill="both", expand=True)

        tab_prefs = tabview.add("Availability & Preferences")
        tab_rules = tabview.add("Workload Rules")
        tab_analytics = tabview.add("Workload Analytics")

        pref_view = TeacherPreferencesView(tab_prefs, service=self.workload_service)
        pref_view.pack(fill="both", expand=True)

        rule_view = WorkloadConfigView(tab_rules, service=self.workload_service)
        rule_view.pack(fill="both", expand=True)

        overview_view = WorkloadOverviewView(tab_analytics, service=self.workload_service)
        overview_view.pack(fill="both", expand=True)

    def _show_workspace_view(self) -> None:
        self._clear_content()
        self._set_active_nav(self.btn_workspace)

        # Refresh subjects in workspace
        try:
            subjects = self.subject_repo.list_all()
            if subjects:
                self.workspace_service._subjects = {s.id: s for s in subjects}
        except Exception:
            pass

        editor = TimetableEditor(self.content_frame, service=self.workspace_service)
        editor.pack(fill="both", expand=True)

    def _show_exchange_view(self) -> None:
        self._clear_content()
        self._set_active_nav(self.btn_exchange)

        tabview = ctk.CTkTabview(self.content_frame)
        tabview.pack(fill="both", expand=True)

        tab_import = tabview.add("Import Data")
        tab_export = tabview.add("Export Timetable")
        tab_reports = tabview.add("Analytics & Reports")

        import_frame = ImportWizardFrame(tab_import, service=self.import_export_service)
        export_frame = ExportDialogFrame(tab_export, service=self.import_export_service)
        report_frame = ReportViewerFrame(tab_reports, service=self.import_export_service)

    def _run_solver_workflow(self) -> None:
        """Launches the solver in a background thread and switches to the grid view."""
        self.btn_generate.configure(state="disabled", text="⏳ Solving...")

        def _worker():
            try:
                # 1. Fetch academic entities
                classes = self.class_repo.list_all()
                teachers = self.teacher_repo.list_all()
                rooms = self.room_repo.list_all()
                subjects = self.subject_repo.list_all()
                offerings = self.subject_repo.list_offerings()

                # If database has offerings, build units
                units: List[SchedulableUnit] = []
                for off in offerings:
                    subj = self.subject_repo.get_by_id(off.subject_id)
                    req_room = RoomType.COMPUTER_LAB if (subj and subj.requires_lab) else None
                    expanded = SessionBuilder.expand_default_weekly_periods(
                        assignment_id=f"asgn-{off.id}",
                        class_group_id=str(off.class_group_id),
                        subject_id=str(off.subject_id),
                        primary_teacher_id=str(off.primary_teacher_id or (teachers[0].id if teachers else "T1")),
                        weekly_periods=off.weekly_sessions_required,
                        session_duration=off.session_duration,
                        session_type=SessionType.LABORATORY if (subj and subj.requires_lab) else SessionType.THEORY,
                        required_room_type=req_room,
                    )
                    units.extend(expanded)

                # Fallback if database has no offerings yet
                if not units:
                    c1 = classes[0] if classes else ClassGroup(id="CG-1", department_id="CS", semester_id="S1", name="Batch A", student_count=30)
                    t1 = teachers[0] if teachers else Teacher(id="T-1", department_id="CS", name="Prof. Turing", employee_id="EMP1")
                    r1 = rooms[0] if rooms else Room(id="R-1", code="R101", name="Lecture 1", room_type=RoomType.LECTURE_HALL, capacity=50)
                    classes = [c1]
                    teachers = [t1]
                    rooms = [r1]
                    units = [
                        SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=c1.id, subject_id="CS101", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1),
                        SchedulableUnit(unit_id="u2", assignment_id="a1", class_group_id=c1.id, subject_id="CS101", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1),
                    ]

                bundle = SchedulingInputBundle(
                    institution_id="inst-1",
                    academic_year_id="ay-1",
                    semester_id="sem-1",
                    days=[0, 1, 2, 3, 4],
                    periods_per_day=6,
                    break_periods={3},
                    units=units,
                    teachers=teachers,
                    rooms=rooms,
                    class_groups=classes,
                )

                config = SchedulingConfig(time_limit_seconds=15.0)
                result = solve(bundle, config)

                # Update workspace on main thread
                def _on_success():
                    self.btn_generate.configure(state="normal", text="⚡  Generate Timetable")
                    self.workspace_service.bundle = bundle
                    if result.status in (SchedulingStatus.OPTIMAL, SchedulingStatus.FEASIBLE):
                        tt = self.workspace_service.create_draft_from_generation(result)
                        self.active_timetable = tt
                    self._show_workspace_view()

                self.after(0, _on_success)

            except Exception as exc:
                logger.error("Solver execution error: %s", exc)
                def _on_error():
                    self.btn_generate.configure(state="normal", text="⚡  Generate Timetable")
                self.after(0, _on_error)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


def run_app() -> None:
    """Launches the desktop application if graphical display is available."""
    try:
        app = TimetableApp()
        app.mainloop()
    except Exception as exc:
        print(f"Graphical interface could not be launched: {exc}")
        print("Run automated tests using: pytest")


if __name__ == "__main__":
    run_app()
