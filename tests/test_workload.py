"""End-to-end tests for Workload Engine and forwarders."""

import pytest
from workload.service import WorkloadServiceImpl
from core.interfaces import WorkloadService
from core.models import Institution, Teacher, ScheduledSession


def test_workload_end_to_end():
    institution = Institution(
        name="Institute of Technology",
        code="IOT",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        period_duration_minutes=60,
    )
    t = Teacher(department_id="d1", name="Dr. Dijkstra", employee_id="E-DIJK", id="t-dijk")
    service = WorkloadServiceImpl(institution=institution, teachers=[t])

    # Assert protocol conformance
    assert isinstance(service, WorkloadService)

    # Configure limits
    rule = service.get_workload_rule("t-dijk")
    rule.max_periods_per_week = 18
    rule.min_periods_per_week = 6
    service.set_workload_rule(rule)

    # Set availability
    service.set_availability("t-dijk", {(0, 0), (0, 1)})
    assert (0, 0) in service.get_availability("t-dijk")

    # Set preferences
    service.set_preferences("t-dijk", {(1, 2): 8})
    assert service.get_preferences("t-dijk")[(1, 2)] == 8

    # Calculate workload with sessions
    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="csa-1",
            day_of_week=1,
            start_period=2,
            duration_periods=2,
            room_id="r-101",
            teacher_id="t-dijk",
            class_group_id="cg-1",
        )
    ]
    summary = service.calculate_faculty_workload("t-dijk", sessions, institution)

    assert summary.assigned_periods_per_week == 2
    assert summary.assigned_contact_hours_per_week == 2.0
    assert summary.remaining_capacity_periods == 16
    assert summary.is_underloaded is True  # 2 < 6 min
    assert summary.is_overloaded is False
