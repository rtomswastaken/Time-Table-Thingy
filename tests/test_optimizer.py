"""Tests for soft preference optimization and objective terms."""

import pytest
from ortools.sat.python import cp_model

from core.models import (
    ClassGroup,
    Room,
    RoomType,
    SchedulableUnit,
    SchedulingConfig,
    SchedulingInputBundle,
    SessionType,
    Teacher,
)
from solver.constraints import ConstraintModelBuilder
from solver.optimizer import ObjectiveOptimizer
from solver.results import ResultBuilder


def test_optimizer_teacher_preference():
    """Optimizer steers sessions to preferred time slots."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    room = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")

    # 1 session with choice between period 0 and period 1
    unit = SchedulableUnit(
        unit_id="u-1",
        assignment_id="a-1",
        class_group_id=cg.id,
        subject_id="s-1",
        teacher_id=teacher.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
    )

    # Teacher strongly prefers period 1 (score +10) over period 0 (score -5)
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=2,
        break_periods=set(),
        units=[unit],
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
        teacher_preferences={"t-1": {(0, 0): -5, (0, 1): 10}},
    )

    config = SchedulingConfig(weight_teacher_preference=50)
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()
    ObjectiveOptimizer.apply_objective(model, bundle, config, variables)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    # Period 1 must be chosen due to higher preference score!
    assert sessions[0].start_period == 1


def test_optimizer_room_preference_and_specialist_conservation():
    """Optimizer places regular lectures in classroom rather than specialist computer lab."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    # Home room classroom and specialist computer lab
    normal_room = Room(id="r-classroom", name="Classroom 101", code="CR1", room_type=RoomType.LECTURE_HALL, capacity=50)
    lab_room = Room(id="r-lab", name="Computer Lab", code="CL", room_type=RoomType.COMPUTER_LAB, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1", home_room_id="r-classroom")

    # General theory lecture (does not require lab)
    unit = SchedulableUnit(
        unit_id="u-theory",
        assignment_id="a-theory",
        class_group_id=cg.id,
        subject_id="s-1",
        teacher_id=teacher.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
        required_room_type=None,
    )

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0],
        periods_per_day=2,
        break_periods=set(),
        units=[unit],
        teachers=[teacher],
        rooms=[normal_room, lab_room],
        class_groups=[cg],
    )

    config = SchedulingConfig(weight_preferred_room=20)
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()
    ObjectiveOptimizer.apply_objective(model, bundle, config, variables)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    # Classroom must be chosen over specialist lab
    assert sessions[0].room_id == "r-classroom"


def test_optimizer_schedule_stability():
    """Stability penalty keeps unlocked sessions at their baseline assignments."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    room = Room(id="r-1", name="Room 1", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
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

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=3,
        break_periods=set(),
        units=[unit],
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
    )

    # Baseline: u-1 was at day 1, period 2
    baseline = {"u-1": (1, 2, "r-1")}

    config = SchedulingConfig()
    builder = ConstraintModelBuilder(bundle, config)
    model, variables = builder.build()
    ObjectiveOptimizer.apply_objective(model, bundle, config, variables, baseline_assignments=baseline)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    assert status == cp_model.OPTIMAL
    sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
    assert len(sessions) == 1
    # Must preserve baseline slot
    assert sessions[0].day_of_week == 1
    assert sessions[0].start_period == 2
