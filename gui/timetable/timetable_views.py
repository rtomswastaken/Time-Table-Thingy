"""Timetable View Models and Perspective Generators.

Prepares multi-perspective presentation models for the Timetable Workspace:
1. Class View
2. Teacher View
3. Room View
4. Department View
5. Semester View
6. Subject View
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import ConstraintViolation, ScheduledSession
from services.timetable_workspace_service import (
    TimetableWorkspaceService,
    WorkspaceWorkloadSummary,
)


class TimetablePerspective(str, Enum):
    CLASS = "CLASS"
    TEACHER = "TEACHER"
    ROOM = "ROOM"
    DEPARTMENT = "DEPARTMENT"
    SEMESTER = "SEMESTER"
    SUBJECT = "SUBJECT"


@dataclass
class SessionCardViewModel:
    """Presentation data for an individual session card in the grid."""
    session_id: str
    class_group_id: str
    class_name: str
    subject_code: str
    subject_name: str
    teacher_id: str
    teacher_name: str
    room_id: str
    room_name: str
    room_code: str
    session_type: str
    session_type_badge: str
    duration_periods: int = 1
    secondary_teacher_name: Optional[str] = None
    student_group_name: Optional[str] = None
    is_locked: bool = False
    lock_reason: str = ""
    has_conflict: bool = False
    conflict_messages: List[str] = field(default_factory=list)
    is_continuation: bool = False
    continuation_index: int = 0  # 0 for head, 1 for 2nd period, etc.

    @property
    def display_tag(self) -> str:
        """Visual code combining badge and subject."""
        return f"[{self.session_type_badge}] {self.subject_code}"


@dataclass
class GridCellViewModel:
    """Presentation data for a single (day, period) cell in the timetable grid."""
    day: int
    period: int
    is_empty: bool = True
    is_break: bool = False
    break_label: str = ""
    is_gap: bool = False
    sessions: List[SessionCardViewModel] = field(default_factory=list)
    cell_status: str = "NORMAL"  # NORMAL, SELECTED, TARGET, CONFLICT, LOCKED, GAP

    @property
    def head_session(self) -> Optional[SessionCardViewModel]:
        return self.sessions[0] if self.sessions else None


@dataclass
class TimetableGridViewModel:
    """Complete presentation model for rendering a weekly timetable grid."""
    perspective: TimetablePerspective
    target_id: str
    title: str
    subtitle: str
    days: List[int]
    day_names: List[str]
    periods: List[int]
    period_labels: List[str]
    break_periods: Set[int]
    cells: Dict[Tuple[int, int], GridCellViewModel] = field(default_factory=dict)
    total_sessions_count: int = 0
    empty_slots_count: int = 0
    workload_summary: Optional[WorkspaceWorkloadSummary] = None
    room_summary: Optional[Dict[str, Any]] = None
    conflicts_count: int = 0


class TimetableViewModelGenerator:
    """Constructs TimetableGridViewModels for any perspective from the workspace service."""

    DAY_NAMES_MAP = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }

    SESSION_BADGES = {
        "THEORY": "TH",
        "LABORATORY": "LAB",
        "PRACTICAL": "PR",
        "TUTORIAL": "TUT",
        "SEMINAR": "SEM",
        "PROJECT": "PRJ",
    }

    def __init__(self, service: TimetableWorkspaceService) -> None:
        self.service = service

    def generate_view(
        self,
        perspective: TimetablePerspective,
        target_id: str,
    ) -> TimetableGridViewModel:
        """Dispatches generation for the requested perspective."""
        if perspective == TimetablePerspective.CLASS:
            return self.generate_class_view(target_id)
        elif perspective == TimetablePerspective.TEACHER:
            return self.generate_teacher_view(target_id)
        elif perspective == TimetablePerspective.ROOM:
            return self.generate_room_view(target_id)
        elif perspective == TimetablePerspective.DEPARTMENT:
            return self.generate_department_view(target_id)
        elif perspective == TimetablePerspective.SEMESTER:
            return self.generate_semester_view(target_id)
        elif perspective == TimetablePerspective.SUBJECT:
            return self.generate_subject_view(target_id)
        else:
            return self.generate_class_view(target_id)

    # -------------------------------------------------------------------------
    # 1. Class View
    # -------------------------------------------------------------------------

    def generate_class_view(self, class_id: str) -> TimetableGridViewModel:
        bundle = self.service.bundle
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        class_name = self.service.get_class_name(class_id)
        title = f"Class Timetable: {class_name}"
        subtitle = "Complete weekly schedule for class cohort"

        # Filter sessions for this class
        relevant_sessions = [s for s in self.service.active_sessions if s.class_group_id == class_id]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="CLASS"
        )

        total_sessions = len(relevant_sessions)
        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.CLASS,
            target_id=class_id,
            title=title,
            subtitle=subtitle,
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # 2. Teacher View
    # -------------------------------------------------------------------------

    def generate_teacher_view(self, teacher_id: str) -> TimetableGridViewModel:
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        teacher_name = self.service.get_teacher_name(teacher_id)
        workloads = self.service.calculate_workload_summaries()
        teacher_workload = next((w for w in workloads if w.teacher_id == teacher_id), None)

        title = f"Teacher Timetable: {teacher_name}"
        if teacher_workload:
            load_txt = "OVERLOADED" if teacher_workload.is_overloaded else "Within Limit"
            subtitle = (
                f"{teacher_workload.assigned_periods} Assigned Periods / {teacher_workload.weekly_limit} Max "
                f"({load_txt}) • {teacher_workload.idle_gaps} Idle Gaps"
            )
        else:
            subtitle = "Weekly teaching commitments and idle period analysis"

        # Filter sessions where teacher is primary or secondary
        relevant_sessions = [
            s for s in self.service.active_sessions
            if s.teacher_id == teacher_id or s.secondary_teacher_id == teacher_id
        ]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="TEACHER"
        )

        # Mark idle gaps in teacher schedule
        self._highlight_teacher_gaps(days, periods, break_periods, cells)

        total_sessions = len(relevant_sessions)
        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.TEACHER,
            target_id=teacher_id,
            title=title,
            subtitle=subtitle,
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            workload_summary=teacher_workload,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # 3. Room View
    # -------------------------------------------------------------------------

    def generate_room_view(self, room_id: str) -> TimetableGridViewModel:
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        room_name = self.service.get_room_name(room_id)
        room_code = self.service.get_room_code(room_id)

        room_obj = None
        if self.service.bundle:
            room_obj = next((r for r in self.service.bundle.rooms if r.id == room_id), None)

        capacity = room_obj.capacity if room_obj else "Unknown"
        room_type = room_obj.room_type.value if room_obj else "Standard"

        title = f"Room Occupancy: {room_name} ({room_code})"
        subtitle = f"Type: {room_type} • Capacity: {capacity} Seats"

        relevant_sessions = [s for s in self.service.active_sessions if s.room_id == room_id]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="ROOM"
        )

        total_sessions = len(relevant_sessions)
        total_schedulable = len(days) * (len(periods) - len(break_periods))
        occupied_slots = sum(s.duration_periods for s in relevant_sessions)
        util_rate = round((occupied_slots / total_schedulable) * 100.0, 1) if total_schedulable > 0 else 0.0

        room_summary = {
            "capacity": capacity,
            "room_type": room_type,
            "occupancy_rate": util_rate,
            "occupied_periods": occupied_slots,
            "free_periods": total_schedulable - occupied_slots,
        }

        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.ROOM,
            target_id=room_id,
            title=title,
            subtitle=f"{subtitle} • Utilization: {util_rate}% ({occupied_slots}/{total_schedulable} periods)",
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            room_summary=room_summary,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # 4. Department View
    # -------------------------------------------------------------------------

    def generate_department_view(self, department_id: str) -> TimetableGridViewModel:
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        dept_classes: List[str] = []
        if self.service.bundle:
            dept_classes = [c.id for c in self.service.bundle.class_groups if c.department_id == department_id]

        title = f"Department Overview: {department_id}"
        subtitle = f"Aggregated view across {len(dept_classes)} department class sections"

        relevant_sessions = [s for s in self.service.active_sessions if s.class_group_id in dept_classes]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="DEPARTMENT"
        )

        total_sessions = len(relevant_sessions)
        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.DEPARTMENT,
            target_id=department_id,
            title=title,
            subtitle=subtitle,
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # 5. Semester View
    # -------------------------------------------------------------------------

    def generate_semester_view(self, semester_id: str) -> TimetableGridViewModel:
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        sem_classes: List[str] = []
        if self.service.bundle:
            sem_classes = [c.id for c in self.service.bundle.class_groups if c.semester_id == semester_id]

        title = f"Semester Schedule: {semester_id}"
        subtitle = f"All active courses for {len(sem_classes)} classes in semester"

        relevant_sessions = [s for s in self.service.active_sessions if s.class_group_id in sem_classes]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="SEMESTER"
        )

        total_sessions = len(relevant_sessions)
        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.SEMESTER,
            target_id=semester_id,
            title=title,
            subtitle=subtitle,
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # 6. Subject View
    # -------------------------------------------------------------------------

    def generate_subject_view(self, subject_id_or_code: str) -> TimetableGridViewModel:
        days, day_names, periods, period_labels, break_periods = self._get_grid_dimensions()

        # Find matching assignment IDs for this subject
        matching_assignments: Set[str] = set()
        if self.service.bundle:
            for u in self.service.bundle.units:
                if u.subject_id == subject_id_or_code or u.unit_id == subject_id_or_code:
                    matching_assignments.add(u.assignment_id)
                    matching_assignments.add(u.unit_id)

        title = f"Subject View: {subject_id_or_code}"
        subtitle = "All lecture and lab sessions scheduled for this course"

        relevant_sessions = [
            s for s in self.service.active_sessions
            if s.class_subject_assignment_id in matching_assignments
            or s.class_subject_assignment_id == subject_id_or_code
        ]
        violations = self.service.validate_current_schedule()

        cells = self._build_cell_matrix(
            days, periods, break_periods, relevant_sessions, violations, perspective_context="SUBJECT"
        )

        total_sessions = len(relevant_sessions)
        empty_count = sum(1 for c in cells.values() if c.is_empty and not c.is_break)
        conflicts = sum(1 for c in cells.values() if any(s.has_conflict for s in c.sessions))

        return TimetableGridViewModel(
            perspective=TimetablePerspective.SUBJECT,
            target_id=subject_id_or_code,
            title=title,
            subtitle=subtitle,
            days=days,
            day_names=day_names,
            periods=periods,
            period_labels=period_labels,
            break_periods=break_periods,
            cells=cells,
            total_sessions_count=total_sessions,
            empty_slots_count=empty_count,
            conflicts_count=conflicts,
        )

    # -------------------------------------------------------------------------
    # Matrix Builder & Multi-Period Span Logic
    # -------------------------------------------------------------------------

    def _build_cell_matrix(
        self,
        days: List[int],
        periods: List[int],
        break_periods: Set[int],
        sessions: List[ScheduledSession],
        violations: List[ConstraintViolation],
        perspective_context: str,
    ) -> Dict[Tuple[int, int], GridCellViewModel]:
        """Builds the 2D grid matrix mapping (day, period) to GridCellViewModel."""
        cells: Dict[Tuple[int, int], GridCellViewModel] = {}

        # Pre-index violations by session ID
        violation_map: Dict[str, List[str]] = {}
        for v in violations:
            for sid in v.involved_sessions:
                violation_map.setdefault(sid, []).append(f"[{v.severity}] {v.message}")

        # Initialize blank cells
        for d in days:
            for p in periods:
                is_brk = p in break_periods
                brk_lbl = "Break / Recess" if is_brk else ""
                cells[(d, p)] = GridCellViewModel(
                    day=d,
                    period=p,
                    is_empty=True,
                    is_break=is_brk,
                    break_label=brk_lbl,
                )

        # Place sessions and expand multi-period spans
        for s in sessions:
            c_name = self.service.get_class_name(s.class_group_id)
            s_code = self.service.get_subject_code(s.class_subject_assignment_id)
            s_name = self.service.get_subject_name(s.class_subject_assignment_id)
            t_name = self.service.get_teacher_name(s.teacher_id)
            sec_t_name = self.service.get_teacher_name(s.secondary_teacher_id) if s.secondary_teacher_id else None
            r_name = self.service.get_room_name(s.room_id)
            r_code = self.service.get_room_code(s.room_id)
            s_type = self.service.get_session_type(s.class_subject_assignment_id)
            badge = self.SESSION_BADGES.get(s_type.upper(), "TH")

            conf_msgs = violation_map.get(s.id, [])
            has_conf = len(conf_msgs) > 0
            reason = self.service.get_lock_reason(s.id) if s.is_locked else ""

            # Primary head card
            head_card = SessionCardViewModel(
                session_id=s.id,
                class_group_id=s.class_group_id,
                class_name=c_name,
                subject_code=s_code,
                subject_name=s_name,
                teacher_id=s.teacher_id,
                teacher_name=t_name,
                secondary_teacher_name=sec_t_name,
                room_id=s.room_id,
                room_name=r_name,
                room_code=r_code,
                session_type=s_type,
                session_type_badge=badge,
                duration_periods=s.duration_periods,
                student_group_name=s.student_group_id,
                is_locked=s.is_locked,
                lock_reason=reason,
                has_conflict=has_conf,
                conflict_messages=conf_msgs,
                is_continuation=False,
                continuation_index=0,
            )

            # Assign to start period
            start_key = (s.day_of_week, s.start_period)
            if start_key in cells:
                cell = cells[start_key]
                cell.is_empty = False
                cell.sessions.append(head_card)
                if has_conf:
                    cell.cell_status = "CONFLICT"
                elif s.is_locked:
                    cell.cell_status = "LOCKED"

            # Expand continuation periods for multi-period sessions
            for offset in range(1, s.duration_periods):
                cont_period = s.start_period + offset
                cont_key = (s.day_of_week, cont_period)
                if cont_key in cells:
                    cont_card = SessionCardViewModel(
                        session_id=s.id,
                        class_group_id=s.class_group_id,
                        class_name=c_name,
                        subject_code=s_code,
                        subject_name=s_name,
                        teacher_id=s.teacher_id,
                        teacher_name=t_name,
                        secondary_teacher_name=sec_t_name,
                        room_id=s.room_id,
                        room_name=r_name,
                        room_code=r_code,
                        session_type=s_type,
                        session_type_badge=badge,
                        duration_periods=s.duration_periods,
                        student_group_name=s.student_group_id,
                        is_locked=s.is_locked,
                        lock_reason=reason,
                        has_conflict=has_conf,
                        conflict_messages=conf_msgs,
                        is_continuation=True,
                        continuation_index=offset,
                    )
                    cont_cell = cells[cont_key]
                    cont_cell.is_empty = False
                    cont_cell.sessions.append(cont_card)

        return cells

    def _highlight_teacher_gaps(
        self,
        days: List[int],
        periods: List[int],
        break_periods: Set[int],
        cells: Dict[Tuple[int, int], GridCellViewModel],
    ) -> None:
        """Flags idle slots between first and last assigned periods of the day."""
        for d in days:
            occupied = [p for p in periods if not cells[(d, p)].is_empty and not cells[(d, p)].is_break]
            if len(occupied) >= 2:
                first_p = min(occupied)
                last_p = max(occupied)
                for p in range(first_p + 1, last_p):
                    c = cells[(d, p)]
                    if c.is_empty and not c.is_break:
                        c.is_gap = True
                        c.cell_status = "GAP"

    def _get_grid_dimensions(self) -> Tuple[List[int], List[str], List[int], List[str], Set[int]]:
        """Resolves configurable working days and periods from the active bundle."""
        if self.service.bundle:
            days = sorted(self.service.bundle.days)
            day_names = [self.DAY_NAMES_MAP.get(d, f"Day {d}") for d in days]
            num_periods = self.service.bundle.periods_per_day
            periods = list(range(num_periods))
            break_periods = set(self.service.bundle.break_periods)
        else:
            days = [0, 1, 2, 3, 4]
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            periods = list(range(6))
            break_periods = {3}

        # Form period labels with times
        labels: List[str] = []
        base_hour = 9
        for p in periods:
            start_h = base_hour + p
            end_h = start_h + 1
            if p in break_periods:
                labels.append(f"Break\n{start_h:02d}:00-{end_h:02d}:00")
            else:
                labels.append(f"Period {p + 1}\n{start_h:02d}:00-{end_h:02d}:00")

        return days, day_names, periods, labels, break_periods
