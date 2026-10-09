"""Tests for SessionBuilder and PreflightValidator."""

import pytest

from core.models import (
    ClassGroup,
    ConstraintType,
    Room,
    RoomType,
    SchedulableUnit,
    SchedulingInputBundle,
    SessionType,
    SubjectSessionRequirement,
    Teacher,
    TeacherWorkloadRule,
)
from solver.session_builder import PreflightValidator, SessionBuilder


def test_expand_offering_requirements():
    """Verify session requirements expand to proper unit counts and durations."""
    req_theory = SubjectSessionRequirement(
        offering_id="off-1",
        session_type=SessionType.THEORY,
        consecutive_periods=1,
        frequency_per_week=3,
    )
    req_lab = SubjectSessionRequirement(
        offering_id="off-1",
        session_type=SessionType.LABORATORY,
        consecutive_periods=2,
        frequency_per_week=1,
        requires_lab=True,
        preferred_room_type=RoomType.COMPUTER_LAB,
    )

    units = SessionBuilder.expand_offering_requirements(
        assignment_id="csa-1",
        class_group_id="cg-1",
        subject_id="sub-1",
        primary_teacher_id="t-1",
        requirements=[req_theory, req_lab],
    )

    assert len(units) == 4
    theory_units = [u for u in units if u.session_type == SessionType.THEORY]
    lab_units = [u for u in units if u.session_type == SessionType.LABORATORY]

    assert len(theory_units) == 3
    assert all(u.duration_periods == 1 for u in theory_units)
    assert len(lab_units) == 1
    assert lab_units[0].duration_periods == 2
    assert lab_units[0].required_room_type == RoomType.COMPUTER_LAB


def test_expand_default_weekly_periods():
    """Verify weekly periods expand into full blocks and remainder blocks."""
    # 5 periods split into 2-period blocks -> two 2-period units + one 1-period unit
    units = SessionBuilder.expand_default_weekly_periods(
        assignment_id="csa-2",
        class_group_id="cg-1",
        subject_id="sub-1",
        primary_teacher_id="t-1",
        weekly_periods=5,
        session_duration=2,
    )
    assert len(units) == 3
    durations = sorted([u.duration_periods for u in units])
    assert durations == [1, 2, 2]


def test_preflight_valid_bundle():
    """A well-configured bundle passes preflight with zero fatal issues."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
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
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        break_periods={3},
        units=[unit],
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
    )

    issues = PreflightValidator.validate_bundle(bundle)
    assert not any(i.is_fatal for i in issues)


def test_preflight_no_rooms():
    """Bundle with no rooms triggers fatal error."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=4,
        break_periods=set(),
        units=[],
        teachers=[teacher],
        rooms=[],  # No rooms!
        class_groups=[cg],
    )
    issues = PreflightValidator.validate_bundle(bundle)
    assert any(i.category == "ROOM_RESOURCES" and i.is_fatal for i in issues)


def test_preflight_room_capacity_incompatible():
    """Detects when no room has sufficient capacity for a class cohort."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    small_room = Room(id="r-1", name="Small Room", code="SR", room_type=RoomType.LECTURE_HALL, capacity=20)
    large_cg = ClassGroup(id="cg-1", name="CS-Large", student_count=60, department_id="dept-1", semester_id="sem-1")
    unit = SchedulableUnit(
        unit_id="u-1",
        assignment_id="a-1",
        class_group_id=large_cg.id,
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
        periods_per_day=4,
        break_periods=set(),
        units=[unit],
        teachers=[teacher],
        rooms=[small_room],  # capacity 20 < 60!
        class_groups=[large_cg],
    )
    issues = PreflightValidator.validate_bundle(bundle)
    assert any(i.category == "ROOM_COMPATIBILITY" for i in issues)


def test_preflight_locked_assignment_break_overlap():
    """Detects locked session placed on a lunch break."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
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
        locked_day=0,
        locked_period=3,  # Break period is 3!
        locked_room_id="r-1",
    )
    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1],
        periods_per_day=6,
        break_periods={3},  # Period 3 is a break
        units=[unit],
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
    )
    issues = PreflightValidator.validate_bundle(bundle)
    assert any(i.category == "LOCKED_BREAK_OVERLAP" for i in issues)


def test_preflight_teacher_workload_exceeded():
    """Pigeonhole check flags teacher assigned more periods than max_periods_per_week."""
    teacher = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    room = Room(id="r-1", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=50)
    cg = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")
    units = [
        SchedulableUnit(
            unit_id=f"u-{i}",
            assignment_id=f"a-{i}",
            class_group_id=cg.id,
            subject_id="s-1",
            teacher_id=teacher.id,
            session_type=SessionType.THEORY,
            duration_periods=1,
        )
        for i in range(10)
    ]
    # Teacher max periods rule is 5
    rule = TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=5)

    bundle = SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        break_periods=set(),
        units=units,  # 10 units > rule of 5
        teachers=[teacher],
        rooms=[room],
        class_groups=[cg],
        teacher_workload_rules={"t-1": rule},
    )
    issues = PreflightValidator.validate_bundle(bundle)
    assert any(i.category == "TEACHER_WORKLOAD_EXCEEDED" for i in issues)
