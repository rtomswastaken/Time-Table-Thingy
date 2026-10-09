"""Tests for workload and preference persistence in SQLite and memory."""

import sqlite3
import pytest
from workload.models import (
    DetailedTeacherPreference,
    SoftPreferenceType,
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
)
from workload.repository import InMemoryWorkloadRepository, WorkloadRepository


@pytest.fixture
def sqlite_repo():
    conn = sqlite3.connect(":memory:")
    return WorkloadRepository(conn)


@pytest.fixture
def in_memory_repo():
    return InMemoryWorkloadRepository()


@pytest.mark.parametrize("repo_fixture", ["sqlite_repo", "in_memory_repo"])
def test_availability_persistence(repo_fixture, request):
    """Availability slots are persisted and queried correctly."""
    repo = request.getfixturevalue(repo_fixture)
    slots = {(0, 1), (0, 2), (2, 4)}

    repo.save_unavailable_slots("t1", slots)
    loaded = repo.get_unavailable_slots("t1")
    assert loaded == slots

    # Overwriting with empty set
    repo.save_unavailable_slots("t1", set())
    assert repo.get_unavailable_slots("t1") == set()


@pytest.mark.parametrize("repo_fixture", ["sqlite_repo", "in_memory_repo"])
def test_slot_weights_persistence(repo_fixture, request):
    """Slot weights are persisted and queried correctly."""
    repo = request.getfixturevalue(repo_fixture)
    weights = {(0, 0): 5, (1, 5): -10}

    repo.save_slot_weights("t1", weights)
    loaded = repo.get_slot_weights("t1")
    assert loaded == weights


@pytest.mark.parametrize("repo_fixture", ["sqlite_repo", "in_memory_repo"])
def test_soft_preferences_persistence(repo_fixture, request):
    """Detailed soft preferences are persisted and restored."""
    repo = request.getfixturevalue(repo_fixture)
    prefs = [
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.PREFER_MORNING,
            weight=9,
            is_active=True,
            description="Morning classes preferred",
        ),
        DetailedTeacherPreference(
            teacher_id="t1",
            preference_type=SoftPreferenceType.MINIMIZE_WORKING_DAYS,
            weight=6,
            target_value=3,
        ),
    ]

    repo.save_soft_preferences("t1", prefs)
    loaded = repo.get_soft_preferences("t1")
    assert len(loaded) == 2

    morning_pref = next(p for p in loaded if p.preference_type == SoftPreferenceType.PREFER_MORNING)
    assert morning_pref.weight == 9
    assert morning_pref.description == "Morning classes preferred"


@pytest.mark.parametrize("repo_fixture", ["sqlite_repo", "in_memory_repo"])
def test_workload_rules_and_profiles_persistence(repo_fixture, request):
    """Workload rules and reusable profiles are persisted."""
    repo = request.getfixturevalue(repo_fixture)

    profile = WorkloadProfile(
        id="profile_custom",
        name="Custom 75% Load",
        max_periods_per_week=15,
        min_periods_per_week=8,
        max_periods_per_day=4,
    )
    repo.save_profile(profile)
    loaded_profile = repo.get_profile("profile_custom")
    assert loaded_profile is not None
    assert loaded_profile.max_periods_per_week == 15

    rule = TeacherWorkloadRuleExtended(
        teacher_id="t1",
        max_periods_per_week=14,
        min_periods_per_week=6,
        max_periods_per_day=4,
        max_consecutive_periods=2,
        profile_id="profile_custom",
    )
    repo.save_workload_rule(rule)
    loaded_rule = repo.get_workload_rule("t1")
    assert loaded_rule is not None
    assert loaded_rule.max_periods_per_week == 14
    assert loaded_rule.profile_id == "profile_custom"
