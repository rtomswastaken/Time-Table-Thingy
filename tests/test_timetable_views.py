"""Automated test suite for Timetable Views and Grid Construction.

Tests:
1. Class timetable construction
2. Teacher timetable construction with gap analysis & workload
3. Room occupancy construction with utilization metrics
4. Department & Semester view aggregations
5. Subject-focused view
6. Configurable working days and periods (non-standard 4-day, 6-day, 8-period grids)
7. Multi-period / laboratory session continuity
8. Empty slot differentiation
"""

from __future__ import annotations

import pytest
import tkinter as tk
import customtkinter as ctk

from core.models import (
    ClassGroup,
    ConstraintType,
    ConstraintViolation,
    Institution,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingInputBundle,
    SessionType,
    Subject,
    Teacher,
    TeacherWorkloadRule,
    Timetable,
)
from gui.timetable.timetable_grid import TimetableGrid
from gui.timetable.timetable_views import (
    TimetablePerspective,
    TimetableViewModelGenerator,
)
from services.timetable_workspace_service import (
    InMemoryTimetableRepository,
    TimetableWorkspaceService,
)


@pytest.fixture
def synthetic_bundle() -> SchedulingInputBundle:
    """Creates a realistic, complete academic bundle for testing."""
    teachers = [
        Teacher(id="T1", department_id="CS", name="Dr. Alan Turing", employee_id="EMP01"),
        Teacher(id="T2", department_id="CS", name="Ada Lovelace", employee_id="EMP02"),
        Teacher(id="T3", department_id="CS", name="Grace Hopper", employee_id="EMP03"),
    ]

    rooms = [
        Room(id="R101", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=60),
        Room(id="LAB1", name="Computing Lab 1", code="LAB1", room_type=RoomType.COMPUTER_LAB, capacity=30),
    ]

    class_groups = [
        ClassGroup(id="CS-3A", department_id="CS", semester_id="SEM-3", name="CS-3A", student_count=50),
        ClassGroup(id="CS-3B", department_id="CS", semester_id="SEM-3", name="CS-3B", student_count=45),
        ClassGroup(id="CS-5A", department_id="CS", semester_id="SEM-5", name="CS-5A", student_count=40),
    ]

    units = [
        SchedulableUnit(
            unit_id="U1",
            assignment_id="A1",
            class_group_id="CS-3A",
            subject_id="CS101",
            teacher_id="T1",
            session_type=SessionType.THEORY,
            duration_periods=1,
        ),
        SchedulableUnit(
            unit_id="U2",
            assignment_id="A2",
            class_group_id="CS-3A",
            subject_id="CS102",
            teacher_id="T2",
            session_type=SessionType.LABORATORY,
            duration_periods=2,
            required_room_type=RoomType.COMPUTER_LAB,
        ),
        SchedulableUnit(
            unit_id="U3",
            assignment_id="A3",
            class_group_id="CS-3B",
            subject_id="CS101",
            teacher_id="T1",
            session_type=SessionType.THEORY,
            duration_periods=1,
        ),
    ]

    workload_rules = {
        "T1": TeacherWorkloadRule(teacher_id="T1", max_periods_per_week=18, max_periods_per_day=4),
        "T2": TeacherWorkloadRule(teacher_id="T2", max_periods_per_week=16, max_periods_per_day=4),
    }

    return SchedulingInputBundle(
        institution_id="INST-1",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        days=[0, 1, 2, 3, 4],  # Mon-Fri
        periods_per_day=6,
        break_periods={3},     # Period index 3 is break
        units=units,
        teachers=teachers,
        rooms=rooms,
        class_groups=class_groups,
        teacher_workload_rules=workload_rules,
    )


