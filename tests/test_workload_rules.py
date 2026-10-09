"""Tests for workload rules, profile management, and limit inheritance."""

import pytest
from core.exceptions import EntityNotFoundError, ValidationError
from workload.models import TeacherWorkloadRuleExtended, WorkloadProfile
from workload.rules import WorkloadRuleManager


def test_standard_profiles_registration():
    """Default institutional profiles are pre-registered and accessible."""
    mgr = WorkloadRuleManager()
    profiles = mgr.list_profiles()
    assert len(profiles) >= 4

    ft = mgr.get_profile("full_time_standard")
    assert ft.max_periods_per_week == 20
    assert ft.min_periods_per_week == 12

    pt = mgr.get_profile("part_time_half")
    assert pt.max_periods_per_week == 10


def test_apply_profile_to_teacher():
    """Applying a profile generates matching teacher rules."""
    mgr = WorkloadRuleManager()
    rule = mgr.apply_profile_to_teacher("t1", "part_time_half")

    assert rule.teacher_id == "t1"
    assert rule.max_periods_per_week == 10
    assert rule.min_periods_per_week == 6
    assert rule.profile_id == "part_time_half"

    # Rule is stored and retrievable
    retrieved = mgr.get_rule_for_teacher("t1")
    assert retrieved.max_periods_per_week == 10


def test_custom_rule_creation_and_conversion():
    """Custom teacher rules can be registered and converted to core model."""
    mgr = WorkloadRuleManager()
    custom_rule = TeacherWorkloadRuleExtended(
        teacher_id="t2",
        max_periods_per_week=16,
        min_periods_per_week=8,
        max_periods_per_day=4,
        max_consecutive_periods=2,
    )
    mgr.create_or_update_rule(custom_rule)

    rule = mgr.get_rule_for_teacher("t2")
    assert rule.max_periods_per_week == 16

    core_rule = rule.to_core_rule()
    assert core_rule.teacher_id == "t2"
    assert core_rule.max_periods_per_week == 16
    assert core_rule.max_consecutive_periods == 2


def test_rule_validation_bounds():
    """Rules validate bounds on creation."""
    with pytest.raises(ValidationError):
        TeacherWorkloadRuleExtended(teacher_id="t1", max_periods_per_week=10, min_periods_per_week=15)

    with pytest.raises(ValidationError):
        TeacherWorkloadRuleExtended(teacher_id="t1", min_periods_per_week=-1)

    with pytest.raises(ValidationError):
        TeacherWorkloadRuleExtended(teacher_id="t1", max_periods_per_day=0)


def test_profile_not_found():
    """Requesting an unknown profile raises EntityNotFoundError."""
    mgr = WorkloadRuleManager()
    with pytest.raises(EntityNotFoundError):
        mgr.get_profile("non_existent_profile")
