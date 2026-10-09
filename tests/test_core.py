"""Tests for shared domain models, validation, and contracts."""

import pytest
from core.models import (
    SessionType,
    RoomType,
    SchedulingStatus,
    ConstraintType,
    Institution,
    Department,
    AcademicYear,
    Semester,
    ClassGroup,
    StudentGroup,
    Teacher,
    TeacherQualification,
    TeacherAvailability,
    TeacherPreference,
    TeacherWorkloadRule,
    Subject,
    SubjectOffering,
    SubjectSessionRequirement,
    ClassSubjectAssignment,
    Room,
    RoomAvailability,
    TimeSlot,
    SchedulableUnit,
    ScheduledSession,
    Timetable,
    TimetableVersion,
    LockedAssignment,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    ConstraintViolation,
    OptimizationMetrics,
)
from core.interfaces import (
    Repository,
    TimetableRepository,
    TimetableSolver,
    ScheduleValidator,
    WorkloadService,
)
from core.exceptions import ValidationError


def test_institution_validation():
    """Verify Institution validates required fields and working days."""
    inst = Institution(name="Tech Institute", code="TI", working_days=[0, 1, 2, 3, 4], periods_per_day=6)
    assert inst.name == "Tech Institute"
    assert inst.code == "TI"
    assert inst.period_duration_minutes == 60

    # Test empty name fails
    with pytest.raises(ValidationError, match="Institution name cannot be empty"):
        Institution(name="  ", code="TI")

    # Test empty code fails
    with pytest.raises(ValidationError, match="Institution code cannot be empty"):
        Institution(name="Tech", code="")

    # Test empty working days fails
    with pytest.raises(ValidationError, match="Institution must have at least one working day"):
        Institution(name="Tech", code="TI", working_days=[])

    # Test invalid day index
    with pytest.raises(ValidationError, match="Invalid day index"):
        Institution(name="Tech", code="TI", working_days=[7])


def test_subject_contact_hours_distinct_from_credits():
    """Verify that academic credits and weekly contact hours are modeled distinctly."""
    # A subject might have 3.0 credits
    subject = Subject(department_id="dept-1", code="CS101", name="Intro to CS", credits=3.0)
    assert subject.credits == 3.0

    # Negative credits fail
    with pytest.raises(ValidationError, match="Credits cannot be negative"):
        Subject(department_id="dept-1", code="CS101", name="Intro", credits=-1.0)

    # But its offering requires 5 contact hours / 5 periods weekly (e.g. 3 lectures + 2 lab)
    offering = SubjectOffering(
        subject_id=subject.id,
        semester_id="sem-1",
        weekly_contact_hours=5.0,
        weekly_periods=5,
    )
    assert offering.weekly_contact_hours != subject.credits
    assert offering.weekly_contact_hours == 5.0
    assert offering.weekly_periods == 5


def test_session_requirements_and_consecutive_periods():
    """Verify laboratory session requirements support consecutive periods."""
    lab_req = SubjectSessionRequirement(
        offering_id="off-1",
        session_type=SessionType.LABORATORY,
        consecutive_periods=2,
        frequency_per_week=1,
        requires_lab=True,
    )
    assert lab_req.consecutive_periods == 2
    assert lab_req.frequency_per_week == 1
    assert lab_req.total_periods == 2

    theory_req = SubjectSessionRequirement(
        offering_id="off-1",
        session_type=SessionType.THEORY,
        consecutive_periods=1,
        frequency_per_week=3,
    )
    assert theory_req.total_periods == 3


def test_period_duration_and_occupied_periods():
    """Verify scheduled session calculates occupied consecutive periods."""
    session = ScheduledSession(
        timetable_id="tt-1",
        class_subject_assignment_id="csa-1",
        day_of_week=0,
        start_period=2,
        duration_periods=3,  # e.g. 3-period block
        room_id="room-1",
        teacher_id="t-1",
        class_group_id="cg-1",
    )
    assert session.occupied_periods == [2, 3, 4]

    with pytest.raises(ValidationError, match="start_period must be >= 0"):
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="csa-1",
            day_of_week=0,
            start_period=-1,
            duration_periods=1,
            room_id="room-1",
            teacher_id="t-1",
            class_group_id="cg-1",
        )


