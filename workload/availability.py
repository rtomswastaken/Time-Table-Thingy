"""Teacher Availability Management.

Handles mandatory hard availability restrictions (unavailable days, unavailable
time slots, restricted periods, working-hour bounds, and slot exceptions).
Guarantees that unavailable slots are treated as non-negotiable hard constraints.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from core.models import Institution, TeacherAvailability as CoreTeacherAvailability
from workload.models import AvailabilityException


class AvailabilityManager:
    """Manages teacher availability matrices, hard restrictions, and exceptions."""

    def __init__(self) -> None:
        # teacher_id -> set of (day_of_week, period_index) that are UNCONDITIONALLY UNAVAILABLE
        self._unavailable_slots: Dict[str, Set[Tuple[int, int]]] = {}
        # teacher_id -> list of AvailabilityException
        self._exceptions: Dict[str, List[AvailabilityException]] = {}
        # teacher_id -> (earliest_start_period, latest_end_period) bounds
        self._working_hour_bounds: Dict[str, Tuple[int, int]] = {}

    def set_unavailable_slots(
        self, teacher_id: str, unavailable_slots: Set[Tuple[int, int]]
    ) -> None:
        """Sets the exact set of unavailable (day, period) slots for a teacher."""
        self._unavailable_slots[teacher_id] = set(unavailable_slots)

    def mark_slot_unavailable(self, teacher_id: str, day_of_week: int, period_index: int) -> None:
        """Marks a single recurring slot as unavailable (hard restriction)."""
        if teacher_id not in self._unavailable_slots:
            self._unavailable_slots[teacher_id] = set()
        self._unavailable_slots[teacher_id].add((day_of_week, period_index))

    def mark_slot_available(self, teacher_id: str, day_of_week: int, period_index: int) -> None:
        """Removes an unavailable restriction from a single slot."""
        if teacher_id in self._unavailable_slots:
            self._unavailable_slots[teacher_id].discard((day_of_week, period_index))

    def mark_day_unavailable(
        self, teacher_id: str, day_of_week: int, periods_per_day: int
    ) -> None:
        """Marks an entire day as unavailable across all period indices."""
        if teacher_id not in self._unavailable_slots:
            self._unavailable_slots[teacher_id] = set()
        for p in range(periods_per_day):
            self._unavailable_slots[teacher_id].add((day_of_week, p))

    def mark_day_available(
        self, teacher_id: str, day_of_week: int, periods_per_day: int
    ) -> None:
        """Restores an entire day as available."""
        if teacher_id in self._unavailable_slots:
            for p in range(periods_per_day):
                self._unavailable_slots[teacher_id].discard((day_of_week, p))

    def set_working_hour_bounds(
        self, teacher_id: str, earliest_period: int, latest_period: int, periods_per_day: int
    ) -> None:
        """Restricts teacher's teaching hours to between earliest_period and latest_period (inclusive).

        All periods outside this range are automatically marked as unavailable across all working days.
        """
        if earliest_period < 0 or latest_period >= periods_per_day or earliest_period > latest_period:
            raise ValidationError(
                f"Invalid period bounds [{earliest_period}, {latest_period}] for {periods_per_day} periods."
            )
        self._working_hour_bounds[teacher_id] = (earliest_period, latest_period)

    def add_exception(self, exception: AvailabilityException) -> None:
        """Adds a specific availability exception or temporary override."""
        if exception.teacher_id not in self._exceptions:
            self._exceptions[exception.teacher_id] = []
        self._exceptions[exception.teacher_id].append(exception)

    def get_unavailable_slots(
        self, teacher_id: str, institution: Optional[Institution] = None
    ) -> Set[Tuple[int, int]]:
        """Computes the complete, authoritative set of unavailable (day, period) slots.

        Takes into account direct slot restrictions, working-hour boundaries, and exceptions.
        """
        result = set(self._unavailable_slots.get(teacher_id, set()))

        # Apply working-hour boundaries if configured
        if teacher_id in self._working_hour_bounds and institution is not None:
            earliest, latest = self._working_hour_bounds[teacher_id]
            for day in institution.working_days:
                for p in range(institution.periods_per_day):
                    if p < earliest or p > latest:
                        result.add((day, p))

        # Apply explicit exceptions
        for exc in self._exceptions.get(teacher_id, []):
            if exc.is_available:
                result.discard((exc.day_of_week, exc.period_index))
            else:
                result.add((exc.day_of_week, exc.period_index))

        return result

    def is_available(
        self,
        teacher_id: str,
        day_of_week: int,
        period_index: int,
        institution: Optional[Institution] = None,
    ) -> bool:
        """Quickly queries whether a teacher is available at a given day and period slot."""
        unavailable = self.get_unavailable_slots(teacher_id, institution)
        return (day_of_week, period_index) not in unavailable

    def get_available_slots(
        self, teacher_id: str, institution: Institution
    ) -> Set[Tuple[int, int]]:
        """Returns all permitted teaching slots for a teacher within an institution's calendar."""
        unavailable = self.get_unavailable_slots(teacher_id, institution)
        available = set()
        for day in institution.working_days:
            for p in range(institution.periods_per_day):
                if (day, p) not in unavailable:
                    available.add((day, p))
        return available

    def to_core_availabilities(
        self, teacher_id: str, institution: Institution
    ) -> List[CoreTeacherAvailability]:
        """Converts internal matrix into a list of CoreTeacherAvailability entities."""
        unavailable = self.get_unavailable_slots(teacher_id, institution)
        records = []
        for day in institution.working_days:
            for p in range(institution.periods_per_day):
                records.append(
                    CoreTeacherAvailability(
                        teacher_id=teacher_id,
                        day_of_week=day,
                        period_index=p,
                        is_available=((day, p) not in unavailable),
                    )
                )
        return records

    def clear(self, teacher_id: Optional[str] = None) -> None:
        """Clears availability configuration."""
        if teacher_id:
            self._unavailable_slots.pop(teacher_id, None)
            self._exceptions.pop(teacher_id, None)
            self._working_hour_bounds.pop(teacher_id, None)
        else:
            self._unavailable_slots.clear()
            self._exceptions.clear()
            self._working_hour_bounds.clear()