@pytest.fixture
def workspace_with_sessions(synthetic_bundle: SchedulingInputBundle) -> TimetableWorkspaceService:
    subjects = [
        Subject(id="CS101", code="CS101", name="Data Structures", department_id="CS", credits=3.0),
        Subject(id="CS102", code="CS102", name="Software Engineering Lab", department_id="CS", credits=2.0),
    ]

    service = TimetableWorkspaceService(
        repository=InMemoryTimetableRepository(),
        bundle=synthetic_bundle,
        subjects=subjects,
    )

    tt = Timetable(
        id="TT-TEST-1",
        name="Odd Semester 2026 Test",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        version=1,
    )

    sessions = [
        # Mon P1: CS-3A Theory with T1 in R101
        ScheduledSession(
            id="S1",
            timetable_id="TT-TEST-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
            is_locked=True,
        ),
        # Mon P4-P5: CS-3A Lab with T2 in LAB1 (2 periods)
        ScheduledSession(
            id="S2",
            timetable_id="TT-TEST-1",
            class_subject_assignment_id="A2",
            day_of_week=0,
            start_period=4,
            duration_periods=2,
            room_id="LAB1",
            teacher_id="T2",
            class_group_id="CS-3A",
        ),
        # Tue P2: CS-3B Theory with T1 in R101
        ScheduledSession(
            id="S3",
            timetable_id="TT-TEST-1",
            class_subject_assignment_id="A3",
            day_of_week=1,
            start_period=1,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3B",
        ),
        # Mon P5: T1 teaching CS-5A (causing evening slot after P1 for gap testing)
        ScheduledSession(
            id="S4",
            timetable_id="TT-TEST-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=5,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-5A",
        ),
    ]

    service.repository.save_timetable(tt, sessions)
    service.load_timetable("TT-TEST-1")
    return service


def test_class_timetable_construction(workspace_with_sessions: TimetableWorkspaceService):
    """Verify class view populates correct sessions, spans, and empty periods."""
    generator = TimetableViewModelGenerator(workspace_with_sessions)
    vm = generator.generate_view(TimetablePerspective.CLASS, "CS-3A")

    assert vm.perspective == TimetablePerspective.CLASS
    assert vm.target_id == "CS-3A"
    assert "CS-3A" in vm.title
    assert vm.days == [0, 1, 2, 3, 4]
    assert len(vm.periods) == 6

    # Verify Mon Period 0 has S1
    cell_mon_p0 = vm.cells[(0, 0)]
    assert not cell_mon_p0.is_empty
    assert len(cell_mon_p0.sessions) == 1
    assert cell_mon_p0.sessions[0].session_id == "S1"
    assert cell_mon_p0.sessions[0].subject_code == "CS101"
    assert cell_mon_p0.sessions[0].is_locked is True

    # Verify Break period (Mon P3)
    cell_mon_break = vm.cells[(0, 3)]
    assert cell_mon_break.is_break is True
    assert "Break" in cell_mon_break.break_label

    # Verify 2-period lab on Mon P4 and P5
    cell_mon_p4 = vm.cells[(0, 4)]
    assert not cell_mon_p4.is_empty
    assert cell_mon_p4.sessions[0].session_id == "S2"
    assert cell_mon_p4.sessions[0].is_continuation is False
    assert cell_mon_p4.sessions[0].duration_periods == 2

    cell_mon_p5 = vm.cells[(0, 5)]
    assert not cell_mon_p5.is_empty
    assert cell_mon_p5.sessions[0].session_id == "S2"
    assert cell_mon_p5.sessions[0].is_continuation is True

    # Total sessions in CS-3A should be 2 (S1 and S2)
    assert vm.total_sessions_count == 2


def test_teacher_timetable_and_gaps(workspace_with_sessions: TimetableWorkspaceService):
    """Verify teacher view reflects all teaching sessions and highlights idle gaps."""
    generator = TimetableViewModelGenerator(workspace_with_sessions)
    vm = generator.generate_view(TimetablePerspective.TEACHER, "T1")

    assert vm.perspective == TimetablePerspective.TEACHER
    assert vm.target_id == "T1"
    assert "Dr. Alan Turing" in vm.title

    # T1 teaches on Mon at P0 (S1) and P5 (S4), so P1, P2 are idle gaps (P3 is break)
    cell_mon_p1 = vm.cells[(0, 1)]
    assert cell_mon_p1.is_gap is True
    assert cell_mon_p1.cell_status == "GAP"

    cell_mon_p2 = vm.cells[(0, 2)]
    assert cell_mon_p2.is_gap is True

    # Workload summary
    assert vm.workload_summary is not None
    assert vm.workload_summary.teacher_id == "T1"
    assert vm.workload_summary.assigned_periods == 3  # S1, S3, S4
    assert vm.workload_summary.idle_gaps > 0


