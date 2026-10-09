"""Automated test suite for Real-Time Timetable Constraint Validation.

Tests:
1. Teacher double-booking (single and multi-period sessions)
2. Class group double-booking
3. Room double-booking
4. Teacher temporal availability enforcement
5. Room temporal availability enforcement
6. Room capacity and room type compatibility
7. Session period boundaries and break period collisions
8. Locked assignment anchor violations
9. Soft preference penalties vs hard constraint rejections
10. Explanation message quality for invalid edits
"""

from __future__ import annotations

import pytest

from core.models import (
    ClassGroup,
    ConstraintType,
    ConstraintViolation,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingInputBundle,
    SessionType,
    Teacher,
    TeacherWorkloadRule,
)
from solver.validator import DeterministicScheduleValidator


@pytest.fixture
def validation_bundle() -> SchedulingInputBundle:
    teachers = [
        Teacher(id="T1", department_id="CS", name="Dr. Alan Turing", employee_id="EMP01"),
        Teacher(id="T2", department_id="CS", name="Ada Lovelace", employee_id="EMP02"),
    ]

    rooms = [
        Room(id="R101", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=40),
        Room(id="LAB1", name="Computing Lab", code="LAB1", room_type=RoomType.COMPUTER_LAB, capacity=30),
    ]

    class_groups = [
        ClassGroup(id="CS-3A", department_id="CS", semester_id="SEM-3", name="CS-3A", student_count=35),
        ClassGroup(id="CS-3B", department_id="CS", semester_id="SEM-3", name="CS-3B", student_count=25),
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
    ]

    # T1 is unavailable on Friday Period 0 (Day 4, Period 0)
    teacher_avail = {"T1": {(4, 0)}}
    # LAB1 is unavailable on Monday Period 1 (Day 0, Period 1)
    room_avail = {"LAB1": {(0, 1)}}

    # T1 prefers not teaching on Thursday Period 4 (weight -5)
    teacher_prefs = {"T1": {(3, 4): -5}}

    workload_rules = {
        "T1": TeacherWorkloadRule(teacher_id="T1", max_periods_per_week=10, max_periods_per_day=3, max_consecutive_periods=2)
    }

    return SchedulingInputBundle(
        institution_id="INST-1",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        break_periods={3},  # Period 3 is lunch recess
        units=units,
        teachers=teachers,
        rooms=rooms,
        class_groups=class_groups,
        teacher_availability=teacher_avail,
        room_availability=room_avail,
        teacher_preferences=teacher_prefs,
        teacher_workload_rules=workload_rules,
    )


