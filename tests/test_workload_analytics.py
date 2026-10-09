"""Tests for department workload analytics and fairness analysis."""

import pytest
from core.models import Institution, ScheduledSession, Teacher
from workload.analytics import WorkloadAnalytics
from workload.calculator import WorkloadCalculator
from workload.models import TeacherWorkloadRuleExtended


@pytest.fixture
def institution():
    return Institution(
        name="Institute of Science",
        code="IOS",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        period_duration_minutes=60,
    )


def test_department_summary(institution):
    """Department summary aggregates periods, hours, overloads, and unused capacity."""
    calculator = WorkloadCalculator()
    analytics = WorkloadAnalytics(calculator)

    teachers = [
        Teacher(department_id="d1", name="Prof. Alpha", employee_id="E1", id="t1"),
        Teacher(department_id="d1", name="Prof. Beta", employee_id="E2", id="t2"),
        Teacher(department_id="d2", name="Prof. Gamma", employee_id="E3", id="t3"),  # Different dept
    ]

    rule = TeacherWorkloadRuleExtended(
        teacher_id="t1",
        max_periods_per_week=20,
        min_periods_per_week=10,
    )

    # Teacher 1 has 15 periods (normal load)
    sessions_t1 = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=d,
            start_period=p,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
        for d in range(5)
        for p in range(3)  # 15 periods
    ]
    summary_t1 = calculator.calculate_teacher_workload("t1", "Prof. Alpha", sessions_t1, rule, institution)

    # Teacher 2 has only 4 periods (underloaded, high unused capacity)
    rule_t2 = TeacherWorkloadRuleExtended(teacher_id="t2", max_periods_per_week=20, min_periods_per_week=10)
    sessions_t2 = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s2",
            day_of_week=0,
            start_period=0,
            duration_periods=4,
            room_id="r1",
            teacher_id="t2",
            class_group_id="c1",
        )
    ]
    summary_t2 = calculator.calculate_teacher_workload("t2", "Prof. Beta", sessions_t2, rule_t2, institution)

    dept_summary = analytics.compute_department_summary(
        department_id="d1",
        department_name="Computer Science",
        teachers=teachers,
        summaries=[summary_t1, summary_t2],
    )

    assert dept_summary.total_teachers == 2
    assert dept_summary.total_assigned_periods == 19
    assert dept_summary.total_assigned_contact_hours == 19.0
    assert dept_summary.average_periods_per_teacher == 9.5
    assert "Prof. Beta" in dept_summary.underloaded_teachers
    assert "Prof. Beta" in dept_summary.teachers_with_high_unused_capacity
    assert dept_summary.workload_std_deviation > 0.0


def test_fairness_analysis(institution):
    """Fairness analysis calculates Gini coefficient, gaps, and variance."""
    calculator = WorkloadCalculator()
    analytics = WorkloadAnalytics(calculator)

    rule = TeacherWorkloadRuleExtended(teacher_id="t1", max_periods_per_week=20)

    # Teacher 1 has 10 periods
    sessions_t1 = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=p,
            duration_periods=1,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
        for p in range(5)
    ]
    s1 = calculator.calculate_teacher_workload("t1", "Teacher 1", sessions_t1, rule, institution)

    # Teacher 2 has 10 periods (equal load)
    sessions_t2 = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s2",
            day_of_week=1,
            start_period=p,
            duration_periods=1,
            room_id="r1",
            teacher_id="t2",
            class_group_id="c1",
        )
        for p in range(5)
    ]
    s2 = calculator.calculate_teacher_workload("t2", "Teacher 2", sessions_t2, rule, institution)

    all_sessions = sessions_t1 + sessions_t2
    metrics = analytics.analyze_fairness([s1, s2], all_sessions, institution)

    assert metrics.workload_spread_periods == 0
    assert metrics.assigned_workload_variance == 0.0
    assert metrics.gini_coefficient == 0.0
    assert metrics.is_equitably_distributed is True