def test_room_occupancy_and_utilization(workspace_with_sessions: TimetableWorkspaceService):
    """Verify room view displays occupancy, available periods, and utilization metrics."""
    generator = TimetableViewModelGenerator(workspace_with_sessions)
    vm = generator.generate_view(TimetablePerspective.ROOM, "R101")

    assert vm.perspective == TimetablePerspective.ROOM
    assert "Room 101" in vm.title
    assert vm.room_summary is not None
    assert vm.room_summary["capacity"] == 60
    assert vm.room_summary["occupancy_rate"] > 0

    # R101 is used at Mon P0 (S1), Tue P1 (S3), Mon P5 (S4)
    assert not vm.cells[(0, 0)].is_empty
    assert not vm.cells[(1, 1)].is_empty
    assert not vm.cells[(0, 5)].is_empty

    # Wed P0 is empty/available
    assert vm.cells[(2, 0)].is_empty is True


def test_department_and_semester_views(workspace_with_sessions: TimetableWorkspaceService):
    """Verify department and semester aggregated views collect cross-class sessions."""
    generator = TimetableViewModelGenerator(workspace_with_sessions)

    # Department view
    dept_vm = generator.generate_view(TimetablePerspective.DEPARTMENT, "CS")
    assert dept_vm.perspective == TimetablePerspective.DEPARTMENT
    # All classes in CS
    assert dept_vm.total_sessions_count == 4

    # Semester view
    sem_vm = generator.generate_view(TimetablePerspective.SEMESTER, "SEM-3")
    assert sem_vm.perspective == TimetablePerspective.SEMESTER
    # CS-3A and CS-3B are SEM-3 (S1, S2, S3)
    assert sem_vm.total_sessions_count == 3


def test_subject_view(workspace_with_sessions: TimetableWorkspaceService):
    """Verify subject view collects all sessions for that subject across sections."""
    generator = TimetableViewModelGenerator(workspace_with_sessions)
    subj_vm = generator.generate_view(TimetablePerspective.SUBJECT, "CS101")

    assert subj_vm.perspective == TimetablePerspective.SUBJECT
    assert "CS101" in subj_vm.title
    # CS101 is scheduled in S1 (CS-3A), S3 (CS-3B), S4 (CS-5A)
    assert subj_vm.total_sessions_count == 3


def test_custom_days_and_periods_grid():
    """Verify grid handles non-standard 6-day, 8-period institutions without hardcoding."""
    bundle_6day = SchedulingInputBundle(
        institution_id="INST-POLY",
        academic_year_id="AY-2026",
        semester_id="SEM-1",
        days=[0, 1, 2, 3, 4, 5],  # 6 working days (Mon-Sat)
        periods_per_day=8,         # 8 periods per day
        break_periods={4},
        units=[],
        teachers=[],
        rooms=[],
        class_groups=[ClassGroup(id="ME-1A", department_id="ME", semester_id="SEM-1", name="ME-1A", student_count=30)],
    )

    service = TimetableWorkspaceService(bundle=bundle_6day)
    generator = TimetableViewModelGenerator(service)
    vm = generator.generate_view(TimetablePerspective.CLASS, "ME-1A")

    assert len(vm.days) == 6
    assert vm.day_names[-1] == "Saturday"
    assert len(vm.periods) == 8
    assert len(vm.cells) == 6 * 8
    assert vm.cells[(5, 7)].is_empty is True  # Saturday Period 8 exists


def test_tkinter_grid_rendering_headless(workspace_with_sessions: TimetableWorkspaceService):
    """Verify TimetableGrid CustomTkinter widget renders widgets cleanly."""
    root = tk.Tk()
    root.withdraw()
    try:
        grid = TimetableGrid(root)
        generator = TimetableViewModelGenerator(workspace_with_sessions)
        vm = generator.generate_view(TimetablePerspective.CLASS, "CS-3A")
        grid.render_grid(vm)

        # Check child widgets were created
        children = grid.winfo_children()
        assert len(children) > 0
    finally:
        root.destroy()
