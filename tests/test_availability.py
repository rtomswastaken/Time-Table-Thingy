"""Tests for teacher availability management, restrictions, and exceptions."""

import pytest
from core.exceptions import ValidationError
from core.models import Institution
from workload.availability import AvailabilityManager
from workload.models import AvailabilityException


@pytest.fixture
def institution():
    return Institution(
        name="Test University",
        code="TU",
        working_days=[0, 1, 2, 3, 4],  # Mon-Fri
        periods_per_day=6,
        period_duration_minutes=60,
    )


def test_default_availability(institution):
    """By default with no restrictions, all slots in working days are available."""
    mgr = AvailabilityManager()
    avail = mgr.get_available_slots("t1", institution)
    assert len(avail) == 5 * 6  # 30 slots
    assert mgr.is_available("t1", 0, 0, institution) is True


def test_mark_specific_slot_unavailable(institution):
    """A teacher can be marked unavailable for a specific slot."""
    mgr = AvailabilityManager()
    mgr.mark_slot_unavailable("t1", day_of_week=0, period_index=1)

    assert mgr.is_available("t1", 0, 1, institution) is False
    assert mgr.is_available("t1", 0, 0, institution) is True
    assert (0, 1) in mgr.get_unavailable_slots("t1", institution)


def test_mark_entire_day_unavailable(institution):
    """An entire day can be marked unavailable (e.g. Wednesday day off)."""
    mgr = AvailabilityManager()
    mgr.mark_day_unavailable("t1", day_of_week=2, periods_per_day=institution.periods_per_day)

    for p in range(6):
        assert mgr.is_available("t1", 2, p, institution) is False

    # Other days remain available
    assert mgr.is_available("t1", 0, 0, institution) is True


def test_working_hour_bounds(institution):
    """Teachers can be restricted to specific working periods (e.g. only periods 1 to 4)."""
    mgr = AvailabilityManager()
    mgr.set_working_hour_bounds(
        teacher_id="t1",
        earliest_period=1,
        latest_period=4,
        periods_per_day=institution.periods_per_day,
    )

    # Periods 0 and 5 should be unavailable on all working days
    assert mgr.is_available("t1", 0, 0, institution) is False
    assert mgr.is_available("t1", 0, 5, institution) is False

    # Periods 1..4 should be available
    assert mgr.is_available("t1", 0, 1, institution) is True
    assert mgr.is_available("t1", 0, 4, institution) is True


def test_invalid_working_hour_bounds():
    """Invalid period bounds raise ValidationError."""
    mgr = AvailabilityManager()
    with pytest.raises(ValidationError):
        mgr.set_working_hour_bounds("t1", earliest_period=5, latest_period=2, periods_per_day=6)

    with pytest.raises(ValidationError):
        mgr.set_working_hour_bounds("t1", earliest_period=-1, latest_period=4, periods_per_day=6)


def test_availability_exceptions(institution):
    """Explicit exceptions can override recurring unavailability or vice versa."""
    mgr = AvailabilityManager()
    # Mark whole Tuesday unavailable
    mgr.mark_day_unavailable("t1", day_of_week=1, periods_per_day=6)

    # Add exception: available specifically on Tuesday Period 2 for a faculty meeting/class
    mgr.add_exception(
        AvailabilityException(
            teacher_id="t1",
            day_of_week=1,
            period_index=2,
            is_available=True,
            reason="Special guest lecture slot",
        )
    )

    assert mgr.is_available("t1", 1, 0, institution) is False
    assert mgr.is_available("t1", 1, 2, institution) is True


def test_conversion_to_core_availabilities(institution):
    """Availability manager correctly converts matrix to list of CoreTeacherAvailability."""
    mgr = AvailabilityManager()
    mgr.mark_slot_unavailable("t1", 0, 0)

    records = mgr.to_core_availabilities("t1", institution)
    assert len(records) == 30

    slot_0_0 = next(r for r in records if r.day_of_week == 0 and r.period_index == 0)
    assert slot_0_0.is_available is False

    slot_0_1 = next(r for r in records if r.day_of_week == 0 and r.period_index == 1)
    assert slot_0_1.is_available is True
