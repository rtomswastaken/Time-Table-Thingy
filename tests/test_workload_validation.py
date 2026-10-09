"""Tests for workload, availability, and preference validation rules."""

import pytest
from core.exceptions import ValidationError
from core.models import Institution
from workload.models import (
    DetailedTeacherPreference,
    SoftPreferenceType,
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
)
from workload.validation import WorkloadValidator


@pytest.fixture
def institution():
    return Institution(
        name="Tech",
        code="T",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
    )


def test_validate_slot_out_of_bounds(institution):
    """Slots outside working days or period range fail validation."""
    # Valid
    WorkloadValidator.validate_slot(0, 0, institution.working_days, institution.periods_per_day)

    # Invalid day (Sunday = 6 when working days are Mon-Fri)
    with pytest.raises(ValidationError, match="Invalid day_of_week"):
        WorkloadValidator.validate_slot(6, 0, institution.working_days, institution.periods_per_day)

    # Invalid period (Period 6 when periods_per_day is 6, indices 0..5)
    with pytest.raises(ValidationError, match="Invalid period_index"):
        WorkloadValidator.validate_slot(0, 6, institution.working_days, institution.periods_per_day)


def test_validate_workload_rule_bounds():
    """Rules with negative limits or min > max raise ValidationError."""
    rule_valid = TeacherWorkloadRuleExtended(
        teacher_id="t1",
        max_periods_per_week=20,
        min_periods_per_week=10,
        max_periods_per_day=5,
        min_periods_per_day=1,
        max_consecutive_periods=3,
    )
    WorkloadValidator.validate_workload_rule(rule_valid)

    # Missing teacher_id
    with pytest.raises(ValidationError, match="teacher_id"):
        rule_invalid = TeacherWorkloadRuleExtended(teacher_id="  ")
        WorkloadValidator.validate_workload_rule(rule_invalid)


def test_validate_preference_weights():
    """Preference weights strictly enforce bounds."""
    # Valid 1..10
    WorkloadValidator.validate_preference_weight(1)
    WorkloadValidator.validate_preference_weight(10)

    with pytest.raises(ValidationError):
        WorkloadValidator.validate_preference_weight(0)

    with pytest.raises(ValidationError):
        WorkloadValidator.validate_preference_weight(11)

    # Slot weights -10..+10
    WorkloadValidator.validate_slot_weight(-10)
    WorkloadValidator.validate_slot_weight(10)

    with pytest.raises(ValidationError):
        WorkloadValidator.validate_slot_weight(-11)

    with pytest.raises(ValidationError):
        WorkloadValidator.validate_slot_weight(11)


def test_validate_preference_with_invalid_day(institution):
    """Soft preference with target day outside institution calendar fails."""
    pref = DetailedTeacherPreference(
        teacher_id="t1",
        preference_type=SoftPreferenceType.PREFER_DAYS,
        target_value=[6],  # Sunday
        weight=5,
    )
    with pytest.raises(ValidationError, match="not in institution working days"):
        WorkloadValidator.validate_preference(pref, institution)


def test_validate_profile_empty_name():
    """WorkloadProfile requires a non-empty name."""
    with pytest.raises(ValidationError):
        profile = WorkloadProfile(id="p1", name="", max_periods_per_week=20, min_periods_per_week=0)
        WorkloadValidator.validate_profile(profile)
