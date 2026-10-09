"""Tests for DeterministicScheduleValidator and move validation."""

import pytest

from core.models import (
    ClassGroup,
    ConstraintType,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SessionType,
    Teacher,
    TeacherWorkloadRule,
)
from solver.validator import DeterministicScheduleValidator


@pytest.fixture
def base_test_bundle():
    teacher1 = Teacher(id="t-1", name="Alice", employee_id="E01", department_id="dept-1")
    teacher2 = Teacher(id="t-2", name="Bob", employee_id="E02", department_id="dept-1")
    room1 = Room(id="r-1", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=50)
    room2 = Room(id="r-2", name="Computer Lab", code="CL1", room_type=RoomType.COMPUTER_LAB, capacity=40)
    cg1 = ClassGroup(id="cg-1", name="CS-1", student_count=30, department_id="dept-1", semester_id="sem-1")
    cg2 = ClassGroup(id="cg-2", name="CS-2", student_count=35, department_id="dept-1", semester_id="sem-1")

    unit1 = SchedulableUnit(
        unit_id="u-1",
        assignment_id="a-1",
        class_group_id=cg1.id,
        subject_id="s-1",
        teacher_id=teacher1.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
    )
    unit2 = SchedulableUnit(
        unit_id="u-2",
        assignment_id="a-2",
        class_group_id=cg2.id,
        subject_id="s-2",
        teacher_id=teacher2.id,
        session_type=SessionType.THEORY,
        duration_periods=1,
    )

    return SchedulingInputBundle(
        institution_id="inst-1",
        academic_year_id="ay-1",
        semester_id="sem-1",
        days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        break_periods={3},
        units=[unit1, unit2],
        teachers=[teacher1, teacher2],
        rooms=[room1, room2],
        class_groups=[cg1, cg2],
        teacher_workload_rules={
            "t-1": TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=10, max_periods_per_day=4, max_consecutive_periods=2)
        },
    )


def test_validator_valid_schedule(base_test_bundle):
    """Clean schedule passes validation with zero violations."""
    validator = DeterministicScheduleValidator()
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    s2 = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=1,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-2",
        class_group_id="cg-2",
    )
    violations = validator.validate([s1, s2], base_test_bundle)
    assert violations == []


def test_validator_teacher_double_booking(base_test_bundle):
    """Detects teacher assigned to two simultaneous sessions."""
    validator = DeterministicScheduleValidator()
    # Both sessions taught by teacher t-1 at Monday Period 0
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    s2 = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-2",
        teacher_id="t-1",  # Same teacher!
        class_group_id="cg-2",
    )
    violations = validator.validate([s1, s2], base_test_bundle)
    assert any(v.violation_type == ConstraintType.TEACHER_DOUBLE_BOOKING for v in violations)


def test_validator_room_double_booking(base_test_bundle):
    """Detects room assigned to two simultaneous sessions."""
    validator = DeterministicScheduleValidator()
    # Both sessions in room r-1 at Monday Period 0
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    s2 = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",  # Same room!
        teacher_id="t-2",
        class_group_id="cg-2",
    )
    violations = validator.validate([s1, s2], base_test_bundle)
    assert any(v.violation_type == ConstraintType.ROOM_DOUBLE_BOOKING for v in violations)


def test_validator_class_double_booking_and_subgroups(base_test_bundle):
    """Whole class conflict is detected, but independent lab batches can run in parallel."""
    validator = DeterministicScheduleValidator()

    # Whole class conflict:
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    s2 = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-2",
        teacher_id="t-2",
        class_group_id="cg-1",  # Same class!
    )
    violations = validator.validate([s1, s2], base_test_bundle)
    assert any(v.violation_type == ConstraintType.CLASS_DOUBLE_BOOKING for v in violations)

    # Subgroup parallel batches: Batch 1 and Batch 2 in parallel in different rooms
    s1_batch = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
        student_group_id="batch-A",
    )
    s2_batch = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-2",
        teacher_id="t-2",
        class_group_id="cg-1",
        student_group_id="batch-B",  # Different batch!
    )
    batch_violations = validator.validate([s1_batch, s2_batch], base_test_bundle)
    assert not any(v.violation_type == ConstraintType.CLASS_DOUBLE_BOOKING for v in batch_violations)


def test_validator_room_capacity_exceeded(base_test_bundle):
    """Detects class size exceeding room seating capacity."""
    validator = DeterministicScheduleValidator()
    # cg-2 has 35 students; room r-2 has capacity 40 (OK)
    # create a small room with capacity 20
    small_room_bundle = SchedulingInputBundle(
        institution_id=base_test_bundle.institution_id,
        academic_year_id=base_test_bundle.academic_year_id,
        semester_id=base_test_bundle.semester_id,
        days=base_test_bundle.days,
        periods_per_day=base_test_bundle.periods_per_day,
        break_periods=base_test_bundle.break_periods,
        units=base_test_bundle.units,
        teachers=base_test_bundle.teachers,
        rooms=[Room(id="r-tiny", name="Tiny Room", code="TR", room_type=RoomType.LECTURE_HALL, capacity=15)],
        class_groups=base_test_bundle.class_groups,
    )
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-tiny",
        teacher_id="t-1",
        class_group_id="cg-1",  # 30 students > 15
    )
    violations = validator.validate([s1], small_room_bundle)
    assert any(v.violation_type == ConstraintType.ROOM_CAPACITY_EXCEEDED for v in violations)


def test_validator_teacher_consecutive_limit_violation(base_test_bundle):
    """Detects teacher teaching more consecutive periods than allowed."""
    validator = DeterministicScheduleValidator()
    # t-1 has max_consecutive_periods = 2
    # Schedule 3 periods consecutively: 0, 1, 2
    sessions = [
        ScheduledSession(
            id=f"u-{i}",
            timetable_id="ay-1",
            class_subject_assignment_id=f"a-{i}",
            day_of_week=0,
            start_period=i,
            duration_periods=1,
            room_id="r-1",
            teacher_id="t-1",
            class_group_id="cg-1",
        )
        for i in range(3)  # periods 0, 1, 2 -> 3 consecutive!
    ]
    violations = validator.validate(sessions, base_test_bundle)
    assert any(v.violation_type == ConstraintType.TEACHER_CONSECUTIVE_LIMIT for v in violations)


def test_validator_validate_move(base_test_bundle):
    """validate_move tests potential move before committing."""
    validator = DeterministicScheduleValidator()
    s1 = ScheduledSession(
        id="u-1",
        timetable_id="ay-1",
        class_subject_assignment_id="a-1",
        day_of_week=0,
        start_period=0,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    s2 = ScheduledSession(
        id="u-2",
        timetable_id="ay-1",
        class_subject_assignment_id="a-2",
        day_of_week=0,
        start_period=1,
        duration_periods=1,
        room_id="r-1",
        teacher_id="t-2",
        class_group_id="cg-2",
    )

    # Move s2 to Period 0 (colliding with s1 in room r-1)
    violations = validator.validate_move(
        session_id="u-2",
        target_day=0,
        target_period=0,
        target_room_id="r-1",
        current_sessions=[s1, s2],
        bundle=base_test_bundle,
    )
    assert any(v.violation_type == ConstraintType.ROOM_DOUBLE_BOOKING for v in violations)

    # Valid move of s2 to room r-2 at Period 0
    valid_move_violations = validator.validate_move(
        session_id="u-2",
        target_day=0,
        target_period=0,
        target_room_id="r-2",
        current_sessions=[s1, s2],
        bundle=base_test_bundle,
    )
    assert valid_move_violations == []