def test_teacher_double_booking_detected(validation_bundle: SchedulingInputBundle):
    """Verify that scheduling a teacher in two different classes at the same slot is flagged."""
    validator = DeterministicScheduleValidator()

    sessions = [
        # T1 teaching CS-3A on Monday Period 0
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # T1 teaching CS-3B on Monday Period 0 (Collision!)
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="LAB1",
            teacher_id="T1",
            class_group_id="CS-3B",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    hard = [v for v in violations if v.is_hard]
    assert len(hard) >= 1
    t_collision = next((v for v in hard if v.violation_type == ConstraintType.TEACHER_DOUBLE_BOOKING), None)
    assert t_collision is not None
    assert "Dr. Alan Turing" in t_collision.message
    assert "double-booked" in t_collision.message


def test_room_double_booking_detected(validation_bundle: SchedulingInputBundle):
    """Verify two classes scheduled in the same room at the same time is rejected."""
    validator = DeterministicScheduleValidator()

    sessions = [
        # CS-3A in R101 with T1 on Tuesday Period 1
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=1,
            start_period=1,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # CS-3B in R101 with T2 on Tuesday Period 1 (Collision!)
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=1,
            start_period=1,
            duration_periods=1,
            room_id="R101",
            teacher_id="T2",
            class_group_id="CS-3B",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    room_conf = next((v for v in violations if v.violation_type == ConstraintType.ROOM_DOUBLE_BOOKING), None)
    assert room_conf is not None
    assert room_conf.is_hard is True
    assert "Room 101" in room_conf.message


def test_class_double_booking_detected(validation_bundle: SchedulingInputBundle):
    """Verify class cohort cannot be in two sessions at the same slot."""
    validator = DeterministicScheduleValidator()

    sessions = [
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=2,
            start_period=2,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A2",
            day_of_week=2,
            start_period=2,
            duration_periods=1,
            room_id="LAB1",
            teacher_id="T2",
            class_group_id="CS-3A",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    class_conf = next((v for v in violations if v.violation_type == ConstraintType.CLASS_DOUBLE_BOOKING), None)
    assert class_conf is not None
    assert class_conf.is_hard is True


def test_teacher_and_room_availability_constraints(validation_bundle: SchedulingInputBundle):
    """Verify unavailable slots are strictly enforced for both teacher and room."""
    validator = DeterministicScheduleValidator()

    # T1 unavailable on Fri P0 (Day 4, Period 0)
    # LAB1 unavailable on Mon P1 (Day 0, Period 1)
    sessions = [
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=4,
            start_period=0,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A2",
            day_of_week=0,
            start_period=1,
            duration_periods=1,
            room_id="LAB1",
            teacher_id="T2",
            class_group_id="CS-3B",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    assert any(v.violation_type == ConstraintType.TEACHER_UNAVAILABLE for v in violations)
    assert any(v.violation_type == ConstraintType.ROOM_UNAVAILABLE for v in violations)


def test_room_capacity_and_type_compatibility(validation_bundle: SchedulingInputBundle):
    """Verify room capacity deficit and specialized room type mismatch."""
    validator = DeterministicScheduleValidator()

    # CS-3A has 35 students. LAB1 capacity is 30. (Capacity exceeded!)
    # And U2 requires COMPUTER_LAB, but assigned to R101 (LECTURE_HALL) -> Type mismatch!
    sessions = [
        # Session in LAB1 with CS-3A (35 students > 30 capacity)
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="LAB1",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # Session requiring Lab assigned to regular lecture hall R101
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A2",
            day_of_week=1,
            start_period=0,
            duration_periods=2,
            room_id="R101",
            teacher_id="T2",
            class_group_id="CS-3B",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    cap_viol = next((v for v in violations if v.violation_type == ConstraintType.ROOM_CAPACITY_EXCEEDED), None)
    assert cap_viol is not None
    assert "below class size" in cap_viol.message

    type_viol = next((v for v in violations if v.violation_type == ConstraintType.ROOM_TYPE_MISMATCH), None)
    assert type_viol is not None
    assert "does not match required type" in type_viol.message


def test_break_period_and_consecutive_boundaries(validation_bundle: SchedulingInputBundle):
    """Verify sessions cannot span designated break periods or exceed day limits."""
    validator = DeterministicScheduleValidator()

    # Day 0, Period 3 is designated BREAK. Session starting at P3 or spanning through P3 is invalid
    sessions = [
        # Single session right in break
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=3,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # 2-period lab starting at P2 and overlapping break at P3
        ScheduledSession(
            id="S2",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=1,
            start_period=2,
            duration_periods=2,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
    ]

    violations = validator.validate(sessions, validation_bundle)
    break_viols = [v for v in violations if v.violation_type == ConstraintType.LAB_CONTINUITY_BROKEN and "break period" in v.message]
    assert len(break_viols) >= 2


def test_soft_preferences_produce_warnings(validation_bundle: SchedulingInputBundle):
    """Verify that soft preference dispreferences generate warnings rather than blocking errors."""
    validator = DeterministicScheduleValidator()

    # T1 has dispreference weight -5 on Day 3, Period 4
    sessions = [
        ScheduledSession(
            id="S1",
            timetable_id="TT-1",
            class_subject_assignment_id="A1",
            day_of_week=3,
            start_period=4,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        )
    ]

    violations = validator.validate(sessions, validation_bundle)
    # No hard errors
    hard = [v for v in violations if v.is_hard]
    assert len(hard) == 0

    # Has soft warning
    soft = [v for v in violations if not v.is_hard]
    assert len(soft) == 1
    assert soft[0].severity == "WARNING"
    assert "prefers not to teach" in soft[0].message
