"""Tests for CP-SAT constraint formulations."""

import pytest
from ortools.sat.python import cp_model

from core.models import (
    ClassGroup,
    ConstraintType,
    Room,
    RoomType,
    SchedulableUnit,
    SchedulingConfig,
    SchedulingInputBundle,
    SessionType,
    Teacher,
    TeacherWorkloadRule,
)
from solver.constraints import ConstraintModelBuilder
from solver.results import ResultBuilder


def test_constraint_no_teacher_double_booking():
    """CP-SAT model prevents shared teacher double-booking across classes."""
    teacher = Teacher(id="t-1", name="Shared Teacher", employee_id="E01", department_id="dept-1")
    room1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    room2 = Room(id="r-2", name="Room 2", code="R2", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg1 = ClassGroup(id="cg-1", name="Class 1", student_count=30, department_id="dept-1", semester_id="sem-1")
    cg2 = ClassGroup(id="cg-2", name="Class 2", student_count=30, department_id="dept-1", semester_id="sem-1")

    # 2 units for Class 1 and 2 units for Class 2, all taught by teacher t-1
    # on a small schedule of 1 day with 4 periods
    units = [
        SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id=cg1.id, subject_id="s1", teacher_id=teacher.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u2", assignment_id="a2", class_group_id=cg1.id, subject_id="s1", teacher_id=teacher.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u3", assignment_id="a3", class_group_id=cg2.id, subject_id="s2", teacher_id=teacher.id, session_type=SessionType.THEORY, duration_periods=1),
        SchedulableUnit(unit_id="u4", assignment_id="a4", class_group_id=cg2.id, subject_id="s2", teacher_id=teacher.id, session_type=SessionType.THEORY, duration_periods=1),
    ]

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=4,
        break_periods=set(),
        units=units,
        teachers=[teacher],
        rooms=[room1, room2],
        class_groups=[cg1, cg2],
    )

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 4

    # Assert no two sessions share the same period
    periods = [s.start_period for s in sessions]
    assert len(set(periods)) == 4


def test_constraint_consecutive_laboratory_block():
    """CP-SAT correctly schedules multi-period consecutive laboratory blocks."""
    teacher = Teacher(id="t-1", name="Lab Instructor", employee_id="E01", department_id="dept-1")
    lab_room = Room(id="r-lab", name="Computer Lab", code="CL", room_type=RoomType.COMPUTER_LAB, capacity=40)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    # Double-period lab block (duration=2)
    lab_unit = SchedulableUnit(
        unit_id="u-lab",
        assignment_id="a-lab",
        class_group_id=cg.id,
        subject_id="s-lab",
        teacher_id=teacher.id,
        session_type=SessionType.LABORATORY,
        duration_periods=2,
        required_room_type=RoomType.COMPUTER_LAB,
    )

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=4,
        break_periods={2},  # Break at period 2!
        units=[lab_unit],
        teachers=[teacher],
        rooms=[lab_room],
        class_groups=[cg],
    )

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    session = sessions[0]

    # Because period 2 is a break, duration 2 can only be placed at period 0 (occupies 0 and 1).
    # It cannot be at period 1 (would occupy 1 and 2[break]) or period 2 (break) or period 3 (exceeds day length 4).
    assert session.start_period == 0
    assert session.occupied_periods == [0, 1]


def test_constraint_teacher_availability():
    """CP-SAT respects teacher unavailability matrix."""
    teacher = Teacher(id="t-1", name="Prof Turing", employee_id="E01", department_id="dept-1")
    room = Room(id="r-1", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    unit = SchedulableUnit(
        unit_id="u-1",
        assignment_id="a-1",
        class_group_id=cg.id,
        subject_id="s-1",
        teacher_id=teacher.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
    )

    # Teacher is unavailable for periods 0 and 1 on day 0
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=3,
        break_periods=set(),
        units=[unit],
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
        teacher_availability={"t-1": {(0, 0), (0, 1)}},  # Unavailable at 0 and 1
    )

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    # Must be placed at period 2
    assert sessions[0].start_period == 2


def test_constraint_locked_assignment_preserved():
    """CP-SAT strictly anchors locked sessions to specified day, period, and room."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    room1 = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    room2 = Room(id="r-2", name="Room 2", code="R2", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    locked_unit = SchedulableUnit(
        unit_id="u-locked",
        assignment_id="a-locked",
        class_group_id=cg.id,
        subject_id="s-1",
        teacher_id=teacher.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
        locked_day=1,
        locked_period=3,
        locked_room_id="r-2",
    )

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=5,
        break_periods=set(),
        units=[locked_unit],
        teachers=[teacher],
        rooms=[room1, room2],
        class_groups=[cg],
    )

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.day_of_week == 1
    assert s.start_period == 3
    assert s.room_id == "r-2"
    assert s.is_locked is True


def test_constraint_teacher_max_periods_per_day():
    """CP-SAT respects teacher max_periods_per_day limit."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    room = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    # 4 units across 2 days (periods_per_day=4)
    # Teacher rule: max 2 periods per day
    units = [
        SchedulableUnit(unit_id=f"u-{i}", assignment_id=f"a-{i}", class_group_id=cg.id, subject_id="s-1", teacher_id=teacher.id, session_type=SessionType.THEORY, duration_periods=1)
        for i in range(4)
    ]

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=4,
        break_periods=set(),
        units=units,
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
        teacher_workload_rules={
            "t-1": TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=4, max_periods_per_day=2)
        },
    )

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 4

    day_0_count = sum(1 for s in sessions if s.day_of_week == 0)
    day_1_count = sum(1 for s in sessions if s.day_of_week == 1)

    assert day_0_count == 2
    assert day_1_count == 2
