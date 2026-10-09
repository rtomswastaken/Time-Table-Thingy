"""End-to-end integration tests for CpSatTimetableSolver, alternatives, and partial regeneration."""

import threading
import pytest

from core.interfaces import TimetableSolver
from core.models import (
    ClassGroup,
    ConstraintType,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SchedulingStatus,
    SessionType,
    Teacher,
    TeacherWorkloadRule,
)
from solver.cp_sat_solver import CpSatTimetableSolver
from solver.solver import generate_alternatives, partial_regenerate, solve


def test_solver_protocol_conformance():
    """Verify CpSatTimetableSolver conforms to TimetableSolver protocol."""
    solver = CpSatTimetableSolver()
    assert isinstance(solver, TimetableSolver)


def test_solver_end_to_end_optimal():
    """End-to-end solve produces a valid optimal timetable with zero violations."""
    t1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    t2 = Teacher(id="t-2", name="Bob", employee_id="E02", department_id="dept-1")
    r1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    r2 = Room(id="r-2", name="Computer Lab", code="CL", room_type=RoomType.COMPUTER_LAB, capacity=40)
    cg1 = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")
    cg2 = ClassGroup(id="cg-2", name="CS-2", student_count=25, department_id="dept-1", semester_id="sem-1")

    # Class 1: 2 theory with Alice, 1 double lab with Bob
    units = [
        SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u2", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u3", assignment_id="a2", class_group_id=cg1.id, subject_id="s2", teacher_id=t2.id, session_type=SessionType.LABORATORY, duration_periods=2, required_room_type=RoomType.COMPUTER_LAB),
        # Class 2: 2 theory with Bob
        SchedulableUnit(unit_id="u4", assignment_id="a3", class_group_id=cg2.id, subject_id="s3", teacher_id=t2.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u5", assignment_id="a3", class_group_id=cg2.id, subject_id="s3", teacher_id=t2.id, session_type=SessionType.THEORY, duration_periods=1),
    ]

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1, 2],
        periods_per_day=4,
        break_periods={2},  # Recess at period 2
        units=units,
        teachers=[t1, t2],
        rooms=[r1, r2],
        class_groups=[cg1, cg2],
        teacher_workload_rules={
            "t-1": TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=10),
            "t-2": TeacherWorkloadRule(teacher_id="t-2", max_periods_per_week=10),
        },
    )

    config = SchedulingConfig(time_limit_seconds=10.0, random_seed=42)
    progress_events = []
    result = solve(bundle, config, progress_callback=lambda p: progress_events.append(p))

    assert result.status == SchedulingStatus.OPTIMAL
    assert len(result.sessions) == 5
    assert len(result.violations) == 0
    assert result.metrics is not None
    assert result.metrics.total_hard_violations == 0
    assert len(progress_events) > 0


def test_solver_infeasible_reporting():
    """Infeasible configurations return INFEASIBLE status and conflict diagnostics."""
    t1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    r1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg1 = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    # 2 units locked to the EXACT same slot and room!
    units = [
        SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1, locked_day=0, locked_period=0, locked_room_id="r-1"),
        SchedulableUnit(unit_id="u2", assignment_id="a2", class_group_id=cg1.id, subject_id="s2", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1, locked_day=0, locked_period=0, locked_room_id="r-1"),
    ]

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=4,
        break_periods=set(),
        units=units,
        teachers=[t1],
        rooms=[r1],
        class_groups=[cg1],
    )

    result = solve(bundle, SchedulingConfig())
    assert result.status == SchedulingStatus.INFEASIBLE
    assert len(result.violations) > 0
    assert any("Conflicting locked assignments" in v.message or "double-booked" in v.message for v in result.violations)


def test_solver_cancellation():
    """Solver respects cancel_token and aborts execution cleanly."""
    t1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    r1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg1 = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    unit = SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1)
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=4,
        break_periods=set(),
        units=[unit],
        teachers=[t1],
        rooms=[r1],
        class_groups=[cg1],
    )

    cancel_event = threading.Event()
    cancel_event.set()  # Pre-cancelled!

    result = solve(bundle, SchedulingConfig(), cancel_token=cancel_event)
    assert result.status == SchedulingStatus.ERROR
    assert "cancelled" in result.message.lower()


def test_solver_alternative_schedules():
    """Solver can generate distinct alternative feasible schedules."""
    t1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    r1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    r2 = Room(id="r-2", name="Room 2", code="R2", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg1 = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    unit = SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1)

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=3,
        break_periods=set(),
        units=[unit],
        teachers=[t1],
        rooms=[r1, r2],
        class_groups=[cg1],
    )

    alternatives = generate_alternatives(bundle, SchedulingConfig(), count=2)
    assert len(alternatives) == 2
    # Ensure solutions are valid and not identical
    s1 = alternatives[0].sessions[0]
    s2 = alternatives[1].sessions[0]
    assert (s1.day_of_week, s1.start_period, s1.room_id) != (s2.day_of_week, s2.start_period, s2.room_id)


def test_solver_partial_regeneration():
    """Partial regeneration preserves locked sessions while recalculating unlocked classes."""
    t1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    t2 = Teacher(id="t-2", name="Bob", employee_id="E02", department_id="dept-1")
    r1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg1 = ClassGroup(id="cg-1", name="Class 1", student_count=30, department_id="dept-1", semester_id="sem-1")
    cg2 = ClassGroup(id="cg-2", name="Class 2", student_count=30, department_id="dept-1", semester_id="sem-1")

    u1 = SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=t1.id, session_type=SessionType.THEORY, duration_periods=1)
    u2 = SchedulableUnit(unit_id="u2", assignment_id="a2", class_group_id=cg2.id, subject_id="s2", teacher_id=t2.id, session_type=SessionType.THEORY, duration_periods=1)

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=3,
        break_periods=set(),
        units=[u1, u2],
        teachers=[t1, t2],
        rooms=[r1],
        class_groups=[cg1, cg2],
    )

    # Existing schedule: u1 is at day 0, period 0, room r-1
    existing_sessions = [
        ScheduledSession(
            id="u1",
            timetable_id="ay-1",
            class_subject_assignment_id="a1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="r-1",
            teacher_id=t1.id,
            class_group_id=cg1.id,
        ),
        ScheduledSession(
            id="u2",
            timetable_id="ay-1",
            class_subject_assignment_id="a2",
            day_of_week=0,
            start_period=1,
            duration_periods=1,
            room_id="r-1",
            teacher_id=t2.id,
            class_group_id=cg2.id,
        ),
    ]

    # Regenerate only cg2
    result = partial_regenerate(
        bundle=bundle,
        existing_sessions=existing_sessions,
        regenerate_class_ids={"cg-2"},
        config=SchedulingConfig(),
    )

    assert result.status in (SchedulingStatus.OPTIMAL, SchedulingStatus.FEASIBLE)
    assert len(result.sessions) == 2

    # Verify Class 1 remained fixed in place
    s_cg1 = next(s for s in result.sessions if s.id == "u1")
    assert s_cg1.day_of_week == 0
    assert s_cg1.start_period == 0
    assert s_cg1.room_id == "r-1"
