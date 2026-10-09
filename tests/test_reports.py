"""Automated test suite for academic workload, room utilization, and conflict reporting."""

import tempfile
from pathlib import Path
import pytest

from core.models import (
    ConstraintType,
    ConstraintViolation,
    Institution,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingResult,
    SchedulingStatus,
    SessionType,
    Teacher,
    TeacherWorkloadRule,
    Timetable,
)
from exchange.models import ExportFormat
from exchange.report_service import ReportServiceImpl
from exchange.reports import (
    ConflictReportGenerator,
    RoomUtilizationReportGenerator,
    TimetableSummaryReportGenerator,
    WorkloadReportGenerator,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_institution():
    return Institution(
        name="Institute of Technology",
        code="IOT",
        working_days=[0, 1, 2, 3, 4],  # 5 days
        periods_per_day=6,              # 6 periods/day = 30 total
        period_duration_minutes=60,
    )


# ---------------------------------------------------------------------------
# Workload Report Tests
# ---------------------------------------------------------------------------


def test_workload_calculation_and_capacity(sample_institution):
    t1 = Teacher(id="t-1", name="Alan Turing", employee_id="T101", department_id="dept-cs")
    t2 = Teacher(id="t-2", name="Ada Lovelace", employee_id="T102", department_id="dept-cs")

    sessions = [
        # T1 has 3 periods on Monday (0, 1, 2) -> consecutive = 3
        ScheduledSession(id="s1", timetable_id="tt", class_subject_assignment_id="a", day_of_week=0, start_period=0, duration_periods=1, room_id="r1", teacher_id="t-1", class_group_id="c1"),
        ScheduledSession(id="s2", timetable_id="tt", class_subject_assignment_id="a", day_of_week=0, start_period=1, duration_periods=1, room_id="r1", teacher_id="t-1", class_group_id="c1"),
        ScheduledSession(id="s3", timetable_id="tt", class_subject_assignment_id="a", day_of_week=0, start_period=2, duration_periods=1, room_id="r1", teacher_id="t-1", class_group_id="c1"),
        # T2 has 1 period on Tuesday
        ScheduledSession(id="s4", timetable_id="tt", class_subject_assignment_id="a", day_of_week=1, start_period=3, duration_periods=1, room_id="r1", teacher_id="t-2", class_group_id="c1"),
    ]

    rules = {
        "t-1": TeacherWorkloadRule(teacher_id="t-1", max_periods_per_week=10, min_periods_per_week=2, max_periods_per_day=4, max_consecutive_periods=2),
        # T2 has no rule
    }

    report = WorkloadReportGenerator.generate_report(
        teachers=[t1, t2],
        sessions=sessions,
        rules=rules,
        institution=sample_institution,
    )

    assert len(report) == 2

    # T1 evaluation
    r_t1 = next(r for r in report if r.teacher_id == "t-1")
    assert r_t1.assigned_periods == 3
    assert r_t1.assigned_contact_hours == 3.0
    assert r_t1.remaining_capacity == 7  # 10 - 3
    assert r_t1.max_consecutive_observed == 3
    assert r_t1.is_overloaded is False
    assert r_t1.is_underloaded is False
    assert r_t1.has_workload_rule is True
    # Consecutive violation flagged in warning message
    assert "consecutive" in r_t1.warning_message.lower()

    # T2 evaluation (no rule)
    r_t2 = next(r for r in report if r.teacher_id == "t-2")
    assert r_t2.assigned_periods == 1
    assert r_t2.has_workload_rule is False
    assert "no specific workload rule" in r_t2.warning_message.lower()


def test_workload_overload_and_underload(sample_institution):
    t_over = Teacher(id="t-over", name="Overloaded", employee_id="T_OV", department_id="dept-cs")
    t_under = Teacher(id="t-under", name="Underloaded", employee_id="T_UN", department_id="dept-cs")

    sessions = [
        # 12 periods assigned to t_over
        ScheduledSession(id=f"s{i}", timetable_id="tt", class_subject_assignment_id="a", day_of_week=i % 5, start_period=i % 4, duration_periods=1, room_id="r1", teacher_id="t-over", class_group_id="c1")
        for i in range(12)
    ]

    rules = {
        "t-over": TeacherWorkloadRule(teacher_id="t-over", max_periods_per_week=10, min_periods_per_week=0),
        "t-under": TeacherWorkloadRule(teacher_id="t-under", max_periods_per_week=20, min_periods_per_week=8),
    }

    report = WorkloadReportGenerator.generate_report(
        teachers=[t_over, t_under],
        sessions=sessions,
        rules=rules,
        institution=sample_institution,
    )

    r_over = next(r for r in report if r.teacher_id == "t-over")
    assert r_over.is_overloaded is True
    assert r_over.assigned_periods == 12

    r_under = next(r for r in report if r.teacher_id == "t-under")
    assert r_under.is_underloaded is True
    assert r_under.assigned_periods == 0


def test_workload_department_filter(sample_institution):
    t1 = Teacher(id="t-1", name="CS Teacher", employee_id="T1", department_id="dept-cs")
    t2 = Teacher(id="t-2", name="Math Teacher", employee_id="T2", department_id="dept-math")

    report = WorkloadReportGenerator.generate_report(
        teachers=[t1, t2],
        sessions=[],
        institution=sample_institution,
        department_filter="dept-cs",
    )
    assert len(report) == 1
    assert report[0].teacher_id == "t-1"


# ---------------------------------------------------------------------------
# Room Utilization Tests
# ---------------------------------------------------------------------------


def test_room_utilization_rate_calculation(sample_institution):
    r1 = Room(id="r-1", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=50)
    r_lab = Room(id="r-lab", name="Computer Lab", code="LAB1", room_type=RoomType.COMPUTER_LAB, capacity=30)

    # 30 total periods in standard 5x6 grid.
    # r1 occupied for 15 periods -> 50% utilization
    sessions = [
        ScheduledSession(id=f"s{i}", timetable_id="tt", class_subject_assignment_id="a", day_of_week=i % 5, start_period=i % 6, duration_periods=1, room_id="r-1", teacher_id="t1", class_group_id="c1")
        for i in range(15)
    ]

    report = RoomUtilizationReportGenerator.generate_report(
        rooms=[r1, r_lab],
        sessions=sessions,
        institution=sample_institution,
    )

    assert len(report) == 2
    rep_r1 = next(r for r in report if r.room_id == "r-1")
    assert rep_r1.occupied_periods == 15
    assert rep_r1.available_periods == 30
    assert rep_r1.utilization_rate == 50.0

    rep_lab = next(r for r in report if r.room_id == "r-lab")
    assert rep_lab.occupied_periods == 0
    assert rep_lab.utilization_rate == 0.0
    # Specialist facility note
    assert "specialist" in rep_lab.notes.lower()


def test_room_zero_availability_division_by_zero_safety():
    # Inst with 0 periods or blocked room
    room = Room(id="r-blocked", name="Maintenance Room", code="R_BLK", room_type=RoomType.LECTURE_HALL, capacity=40)
    # 30 unavailable slots out of 30 total
    unavail_slots = {(d, p) for d in range(5) for p in range(6)}

    report = RoomUtilizationReportGenerator.generate_report(
        rooms=[room],
        sessions=[],
        institution=Institution(name="Inst", code="I", working_days=[0, 1, 2, 3, 4], periods_per_day=6),
        room_availabilities={"r-blocked": unavail_slots},
    )

    assert len(report) == 1
    assert report[0].available_periods == 0
    assert report[0].utilization_rate == 0.0
    assert "zero available periods" in report[0].notes.lower()


# ---------------------------------------------------------------------------
# Conflict & Unscheduled Session Reports Tests
# ---------------------------------------------------------------------------


def test_conflict_report_hard_vs_soft_violations():
    violations = [
        ConstraintViolation(
            violation_type=ConstraintType.TEACHER_DOUBLE_BOOKING,
            is_hard=True,
            severity="ERROR",
            message="Teacher T1 double-booked Monday Period 1",
            involved_teachers=["t1"],
        ),
        ConstraintViolation(
            violation_type=ConstraintType.TEACHER_CONSECUTIVE_LIMIT,
            is_hard=False,
            severity="WARNING",
            message="Teacher T1 exceeds consecutive period preference",
            involved_teachers=["t1"],
        ),
    ]

    report = ConflictReportGenerator.generate_conflict_report(violations=violations)
    assert len(report) == 2
    assert report[0].is_hard is True
    assert report[0].severity == "ERROR"
    assert "Reschedule" in report[0].remediation_suggestion

    assert report[1].is_hard is False
    assert report[1].severity == "WARNING"


def test_conflict_report_solver_infeasible_outcome():
    infeasible_result = SchedulingResult(
        status=SchedulingStatus.INFEASIBLE,
        message="Contradictory constraints prevent solution.",
    )
    report = ConflictReportGenerator.generate_conflict_report(result=infeasible_result)
    assert len(report) == 1
    assert report[0].violation_type == "SOLVER_PROVEN_INFEASIBLE"
    assert report[0].is_hard is True


def test_unscheduled_sessions_report():
    unit1 = SchedulableUnit(unit_id="u1", assignment_id="a1", class_group_id="c1", subject_id="s1", teacher_id="t1", session_type=SessionType.THEORY, duration_periods=1)
    unit2 = SchedulableUnit(unit_id="u2", assignment_id="a2", class_group_id="c1", subject_id="s2", teacher_id="t2", session_type=SessionType.THEORY, duration_periods=1)

    # Only unit1 placed
    session1 = ScheduledSession(id="u1", timetable_id="tt", class_subject_assignment_id="a1", day_of_week=0, start_period=0, duration_periods=1, room_id="r1", teacher_id="t1", class_group_id="c1")

    meta = {
        "sub_code_map": {"s2": "CS202"},
        "sub_name_map": {"s2": "Database Systems"},
        "class_name_map": {"c1": "CS-3A"},
        "teacher_name_map": {"t2": "Dr. Codd"},
    }

    report = ConflictReportGenerator.generate_unscheduled_report(
        required_units=[unit1, unit2],
        scheduled_sessions=[session1],
        metadata=meta,
    )

    assert len(report) == 1
    assert report[0].subject_code == "CS202"
    assert report[0].class_name == "CS-3A"
    assert report[0].teacher_name == "Dr. Codd"
    assert report[0].missing_count == 1


# ---------------------------------------------------------------------------
# Timetable Summary Report Tests
# ---------------------------------------------------------------------------


def test_timetable_summary_report():
    tt = Timetable(id="tt-01", name="Fall 2026", academic_year_id="2026", semester_id="S1", is_published=True)
    sessions = [
        ScheduledSession(id="s1", timetable_id="tt-01", class_subject_assignment_id="a1", day_of_week=0, start_period=0, duration_periods=2, room_id="r1", teacher_id="t1", class_group_id="c1"),
        ScheduledSession(id="s2", timetable_id="tt-01", class_subject_assignment_id="a2", day_of_week=1, start_period=0, duration_periods=1, room_id="r2", teacher_id="t2", class_group_id="c2"),
    ]

    summary = TimetableSummaryReportGenerator.generate_summary(
        timetable=tt,
        sessions=sessions,
        violations=[],
        unscheduled_count=0,
    )

    assert summary.timetable_id == "tt-01"
    assert summary.status == "PUBLISHED"
    assert summary.total_classes == 2
    assert summary.total_teachers == 2
    assert summary.total_rooms == 2
    assert summary.total_sessions == 2
    assert summary.total_periods_placed == 3
    assert summary.total_hours_scheduled == 3.0
    assert summary.is_valid is True


# ---------------------------------------------------------------------------
# Report Service Integration Tests
# ---------------------------------------------------------------------------


def test_report_service_generation_protocols(temp_dir, sample_institution):
    t = Teacher(id="t1", name="Alan", employee_id="T1", department_id="dept-1")
    r = Room(id="r1", name="Hall", code="R1", room_type=RoomType.LECTURE_HALL, capacity=50)
    sess = [
        ScheduledSession(id="s1", timetable_id="tt", class_subject_assignment_id="a", day_of_week=0, start_period=0, duration_periods=1, room_id="r1", teacher_id="t1", class_group_id="c1")
    ]

    service = ReportServiceImpl(
        context={
            "teachers": [t],
            "rooms": [r],
            "sessions": sess,
            "institution": sample_institution,
        }
    )

    # Test protocol method generate_workload_report
    w_path = service.generate_workload_report("tt")
    assert Path(w_path).exists()
    assert Path(w_path).suffix == ".xlsx"

    # Test protocol method generate_room_utilization_report
    r_path = service.generate_room_utilization_report("tt")
    assert Path(r_path).exists()
    assert Path(r_path).suffix == ".xlsx"

    # Test export_report in CSV format
    csv_dest = temp_dir / "workload.csv"
    res = service.export_report("WORKLOAD", "tt", str(csv_dest), format=ExportFormat.CSV)
    assert res.success is True
    assert csv_dest.exists()
