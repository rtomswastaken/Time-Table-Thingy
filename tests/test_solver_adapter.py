"""Tests for solver adapter interface contract with Agent 5."""

import pytest
from core.models import Institution, ScheduledSession, Teacher
from workload.availability import AvailabilityManager
from workload.models import DetailedTeacherPreference, SoftPreferenceType
from workload.preferences import PreferenceManager
from workload.rules import WorkloadRuleManager
from workload.solver_adapter import SolverWorkloadAdapter


@pytest.fixture
def institution():
    return Institution(
        name="Tech University",
        code="TU",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        period_duration_minutes=60,
    )


def test_solver_adapter_exports(institution):
    """Adapter exports exact dictionaries expected by SchedulingInputBundle."""
    avail_mgr = AvailabilityManager()
    avail_mgr.mark_slot_unavailable("t1", day_of_week=0, period_index=0)

    rule_mgr = WorkloadRuleManager()
    rule_mgr.apply_profile_to_teacher("t1", "part_time_half")

    pref_mgr = PreferenceManager()
    pref_mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=8,
        )
    )

    adapter = SolverWorkloadAdapter(avail_mgr, rule_mgr, pref_mgr)

    teachers = [Teacher(department_id="d1", name="Dr. Ada", employee_id="E1", id="t1")]

    # 1. Export teacher_availability
    avail_export = adapter.export_solver_availability(teachers, institution)
    assert "t1" in avail_export
    assert (0, 0) in avail_export["t1"]

    # 2. Export teacher_workload_rules
    rules_export = adapter.export_solver_workload_rules(teachers)
    assert "t1" in rules_export
    assert rules_export["t1"].max_periods_per_week == 10  # from part_time_half

    # 3. Export teacher_preferences
    prefs_export = adapter.export_solver_preferences(teachers, institution)
    assert "t1" in prefs_export
    assert (0, 0) in prefs_export["t1"]
    assert prefs_export["t1"][(0, 0)] > 0  # Morning preferred


def test_solver_post_solve_evaluation(institution):
    """Adapter evaluates completed schedule and computes penalty score for solver."""
    avail_mgr = AvailabilityManager()
    rule_mgr = WorkloadRuleManager()
    pref_mgr = PreferenceManager()

    pref_mgr.add_preference(
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.AVOID_FINAL_PERIOD,
            weight=10,
        )
    )

    adapter = SolverWorkloadAdapter(avail_mgr, rule_mgr, pref_mgr)
    teachers = [Teacher(department_id="d1", name="Dr. Ada", employee_id="E1", id="t1")]

    # Session in final period
    sessions = [
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

    penalty = adapter.compute_total_penalty_score(teachers, sessions, institution)
    assert penalty > 0.0

    eval_reports = adapter.evaluate_timetable_preferences(teachers, sessions, institution)
    assert "t1" in eval_reports
    assert eval_reports["t1"].satisfaction_rate < 1.0
