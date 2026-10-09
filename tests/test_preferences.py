"""Tests for soft preference modeling, priority weights, and timetable evaluation."""

import pytest
from core.exceptions import ValidationError
from core.models import Institution, ScheduledSession
from workload.models import DetailedTeacherPreference, SoftPreferenceType
from workload.preferences import PreferenceManager


@pytest.fixture
def institution():
    return Institution(
        name="State Tech",
        code="ST",
        working_days=[0, 1, 2, 3, 4],  # Mon-Fri
        periods_per_day=6,
        period_duration_minutes=60,
    )


def test_preference_weight_validation():
    """Preferences must enforce normalized 1..10 weight bounds."""
    with pytest.raises(ValidationError):
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=11,  # Invalid
        )

    with pytest.raises(ValidationError):
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=0,  # Invalid
        )


def test_prefer_morning_evaluation(institution):
    """Evaluates morning preference satisfaction score and penalty."""
    mgr = PreferenceManager()
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=8,
        )
    )

    # All morning sessions (periods 0, 1, 2 out of 6)
    morning_sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=0,
            duration_periods=2,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s2",
            day_of_week=1,
            start_period=1,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
    ]

    report = mgr.evaluate_preferences("t1", morning_sessions, institution)
    assert report.satisfaction_rate == 1.0
    assert report.total_penalty == 0.0

    # Afternoon session (period 4)
    afternoon_sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=4,
            duration_periods=2,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]
    report_afternoon = mgr.evaluate_preferences("t1", afternoon_sessions, institution)
    assert report_afternoon.satisfaction_rate == 0.0
    assert report_afternoon.total_penalty > 0.0


def test_avoid_final_period_evaluation(institution):
    """Avoid final period detects late slot assignments."""
    mgr = PreferenceManager()
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.AVOID_FINAL_PERIOD,
            weight=6,
        )
    )

    # Session ending in period 5 (the final period in 6-period day)
    late_session = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=5,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]

    report = mgr.evaluate_preferences("t1", late_session, institution)
    assert report.items[0].is_satisfied is False
    assert report.items[0].penalty_incurred > 0.0


def test_minimize_gaps_evaluation(institution):
    """Minimize gaps calculates penalties for idle windows between classes."""
    mgr = PreferenceManager()
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.MINIMIZE_GAPS,
            weight=7,
        )
    )

    # Sessions at Period 0 and Period 3 on Monday (idle gap at Period 1 and Period 2)
    gapped_sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s2",
            day_of_week=0,
            start_period=3,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        ),
    ]

    report = mgr.evaluate_preferences("t1", gapped_sessions, institution)
    assert report.items[0].is_satisfied is False
    assert "idle gap" in report.items[0].explanation


def test_conflicting_preferences(institution):
    """System cleanly tracks multiple conflicting soft preferences as weighted objectives."""
    mgr = PreferenceManager()
    # Preference 1: Prefer mornings
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=10,
        )
    )
    # Preference 2: Compact days (teach on only 2 days)
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.MINIMIZE_WORKING_DAYS,
            weight=5,
            target_value=2,
        )
    )

    # Schedule spread across 4 days, but all in the morning
    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id=f"s{d}",
            day_of_week=d,
            start_period=0,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
        for d in range(4)
    ]

    report = mgr.evaluate_preferences("t1", sessions, institution)
    assert len(report.items) == 2

    morning_item = next(i for i in report.items if i.preference_type == SoftPreferenceType.PREFER_MORNING.value)
    days_item = next(i for i in report.items if i.preference_type == SoftPreferenceType.MINIMIZE_WORKING_DAYS.value)

    # Morning is fully satisfied
    assert morning_item.is_satisfied is True
    # Compact days is partially penalized
    assert days_item.is_satisfied is False


def test_solver_preference_matrix_generation(institution):
    """Generates unified slot matrix (-10..+10) for Agent 5 solver."""
    mgr = PreferenceManager()
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=8,
        )
    )
    mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.AVOID_FINAL_PERIOD,
            weight=10,
        )
    )

    matrix = mgr.build_solver_slot_preference_matrix("t1", institution)
    # Morning period (0, 0) should have positive weight
    assert matrix[(0, 0)] > 0
    # Final period (0, 5) should have negative penalty weight
    assert matrix[(0, 5)] < 0
