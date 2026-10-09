"""Tests for WorkloadService implementing core.interfaces.WorkloadService."""

import pytest
from core.interfaces import FacultyWorkloadSummary, WorkloadService
from core.models import Institution, ScheduledSession, Teacher
from workload.models import DetailedTeacherPreference, SoftPreferenceType
from workload.repository import InMemoryWorkloadRepository
from workload.service import WorkloadServiceImpl


class MockTimetableRepo:
    def __init__(self, sessions):
        self.sessions = sessions

    def get_sessions(self, timetable_id: str):
        return self.sessions


@pytest.fixture
def institution():
    return Institution(
        name="Metropolitan University",
        code="METRO",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        period_duration_minutes=60,
    )


def test_workload_service_protocol_conformance(institution):
    """WorkloadServiceImpl strictly satisfies core.interfaces.WorkloadService protocol."""
    service = WorkloadServiceImpl(institution=institution)
    assert isinstance(service, WorkloadService)


def test_calculate_faculty_workload(institution):
    """WorkloadService calculates faculty workload conforming to FacultyWorkloadSummary."""
    service = WorkloadServiceImpl(institution=institution)
    service.register_teacher(Teacher(department_id="d1", name="Dr. Shannon", employee_id="E10", id="t1"))

    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=0,
            duration_periods=2,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]

    summary = service.calculate_faculty_workload("t1", sessions, institution)
    assert isinstance(summary, FacultyWorkloadSummary)
    assert summary.teacher_id == "t1"
    assert summary.assigned_periods_per_week == 2
    assert summary.assigned_contact_hours_per_week == 2.0
    assert summary.daily_periods[0] == 2
    assert summary.max_consecutive_observed == 2


def test_set_and_get_availability(institution):
    """Setting availability validates and persists slots."""
    service = WorkloadServiceImpl(institution=institution)
    unavailable = {(0, 1), (1, 2)}

    service.set_availability("t1", unavailable)
    loaded = service.get_availability("t1")
    assert loaded == unavailable


def test_set_and_get_preferences(institution):
    """Setting raw preferences validates weights and persists."""
    service = WorkloadServiceImpl(institution=institution)
    prefs = {(0, 0): 5, (2, 5): -5}

    service.set_preferences("t1", prefs)
    loaded = service.get_preferences("t1")
    assert loaded == prefs


def test_calculate_all_workloads_with_repo(institution):
    """calculate_all_workloads queries timetable repo and computes summaries."""
    sessions = [
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
            start_period=1,
            duration_periods=1,
            room_id="r1",
            teacher_id="t2",
            class_group_id="c1",
        ),
    ]

    mock_repo = MockTimetableRepo(sessions)
    teachers = [
        Teacher(department_id="d1", name="T1", employee_id="E1", id="t1"),
        Teacher(department_id="d1", name="T2", employee_id="E2", id="t2"),
    ]
    service = WorkloadServiceImpl(timetable_repo=mock_repo, institution=institution, teachers=teachers)

    all_summaries = service.calculate_all_workloads("tt-1")
    assert len(all_summaries) == 2
    teacher_ids = {s.teacher_id for s in all_summaries}
    assert teacher_ids == {"t1", "t2"}


def test_department_summary_and_fairness(institution):
    """Service generates department summaries and fairness metrics."""
    sessions = [
        ScheduledSession(
            timetable_id="tt-1",
            class_subject_assignment_id="s1",
            day_of_week=0,
            start_period=0,
            duration_periods=2,
            room_id="r1",
            teacher_id="t1",
            class_group_id="c1",
        )
    ]
    mock_repo = MockTimetableRepo(sessions)
    teachers = [
        Teacher(department_id="d1", name="T1", employee_id="E1", id="t1"),
    ]
    service = WorkloadServiceImpl(timetable_repo=mock_repo, institution=institution, teachers=teachers)

    dept_summary = service.get_department_summary("d1", "Computer Science", "tt-1")
    assert dept_summary.department_id == "d1"
    assert dept_summary.total_assigned_periods == 2

    fairness = service.analyze_fairness("tt-1")
    assert fairness.gini_coefficient == 0.0