def test_teacher_workload_validation():
    """Verify TeacherWorkloadRule bounds checking."""
    rule = TeacherWorkloadRule(
        teacher_id="t-1",
        max_periods_per_week=18,
        min_periods_per_week=10,
        max_periods_per_day=4,
        max_consecutive_periods=2,
    )
    assert rule.max_periods_per_week == 18

    # Max less than min fails
    with pytest.raises(ValidationError, match="max_periods_per_week cannot be less than min_periods_per_week"):
        TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=5, min_periods_per_week=10)


def test_hard_constraints_distinct_from_soft_preferences():
    """Verify ConstraintViolation differentiates hard vs soft severity."""
    hard_violation = ConstraintViolation(
        violation_type=ConstraintType.TEACHER_DOUBLE_BOOKING,
        is_hard=True,
        severity="ERROR",
        message="Teacher T1 double-booked at Monday Period 1",
        involved_teachers=["t-1"],
    )
    assert hard_violation.is_hard is True
    assert hard_violation.severity == "ERROR"

    soft_violation = ConstraintViolation(
        violation_type=ConstraintType.TEACHER_CONSECUTIVE_LIMIT,
        is_hard=False,
        severity="WARNING",
        message="Teacher T1 prefers not teaching during late afternoon",
        involved_teachers=["t-1"],
    )
    assert soft_violation.is_hard is False
    assert soft_violation.severity == "WARNING"


def test_scheduling_result_statuses():
    """Verify SchedulingResult supports OPTIMAL, FEASIBLE, INFEASIBLE, and TIMEOUT states."""
    # Optimal
    res_optimal = SchedulingResult(
        status=SchedulingStatus.OPTIMAL,
        sessions=[],
        metrics=OptimizationMetrics(total_hard_violations=0, soft_penalty_score=12.5),
        execution_time_seconds=2.4,
    )
    assert res_optimal.status == SchedulingStatus.OPTIMAL
    assert res_optimal.metrics is not None and res_optimal.metrics.total_hard_violations == 0

    # Infeasible
    res_infeasible = SchedulingResult(
        status=SchedulingStatus.INFEASIBLE,
        violations=[
            ConstraintViolation(
                violation_type=ConstraintType.ROOM_UNAVAILABLE,
                is_hard=True,
                severity="ERROR",
                message="Computer Lab capacity insufficient for class",
            )
        ],
        execution_time_seconds=0.5,
    )
    assert res_infeasible.status == SchedulingStatus.INFEASIBLE
    assert len(res_infeasible.violations) == 1

    # Timeout
    res_timeout = SchedulingResult(
        status=SchedulingStatus.TIMEOUT,
        sessions=[],
        message="Solver time limit reached (60.0s)",
        execution_time_seconds=60.0,
    )
    assert res_timeout.status == SchedulingStatus.TIMEOUT


def test_interface_protocols_runtime_checking():
    """Verify runtime protocol verification for repositories and solvers."""
    class DummySolver:
        def solve(self, bundle, config, progress_callback=None, cancel_token=None):
            return SchedulingResult(status=SchedulingStatus.FEASIBLE)

    assert isinstance(DummySolver(), TimetableSolver)

    class DummyValidator:
        def validate(self, sessions, bundle):
            return []
        def validate_move(self, session_id, target_day, target_period, target_room_id, current_sessions, bundle):
            return []

    assert isinstance(DummyValidator(), ScheduleValidator)


def test_schedulable_unit_and_locked_assignments():
    """Verify SchedulableUnit handles locked assignments correctly."""
    unit = SchedulableUnit(
        unit_id="u-1",
        assignment_id="a-1",
        class_group_id="cg-1",
        subject_id="s-1",
        teacher_id="t-1",
        session_type=SessionType.THEORY,
        duration_periods=1,
        locked_day=0,
        locked_period=1,
        locked_room_id="room-101",
    )
    assert unit.locked_day == 0
    assert unit.locked_period == 1
    assert unit.locked_room_id == "room-101"
