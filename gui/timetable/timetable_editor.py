"""Timetable Workspace & Interactive Editor.

Main presentation container providing:
- Multi-perspective views (Class, Teacher, Room, Department, Semester, Subject)
- Manual session editing (Move, Swap, Teacher Reassign, Room Reassign)
- Session locking and unlocking
- Real-time constraint validation and conflict explanations
- Undo / Redo history
- Draft, Save, Publish, Version cloning and Diff workflows
- Workload and quality summaries
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Tuple
import customtkinter as ctk

from core.exceptions import ValidationError
from core.models import ConstraintViolation, ScheduledSession, Timetable
from gui.timetable.timetable_grid import TimetableGrid
from gui.timetable.timetable_views import (
    GridCellViewModel,
    SessionCardViewModel,
    TimetableGridViewModel,
    TimetablePerspective,
    TimetableViewModelGenerator,
)
from services.timetable_workspace_service import (
    TimetableDiff,
    TimetableWorkspaceService,
    WorkspaceWorkloadSummary,
)


class TimetableEditor(ctk.CTkFrame):
    """The central Timetable Workspace and Interactive Editor widget."""

    def __init__(
        self,
        master: Any,
        service: TimetableWorkspaceService,
        on_status_change: Optional[Callable[[str], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.service = service
        self.view_generator = TimetableViewModelGenerator(service)
        self.on_status_change = on_status_change

        # View state
        self.current_perspective: TimetablePerspective = TimetablePerspective.CLASS
        self.current_target_id: str = ""
        self.selected_session: Optional[SessionCardViewModel] = None
        self.selected_empty_slot: Optional[Tuple[int, int]] = None

        # Build UI layout
        self._build_toolbar()
        self._build_main_content()
        self._build_status_bar()

        # Keyboard shortcuts
        self._bind_shortcuts()

        # Initial data population
        self.refresh_entity_selectors()
        self.refresh_view()

    # -------------------------------------------------------------------------
    # Layout Builders
    # -------------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        """Top navigation bar with perspectives, target selector, and lifecycle actions."""
        self.toolbar_frame = ctk.CTkFrame(self, corner_radius=8, height=48)
        self.toolbar_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 1. Perspective segmented button
        self.perspective_seg = ctk.CTkSegmentedButton(
            self.toolbar_frame,
            values=["Class", "Teacher", "Room", "Department", "Semester", "Subject"],
            command=self._handle_perspective_change,
        )
        self.perspective_seg.set("Class")
        self.perspective_seg.pack(side="left", padx=10, pady=8)

        # 2. Target entity dropdown (e.g. Choose Class / Teacher)
        self.target_dropdown = ctk.CTkOptionMenu(
            self.toolbar_frame,
            values=["Select Entity..."],
            command=self._handle_target_change,
            width=200,
        )
        self.target_dropdown.pack(side="left", padx=5, pady=8)

        # 3. Action buttons (Undo, Redo, Save, Publish, Compare, Regenerate)
        self.btn_undo = ctk.CTkButton(
            self.toolbar_frame,
            text="↶ Undo",
            width=70,
            command=self.handle_undo,
            state="disabled",
        )
        self.btn_undo.pack(side="left", padx=3, pady=8)

        self.btn_redo = ctk.CTkButton(
            self.toolbar_frame,
            text="↷ Redo",
            width=70,
            command=self.handle_redo,
            state="disabled",
        )
        self.btn_redo.pack(side="left", padx=3, pady=8)

        # Right side actions
        self.btn_save = ctk.CTkButton(
            self.toolbar_frame,
            text="💾 Save Draft",
            fg_color=("#16A34A", "#15803D"),
            hover_color=("#15803D", "#166534"),
            width=90,
            command=self.handle_save_draft,
        )
        self.btn_save.pack(side="right", padx=(4, 10), pady=8)

        self.btn_discard = ctk.CTkButton(
            self.toolbar_frame,
            text="✕ Discard",
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray40"),
            text_color=("black", "white"),
            width=80,
            command=self.handle_discard_changes,
        )
        self.btn_discard.pack(side="right", padx=4, pady=8)

        self.btn_publish = ctk.CTkButton(
            self.toolbar_frame,
            text="🚀 Publish",
            fg_color=("#4F46E5", "#4338CA"),
            hover_color=("#4338CA", "#3730A3"),
            width=80,
            command=self.handle_publish,
        )
        self.btn_publish.pack(side="right", padx=4, pady=8)

        self.btn_diff = ctk.CTkButton(
            self.toolbar_frame,
            text="🔍 Compare",
            width=80,
            command=self.handle_compare_versions,
        )
        self.btn_diff.pack(side="right", padx=4, pady=8)

        self.btn_regen = ctk.CTkButton(
            self.toolbar_frame,
            text="⚡ Partial Regen",
            width=100,
            command=self.handle_partial_regenerate,
        )
        self.btn_regen.pack(side="right", padx=4, pady=8)

    def _build_main_content(self) -> None:
        """Central workspace area containing the TimetableGrid and right Inspector panel."""
        self.content_paned = ctk.CTkFrame(self, fg_color="transparent")
        self.content_paned.pack(fill="both", expand=True, padx=10, pady=5)

        # Left / Center: Weekly Grid
        self.grid_container = ctk.CTkFrame(self.content_paned, corner_radius=8)
        self.grid_container.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.grid_widget = TimetableGrid(
            self.grid_container,
            on_session_selected=self._handle_session_selected,
            on_empty_slot_clicked=self._handle_empty_slot_clicked,
            on_session_double_click=self._handle_session_double_click,
        )
        self.grid_widget.pack(fill="both", expand=True, padx=5, pady=5)

        # Right: Inspector & Summary Panel
        self.inspector_panel = ctk.CTkFrame(self.content_paned, width=320, corner_radius=8)
        self.inspector_panel.pack(side="right", fill="y", padx=(5, 0))
        self.inspector_panel.pack_propagate(False)

        self._build_inspector_ui()

    def _build_inspector_ui(self) -> None:
        """Constructs the right inspector containing details, conflict list, and analytics."""
        title_lbl = ctk.CTkLabel(
            self.inspector_panel,
            text="Session Inspector & Actions",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title_lbl.pack(fill="x", padx=10, pady=(10, 5))

        # Selected Session Card Details
        self.details_box = ctk.CTkTextbox(
            self.inspector_panel,
            height=130,
            font=ctk.CTkFont(size=11),
            wrap="word",
        )
        self.details_box.pack(fill="x", padx=10, pady=5)
        self.details_box.insert("1.0", "Click a session card in the grid to inspect details and edit.")
        self.details_box.configure(state="disabled")

        # Session Action Buttons
        self.actions_frame = ctk.CTkFrame(self.inspector_panel, fg_color="transparent")
        self.actions_frame.pack(fill="x", padx=10, pady=5)

        self.btn_move = ctk.CTkButton(
            self.actions_frame,
            text="Move to Slot...",
            height=28,
            command=self.open_move_dialog,
            state="disabled",
        )
        self.btn_move.pack(fill="x", pady=2)

        self.btn_swap = ctk.CTkButton(
            self.actions_frame,
            text="Swap Sessions...",
            height=28,
            command=self.open_swap_dialog,
            state="disabled",
        )
        self.btn_swap.pack(fill="x", pady=2)

        self.btn_reassign_t = ctk.CTkButton(
            self.actions_frame,
            text="Reassign Teacher...",
            height=28,
            command=self.open_reassign_teacher_dialog,
            state="disabled",
        )
        self.btn_reassign_t.pack(fill="x", pady=2)

        self.btn_reassign_r = ctk.CTkButton(
            self.actions_frame,
            text="Reassign Room...",
            height=28,
            command=self.open_reassign_room_dialog,
            state="disabled",
        )
        self.btn_reassign_r.pack(fill="x", pady=2)

        self.btn_lock = ctk.CTkButton(
            self.actions_frame,
            text="🔒 Lock Session",
            height=28,
            command=self.toggle_session_lock,
            state="disabled",
        )
        self.btn_lock.pack(fill="x", pady=2)

        # Real-Time Validation & Conflicts Section
        conf_hdr = ctk.CTkLabel(
            self.inspector_panel,
            text="Real-Time Validation",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        conf_hdr.pack(fill="x", padx=10, pady=(12, 2))

        self.conflicts_box = ctk.CTkTextbox(
            self.inspector_panel,
            height=130,
            font=ctk.CTkFont(size=10),
            wrap="word",
        )
        self.conflicts_box.pack(fill="x", padx=10, pady=2)
        self.conflicts_box.insert("1.0", "No conflicts detected. Schedule is valid.")
        self.conflicts_box.configure(state="disabled")

        # Workload & Quality Summary Section
        summary_hdr = ctk.CTkLabel(
            self.inspector_panel,
            text="Schedule Quality Metrics",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        summary_hdr.pack(fill="x", padx=10, pady=(10, 2))

        self.summary_box = ctk.CTkTextbox(
            self.inspector_panel,
            height=110,
            font=ctk.CTkFont(size=10),
            wrap="word",
        )
        self.summary_box.pack(fill="x", padx=10, pady=(2, 10))
        self.summary_box.insert("1.0", "Metrics summary will appear here.")
        self.summary_box.configure(state="disabled")

    def _build_status_bar(self) -> None:
        """Bottom status bar indicating version, dirty state, and active schedule info."""
        self.status_frame = ctk.CTkFrame(self, height=30, corner_radius=6)
        self.status_frame.pack(fill="x", padx=10, pady=(5, 10))

        self.status_badge = ctk.CTkLabel(
            self.status_frame,
            text="[Draft v1 • Saved]",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#16A34A", "#4ADE80"),
        )
        self.status_badge.pack(side="left", padx=10)

        self.status_message = ctk.CTkLabel(
            self.status_frame,
            text="Ready",
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.status_message.pack(side="left", fill="x", expand=True, padx=5)

    def _bind_shortcuts(self) -> None:
        """Binds Ctrl+Z / Cmd+Z for Undo and Ctrl+Y / Cmd+Y for Redo."""
        try:
            root = self.winfo_toplevel()
            root.bind("<Control-z>", lambda e: self.handle_undo(), add="+")
            root.bind("<Command-z>", lambda e: self.handle_undo(), add="+")
            root.bind("<Control-y>", lambda e: self.handle_redo(), add="+")
            root.bind("<Command-y>", lambda e: self.handle_redo(), add="+")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Navigation & Entity Selectors
    # -------------------------------------------------------------------------

    def refresh_entity_selectors(self) -> None:
        """Populates the target entity dropdown based on the active perspective."""
        bundle = self.service.bundle
        values: List[str] = []

        if self.current_perspective == TimetablePerspective.CLASS:
            if bundle and bundle.class_groups:
                values = [f"{c.name} ({c.id})" for c in bundle.class_groups]
            else:
                values = ["No Classes Available"]

        elif self.current_perspective == TimetablePerspective.TEACHER:
            if bundle and bundle.teachers:
                values = [f"{t.name} ({t.id})" for t in bundle.teachers]
            else:
                values = ["No Teachers Available"]

        elif self.current_perspective == TimetablePerspective.ROOM:
            if bundle and bundle.rooms:
                values = [f"{r.name} [{r.code}] ({r.id})" for r in bundle.rooms]
            else:
                values = ["No Rooms Available"]

        elif self.current_perspective == TimetablePerspective.DEPARTMENT:
            depts = set()
            if bundle:
                for c in bundle.class_groups:
                    depts.add(c.department_id)
            values = sorted(list(depts)) if depts else ["No Departments Available"]

        elif self.current_perspective == TimetablePerspective.SEMESTER:
            sems = set()
            if bundle:
                for c in bundle.class_groups:
                    sems.add(c.semester_id)
            values = sorted(list(sems)) if sems else ["No Semesters Available"]

        elif self.current_perspective == TimetablePerspective.SUBJECT:
            subjs = set()
            if bundle:
                for u in bundle.units:
                    subjs.add(u.subject_id)
            values = sorted(list(subjs)) if subjs else ["No Subjects Available"]

        self.target_dropdown.configure(values=values)
        if values and not values[0].startswith("No "):
            # Extract raw ID from parenthesis or select first
            self.target_dropdown.set(values[0])
            self.current_target_id = self._extract_id_from_dropdown(values[0])
        else:
            self.target_dropdown.set(values[0] if values else "Empty")
            self.current_target_id = ""

    def _extract_id_from_dropdown(self, text: str) -> str:
        """Extracts the ID enclosed in parentheses from dropdown string."""
        if "(" in text and text.endswith(")"):
            return text.split("(")[-1].rstrip(")")
        return text

    def _handle_perspective_change(self, value: str) -> None:
        perspective_map = {
            "Class": TimetablePerspective.CLASS,
            "Teacher": TimetablePerspective.TEACHER,
            "Room": TimetablePerspective.ROOM,
            "Department": TimetablePerspective.DEPARTMENT,
            "Semester": TimetablePerspective.SEMESTER,
            "Subject": TimetablePerspective.SUBJECT,
        }
        self.current_perspective = perspective_map.get(value, TimetablePerspective.CLASS)
        self.selected_session = None
        self.selected_empty_slot = None
        self.refresh_entity_selectors()
        self.refresh_view()

    def _handle_target_change(self, value: str) -> None:
        self.current_target_id = self._extract_id_from_dropdown(value)
        self.selected_session = None
        self.selected_empty_slot = None
        self.refresh_view()

    # -------------------------------------------------------------------------
    # View Rendering & State Synchronization
    # -------------------------------------------------------------------------

    def refresh_view(self) -> None:
        """Generates the view model for the active perspective and updates all widgets."""
        if not self.current_target_id:
            # Empty state
            return

        model = self.view_generator.generate_view(self.current_perspective, self.current_target_id)
        selected_id = self.selected_session.session_id if self.selected_session else None

        # Render grid
        self.grid_widget.render_grid(
            model,
            selected_session_id=selected_id,
            selected_empty_slot=self.selected_empty_slot,
        )

        # Update Inspector details
        self._update_inspector_details()

        # Update Real-Time Validation Box
        self._update_validation_panel()

        # Update Quality Metrics Summary Box
        self._update_summary_panel(model)

        # Update Toolbar Buttons (Undo/Redo status)
        self.btn_undo.configure(state="normal" if self.service.can_undo else "disabled")
        self.btn_redo.configure(state="normal" if self.service.can_redo else "disabled")

        # Update Status Bar
        self._update_status_bar()

    def _update_inspector_details(self) -> None:
        self.details_box.configure(state="normal")
        self.details_box.delete("1.0", "end")

        if self.selected_session:
            s = self.selected_session
            lock_status = f"🔒 LOCKED ({s.lock_reason})" if s.is_locked else "Unlocked"
            conf_status = "⚠️ HAS CONFLICTS" if s.has_conflict else "✓ Valid"

            text = (
                f"Subject: {s.subject_code} - {s.subject_name}\n"
                f"Class: {s.class_name}\n"
                f"Teacher: {s.teacher_name}\n"
                f"Room: {s.room_name} ({s.room_code})\n"
                f"Type: {s.session_type} ({s.duration_periods} Periods)\n"
                f"Status: {lock_status} • {conf_status}"
            )
            self.details_box.insert("1.0", text)

            # Enable session actions
            self.btn_move.configure(state="normal")
            self.btn_swap.configure(state="normal")
            self.btn_reassign_t.configure(state="normal")
            self.btn_reassign_r.configure(state="normal")
            self.btn_lock.configure(
                state="normal",
                text="🔓 Unlock Session" if s.is_locked else "🔒 Lock Session",
            )
        else:
            self.details_box.insert("1.0", "Select a session card to inspect details and perform edits.")
            self.btn_move.configure(state="disabled")
            self.btn_swap.configure(state="disabled")
            self.btn_reassign_t.configure(state="disabled")
            self.btn_reassign_r.configure(state="disabled")
            self.btn_lock.configure(state="disabled", text="🔒 Lock Session")

        self.details_box.configure(state="disabled")

    def _update_validation_panel(self) -> None:
        violations = self.service.validate_current_schedule()
        self.conflicts_box.configure(state="normal")
        self.conflicts_box.delete("1.0", "end")

        hard_count = sum(1 for v in violations if v.is_hard)
        soft_count = len(violations) - hard_count

        if not violations:
            self.conflicts_box.insert("1.0", "✓ 0 Conflicts. All hard and soft constraints satisfied.")
        else:
            lines = [f"⚠️ {hard_count} Hard Errors, {soft_count} Soft Warnings:\n"]
            for v in violations:
                prefix = "❌ [HARD]" if v.is_hard else "⚠️ [WARN]"
                lines.append(f"{prefix} {v.message}")
            self.conflicts_box.insert("1.0", "\n".join(lines))

        self.conflicts_box.configure(state="disabled")

    def _update_summary_panel(self, model: TimetableGridViewModel) -> None:
        metrics = self.service.calculate_quality_metrics()
        self.summary_box.configure(state="normal")
        self.summary_box.delete("1.0", "end")

        text = (
            f"Scheduled Sessions: {model.total_sessions_count}\n"
            f"Empty Time Slots: {model.empty_slots_count}\n"
            f"Room Utilization: {metrics.room_utilization_percentage}%\n"
            f"Teacher Idle Gaps: {metrics.teacher_idle_gaps}\n"
            f"Soft Penalty Score: {metrics.soft_penalty_score}"
        )
        self.summary_box.insert("1.0", text)
        self.summary_box.configure(state="disabled")

    def _update_status_bar(self) -> None:
        tt = self.service.active_timetable
        if not tt:
            self.status_badge.configure(text="[No Timetable Loaded]", text_color="gray50")
            self.status_message.configure(text="Please generate or load a timetable.")
            return

        if tt.is_published:
            badge_txt = f"[Published v{tt.version} • Immutable]"
            color = ("#4F46E5", "#818CF8")
        elif self.service.is_dirty:
            badge_txt = f"[Draft v{tt.version} • Unsaved Changes]"
            color = ("#D97706", "#FBBF24")
        else:
            badge_txt = f"[Draft v{tt.version} • Saved]"
            color = ("#16A34A", "#4ADE80")

        self.status_badge.configure(text=badge_txt, text_color=color)

        if self.service.is_dirty:
            msg = "Working draft has unsaved changes. Click 'Save Draft' or 'Discard'."
        else:
            msg = f"Active schedule '{tt.name}' loaded."
        self.status_message.configure(text=msg)

    # -------------------------------------------------------------------------
    # User Interaction Handlers (Click, Move, Swap)
    # -------------------------------------------------------------------------

    def _handle_session_selected(self, session_vm: SessionCardViewModel) -> None:
        """Called when user clicks a session card in the grid."""
        # If user previously had a session selected and clicked another session, offer Swap
        if self.selected_session and self.selected_session.session_id != session_vm.session_id:
            # Quick swap confirmation
            self._confirm_and_swap(self.selected_session.session_id, session_vm.session_id)
            return

        # Regular selection
        self.selected_session = session_vm
        self.selected_empty_slot = None
        self.refresh_view()

    def _handle_empty_slot_clicked(self, day: int, period: int) -> None:
        """Called when user clicks an empty slot in the grid."""
        # If a session is currently selected, offer Move to this slot
        if self.selected_session:
            self._confirm_and_move(self.selected_session.session_id, day, period)
            return

        # Otherwise, mark target slot
        self.selected_empty_slot = (day, period)
        self.selected_session = None
        self.refresh_view()

    def _handle_session_double_click(self, session_vm: SessionCardViewModel) -> None:
        """Double click opens full details or move dialog."""
        self.selected_session = session_vm
        self.open_move_dialog()

    def _confirm_and_move(self, session_id: str, day: int, period: int) -> None:
        """Attempts to move the selected session to the clicked slot with real-time validation."""
        sess = self.service._find_session(session_id)
        if not sess:
            return

        room_id = sess.room_id
        success, violations = self.service.move_session(
            timetable_id=sess.timetable_id,
            session_id=session_id,
            day=day,
            start_period=period,
            room_id=room_id,
            force=False,
        )

        if success:
            self.selected_session = None
            self.selected_empty_slot = None
            self.refresh_view()
            self._show_notification("✓ Session moved successfully.")
        else:
            hard = [v for v in violations if v.is_hard]
            msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
            self._show_conflict_modal("Cannot Move Session", msg)

    def _confirm_and_swap(self, session_a_id: str, session_b_id: str) -> None:
        """Attempts to swap two sessions with real-time validation."""
        sess_a = self.service._find_session(session_a_id)
        if not sess_a:
            return

        success, violations = self.service.swap_sessions(
            timetable_id=sess_a.timetable_id,
            session_a_id=session_a_id,
            session_b_id=session_b_id,
            force=False,
        )

        if success:
            self.selected_session = None
            self.selected_empty_slot = None
            self.refresh_view()
            self._show_notification("✓ Sessions swapped successfully.")
        else:
            hard = [v for v in violations if v.is_hard]
            msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
            self._show_conflict_modal("Cannot Swap Sessions", msg)

    # -------------------------------------------------------------------------
    # Dialogs: Move, Swap, Reassign Teacher, Reassign Room, Version Diff
    # -------------------------------------------------------------------------

    def open_move_dialog(self) -> None:
        if not self.selected_session:
            return

        sess = self.service._find_session(self.selected_session.session_id)
        if not sess or not self.service.bundle:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Move Session")
        dialog.geometry("380x320")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Move {self.selected_session.subject_code} ({self.selected_session.duration_periods} Periods)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 10))

        # Day selector
        ctk.CTkLabel(dialog, text="Target Day:").pack(anchor="w", padx=20)
        day_names = [TimetableViewModelGenerator.DAY_NAMES_MAP.get(d, f"Day {d}") for d in self.service.bundle.days]
        day_menu = ctk.CTkOptionMenu(dialog, values=day_names)
        day_menu.pack(fill="x", padx=20, pady=(0, 10))

        # Period selector
        ctk.CTkLabel(dialog, text="Target Start Period:").pack(anchor="w", padx=20)
        periods_str = [f"Period {p + 1}" for p in range(self.service.bundle.periods_per_day)]
        period_menu = ctk.CTkOptionMenu(dialog, values=periods_str)
        period_menu.pack(fill="x", padx=20, pady=(0, 10))

        # Room selector
        ctk.CTkLabel(dialog, text="Target Room:").pack(anchor="w", padx=20)
        room_names = [f"{r.name} [{r.code}]" for r in self.service.bundle.rooms]
        room_menu = ctk.CTkOptionMenu(dialog, values=room_names)
        room_menu.pack(fill="x", padx=20, pady=(0, 15))

        def execute_move() -> None:
            chosen_day_idx = day_names.index(day_menu.get())
            chosen_day = sorted(self.service.bundle.days)[chosen_day_idx]
            chosen_period = int(period_menu.get().replace("Period ", "")) - 1
            chosen_room_idx = room_names.index(room_menu.get())
            chosen_room_id = self.service.bundle.rooms[chosen_room_idx].id

            success, violations = self.service.move_session(
                timetable_id=sess.timetable_id,
                session_id=sess.id,
                day=chosen_day,
                start_period=chosen_period,
                room_id=chosen_room_id,
            )
            dialog.destroy()
            if success:
                self.selected_session = None
                self.refresh_view()
                self._show_notification("✓ Session moved successfully.")
            else:
                hard = [v for v in violations if v.is_hard]
                msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
                self._show_conflict_modal("Cannot Move Session", msg)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Confirm Move", command=execute_move).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray50", command=dialog.destroy).pack(side="right")

    def open_swap_dialog(self) -> None:
        if not self.selected_session:
            return

        sess = self.service._find_session(self.selected_session.session_id)
        if not sess:
            return

        # List other sessions
        other_sessions = [s for s in self.service.active_sessions if s.id != sess.id]
        if not other_sessions:
            self._show_notification("No other sessions available to swap.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Swap Sessions")
        dialog.geometry("420x260")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Swap {self.selected_session.subject_code} with another session",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 10))

        options = [
            f"{self.service.get_subject_code(s.class_subject_assignment_id)} - "
            f"{self.service.get_class_name(s.class_group_id)} (Day {s.day_of_week}, P{s.start_period + 1})"
            for s in other_sessions
        ]
        swap_menu = ctk.CTkOptionMenu(dialog, values=options, width=360)
        swap_menu.pack(padx=20, pady=(10, 20))

        def execute_swap() -> None:
            chosen_idx = options.index(swap_menu.get())
            target_sess = other_sessions[chosen_idx]

            success, violations = self.service.swap_sessions(
                timetable_id=sess.timetable_id,
                session_a_id=sess.id,
                session_b_id=target_sess.id,
            )
            dialog.destroy()
            if success:
                self.selected_session = None
                self.refresh_view()
                self._show_notification("✓ Sessions swapped successfully.")
            else:
                hard = [v for v in violations if v.is_hard]
                msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
                self._show_conflict_modal("Cannot Swap Sessions", msg)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Confirm Swap", command=execute_swap).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray50", command=dialog.destroy).pack(side="right")

    def open_reassign_teacher_dialog(self) -> None:
        if not self.selected_session or not self.service.bundle:
            return

        sess = self.service._find_session(self.selected_session.session_id)
        if not sess:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Reassign Teacher")
        dialog.geometry("380x240")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Reassign Teacher for {self.selected_session.subject_code}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 10))

        teachers = self.service.bundle.teachers
        options = [f"{t.name} ({t.id})" for t in teachers]
        t_menu = ctk.CTkOptionMenu(dialog, values=options, width=320)
        t_menu.pack(padx=20, pady=(10, 20))

        def execute_reassign() -> None:
            chosen_idx = options.index(t_menu.get())
            new_teacher_id = teachers[chosen_idx].id

            success, violations = self.service.reassign_teacher(sess.id, new_teacher_id)
            dialog.destroy()
            if success:
                self.refresh_view()
                self._show_notification("✓ Teacher reassigned successfully.")
            else:
                hard = [v for v in violations if v.is_hard]
                msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
                self._show_conflict_modal("Cannot Reassign Teacher", msg)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Reassign", command=execute_reassign).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray50", command=dialog.destroy).pack(side="right")

    def open_reassign_room_dialog(self) -> None:
        if not self.selected_session or not self.service.bundle:
            return

        sess = self.service._find_session(self.selected_session.session_id)
        if not sess:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Reassign Room")
        dialog.geometry("380x240")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=f"Reassign Room for {self.selected_session.subject_code}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 10))

        rooms = self.service.bundle.rooms
        options = [f"{r.name} [{r.code}] ({r.id})" for r in rooms]
        r_menu = ctk.CTkOptionMenu(dialog, values=options, width=320)
        r_menu.pack(padx=20, pady=(10, 20))

        def execute_reassign() -> None:
            chosen_idx = options.index(r_menu.get())
            new_room_id = rooms[chosen_idx].id

            success, violations = self.service.reassign_room(sess.id, new_room_id)
            dialog.destroy()
            if success:
                self.refresh_view()
                self._show_notification("✓ Room reassigned successfully.")
            else:
                hard = [v for v in violations if v.is_hard]
                msg = "\n".join(v.message for v in hard[:3]) if hard else "Constraint violation."
                self._show_conflict_modal("Cannot Reassign Room", msg)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_row, text="Reassign", command=execute_reassign).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray50", command=dialog.destroy).pack(side="right")

    def toggle_session_lock(self) -> None:
        """Locks or unlocks the currently selected session."""
        if not self.selected_session:
            return

        sess = self.service._find_session(self.selected_session.session_id)
        if not sess:
            return

        if sess.is_locked:
            self.service.unlock_session(sess.timetable_id, sess.id)
            self._show_notification("✓ Session unlocked.")
        else:
            self.service.lock_session(sess.timetable_id, sess.id, lock_reason="Pinned by user")
            self._show_notification("✓ Session locked.")

        self.refresh_view()

    # -------------------------------------------------------------------------
    # Lifecycle & Action Handlers (Undo, Redo, Save, Discard, Publish)
    # -------------------------------------------------------------------------

    def handle_undo(self) -> None:
        if self.service.undo():
            self.selected_session = None
            self.refresh_view()
            self._show_notification("↶ Edit undone.")

    def handle_redo(self) -> None:
        if self.service.redo():
            self.selected_session = None
            self.refresh_view()
            self._show_notification("↷ Edit redone.")

    def handle_save_draft(self) -> None:
        try:
            self.service.save_draft()
            self.refresh_view()
            self._show_notification("💾 Draft saved successfully.")
        except Exception as e:
            self._show_conflict_modal("Save Error", str(e))

    def handle_discard_changes(self) -> None:
        if not self.service.is_dirty:
            self._show_notification("No unsaved changes to discard.")
            return

        self.service.discard_changes()
        self.selected_session = None
        self.selected_empty_slot = None
        self.refresh_view()
        self._show_notification("✕ Unsaved changes discarded.")

    def handle_publish(self) -> None:
        try:
            self.service.publish_timetable()
            self.refresh_view()
            self._show_notification("🚀 Timetable successfully published!")
        except ValidationError as ve:
            self._show_conflict_modal("Publish Blocked", str(ve))
        except Exception as e:
            self._show_conflict_modal("Publish Error", str(e))

    def handle_compare_versions(self) -> None:
        """Opens version comparison modal."""
        timetables = self.service.repository.list_timetables()
        if len(timetables) < 2:
            self._show_notification("At least 2 timetable versions required to compare.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Compare Timetable Versions")
        dialog.geometry("600x480")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Timetable Version Comparison (Diff)",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=20, pady=(15, 5))

        # Select versions
        ctrl_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=20, pady=5)

        names = [f"{t.name} (v{t.version}) [{t.id[:6]}]" for t in timetables]
        v_a_menu = ctk.CTkOptionMenu(ctrl_frame, values=names)
        v_a_menu.pack(side="left", padx=5)
        v_a_menu.set(names[0])

        v_b_menu = ctk.CTkOptionMenu(ctrl_frame, values=names)
        v_b_menu.pack(side="left", padx=5)
        v_b_menu.set(names[1] if len(names) > 1 else names[0])

        diff_box = ctk.CTkTextbox(dialog, height=320, font=ctk.CTkFont(size=11), wrap="word")
        diff_box.pack(fill="both", expand=True, padx=20, pady=10)

        def run_diff() -> None:
            idx_a = names.index(v_a_menu.get())
            idx_b = names.index(v_b_menu.get())
            diff = self.service.compare_versions(timetables[idx_a].id, timetables[idx_b].id)

            diff_box.configure(state="normal")
            diff_box.delete("1.0", "end")

            lines = [
                f"Diff between '{diff.version_a_name}' and '{diff.version_b_name}':",
                f"Total Differences: {diff.total_differences}\n",
                f"• Moved Sessions ({len(diff.moved_sessions)}):",
            ]
            for m in diff.moved_sessions:
                lines.append(
                    f"   - {m.subject_code} ({m.class_name}): Day {m.old_slot[0]} P{m.old_slot[1] + 1} "
                    f"-> Day {m.new_slot[0]} P{m.new_slot[1] + 1}"
                )

            lines.append(f"\n• Reassigned Teachers ({len(diff.reassigned_teachers)}):")
            for t in diff.reassigned_teachers:
                lines.append(f"   - {t.subject_code}: {t.old_teacher_name} -> {t.new_teacher_name}")

            lines.append(f"\n• Reassigned Rooms ({len(diff.reassigned_rooms)}):")
            for r in diff.reassigned_rooms:
                lines.append(f"   - {r.subject_code}: {r.old_room_name} -> {r.new_room_name}")

            diff_box.insert("1.0", "\n".join(lines))
            diff_box.configure(state="disabled")

        ctk.CTkButton(ctrl_frame, text="Compute Diff", command=run_diff).pack(side="left", padx=10)
        run_diff()

    def handle_partial_regenerate(self) -> None:
        """Triggers partial regeneration workflow while preserving locked sessions."""
        if not self.service.active_timetable:
            return

        result = self.service.partial_regenerate(self.service.active_timetable.id)
        self.refresh_view()
        self._show_notification(result.message)

    # -------------------------------------------------------------------------
    # Notifications & Modal Alerts
    # -------------------------------------------------------------------------

    def _show_notification(self, message: str) -> None:
        self.status_message.configure(text=message)
        if self.on_status_change:
            self.on_status_change(message)

    def _show_conflict_modal(self, title: str, explanation: str) -> None:
        modal = ctk.CTkToplevel(self)
        modal.title(title)
        modal.geometry("450x260")
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(
            modal,
            text=f"⚠️ {title}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("#DC2626", "#EF4444"),
        ).pack(padx=20, pady=(15, 10))

        box = ctk.CTkTextbox(modal, height=130, wrap="word", font=ctk.CTkFont(size=11))
        box.pack(fill="both", expand=True, padx=20, pady=5)
        box.insert("1.0", explanation)
        box.configure(state="disabled")

        ctk.CTkButton(modal, text="Understood", command=modal.destroy, width=100).pack(pady=10)
