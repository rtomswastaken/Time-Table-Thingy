"""Tests for workload calculations, contact hours vs periods, and constraint violations."""

import pytest
from core.models import Institution, ScheduledSession
from workload.calculator import WorkloadCalculator
from workload.models import (
    TeacherWorkloadRuleExtended,
    WorkloadViolationType,
)


@pytest.fixture
def institution():
    return Institution(
        name="Engineering College",
        code="EC",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        period_duration_minutes=50,  # 50-minute periods
    )


@pytest.fixture
def standard_rule():
    return TeacherWorkloadRuleExtended(
        teacher_id="t1",
        max_periods_per_week=15,
        min_periods_per_week=6,
        max_periods_per_day=4,
        max_consecutive_periods=2,
        max_contact_minutes_per_week=750,  # 15 * 50 = 750 min = 12.5 hrs
        max_periods_per_class_per_week=4,
        max_periods_per_class_per_day=2,
    )


def test_period_count_vs_contact_duration(institution, standard_rule):
    """Calculations distinguish periods and contact minutes with 50-min periods."""
    calculator = WorkloadCalculator()

    # Three 1-period sessions + One 2-period lab = 5 periods total
    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=1,
            start_period=1,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-2",
            day_of_week=2,
            start_period=2,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c2",
        ),
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-lab",
            day_of_week=3,
            start_period=3,
            duration_periods=2,  # 2 periods = 100 minutes
            room_id="r-lab",
            teacher_id="t1",
            class_group_id="c1",
        ),
    ]

    summary = calculator.calculate_teacher_workload(
        teacher_id="t1",
        teacher_name="Dr. Turing",
        sessions=sessions,
        rule=standard_rule,
        institution=institution,
    )

    # 1 + 1 + 1 + 2 = 5 periods
    assert summary.assigned_periods_per_week == 5
    # 5 periods * 50 min = 250 contact minutes = 4.17 hours
    assert summary.assigned_contact_minutes == 250
    assert summary.assigned_contact_hours_per_week == round(250 / 60.0, 2)

    # Remaining capacity: 15 - 5 = 10 periods
    assert summary.remaining_capacity_periods == 10
    assert summary.teaching_days_count == 4
    assert summary.assigned_classes_count == 2


def test_custom_period_durations(institution, standard_rule):
    """Calculations handle heterogeneous period durations without drift."""
    calculator = WorkloadCalculator()

    # Slot 0 is 60 min, slot 1 is 90 min
    custom_durations = {0: 60, 1: 90}

    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=0,
            start_period=0,
            duration_periods=2,  # Occupies slot 0 and slot 1 -> 60 + 90 = 150 min
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
    ]

    summary = calculator.calculate_teacher_workload(
        teacher_id="t1",
        teacher_name="Dr. Turing",
        sessions=sessions,
        rule=standard_rule,
        institution=institution,
        period_durations=custom_durations,
    )

    assert summary.assigned_periods_per_week == 2
    assert summary.assigned_contact_minutes == 150
    assert summary.assigned_contact_hours_per_week == 2.5


def test_consecutive_period_violation(institution, standard_rule):
    """Exceeding consecutive teaching limits triggers a violation."""
    calculator = WorkloadCalculator()

    # 3 consecutive periods (0, 1, 2) on Monday when max is 2
    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=0,
            start_period=0,
            duration_periods=3,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
    ]

    summary = calculator.calculate_teacher_workload(
        teacher_id="t1",
        teacher_name="Dr. Turing",
        sessions=sessions,
        rule=standard_rule,
        institution=institution,
    )

    assert summary.max_consecutive_observed == 3
    violation_types = [v.violation_type for v in summary.violations]
    assert WorkloadViolationType.CONSECUTIVE_PERIODS_EXCEEDED in violation_types


def test_weekly_overload_and_underload(institution, standard_rule):
    """Weekly load below minimum or above maximum is flagged."""
    calculator = WorkloadCalculator()

    # Underloaded: only 2 periods when min is 6
    sessions_under = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=0,
            start_period=0,
            duration_periods=2,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]
    summary_under = calculator.calculate_teacher_workload(
        "t1", "Dr. Turing", sessions_under, standard_rule, institution
    )
    assert summary_under.is_underloaded is True
    assert summary_under.is_overloaded is False
    assert any(v.violation_type == WorkloadViolationType.WEEKLY_PERIODS_BELOW_MIN for v in summary_under.violations)

    # Overloaded: 18 periods when max is 15
    sessions_over = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=day,
            start_period=p,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
        for day in range(5)
        for p in range(4)  # 20 periods
    ]
    summary_over = calculator.calculate_teacher_workload(
        "t1", "Dr. Turing", sessions_over, standard_rule, institution
    )
    assert summary_over.is_overloaded is True
    assert any(v.violation_type == WorkloadViolationType.WEEKLY_PERIODS_EXCEEDED for v in summary_over.violations)


def test_unavailable_slot_violation(institution, standard_rule):
    """Scheduling a teacher during an unavailable slot flags an ERROR violation."""
    calculator = WorkloadCalculator()

    unavailable = {(0, 1)}  # Monday Period 1 is unavailable

    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="sub-1",
            day_of_week=0,
            start_period=1,  # Hits unavailable slot
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]

    summary = calculator.calculate_teacher_workload(
        "t1", "Dr. Turing", sessions, standard_rule, institution, unavailable_slots=unavailable
    )

    unavail_violation = next(
        v for v in summary.violations if v.violation_type == WorkloadViolationType.UNAVAILABLE_SLOT_VIOLATED
    )
    assert unavail_violation.severity == "ERROR"
    assert unavail_violation.day == 0
    assert unavail_violation.period == 1
