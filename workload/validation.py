"""Workload, Availability, and Preference Validation Suite.

Validates configurations before persistence or scheduling, distinguishing between
invalid user inputs and challenging scheduling targets.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from core.models import Institution
from workload.models import (
    DetailedTeacherPreference,
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
)


class WorkloadValidator:
    """Comprehensive validator for workload limits, availability, and preferences."""

    @staticmethod
    def validate_slot(
        day: int,
        period: int,
        working_days: List[int],
        periods_per_day: int,
    ) -> None:
        """Ensures a day and period slot exists within the institution's grid."""
        if day not in working_days:
            raise ValidationError(
                f"Invalid day_of_week {day}. Must be one of configured working days: {working_days}."
            )
        if not 0 <= period < periods_per_day:
            raise ValidationError(
                f"Invalid period_index {period}. Must be between 0 and {periods_per_day - 1}."
            )

    @staticmethod
    def validate_availability_slots(
        slots: Set[Tuple[int, int]],
        working_days: List[int],
        periods_per_day: int,
    ) -> None:
        """Validates all slots in an availability set."""
        for day, period in slots:
            WorkloadValidator.validate_slot(day, period, working_days, periods_per_day)

    @staticmethod
    def validate_workload_rule(rule: TeacherWorkloadRuleExtended) -> None:
        """Validates bounds and logical consistency of a teacher's workload rule."""
        if not rule.teacher_id or not rule.teacher_id.strip():
            raise ValidationError("Workload rule must reference a valid teacher_id.")

        if rule.min_periods_per_week < 0:
            raise ValidationError(
                f"Minimum weekly periods cannot be negative, got {rule.min_periods_per_week}."
            )
        if rule.max_periods_per_week < 0:
            raise ValidationError(
                f"Maximum weekly periods cannot be negative, got {rule.max_periods_per_week}."
            )
        if rule.min_periods_per_week > rule.max_periods_per_week:
            raise ValidationError(
                f"Minimum weekly periods ({rule.min_periods_per_week}) cannot exceed maximum "
                f"weekly periods ({rule.max_periods_per_week})."
            )

        if rule.max_periods_per_day < 1:
            raise ValidationError(
                f"Maximum daily periods must be at least 1, got {rule.max_periods_per_day}."
            )
        if rule.min_periods_per_day < 0:
            raise ValidationError(
                f"Minimum daily periods cannot be negative, got {rule.min_periods_per_day}."
            )
        if rule.min_periods_per_day > rule.max_periods_per_day:
            raise ValidationError(
                f"Minimum daily periods ({rule.min_periods_per_day}) cannot exceed maximum "
                f"daily periods ({rule.max_periods_per_day})."
            )

        if rule.max_consecutive_periods < 1:
            raise ValidationError(
                f"Maximum consecutive periods must be >= 1, got {rule.max_consecutive_periods}."
            )

        # Contact minutes validation
        if rule.min_contact_minutes_per_week is not None and rule.min_contact_minutes_per_week < 0:
            raise ValidationError("Minimum weekly contact minutes cannot be negative.")
        if rule.max_contact_minutes_per_week is not None and rule.max_contact_minutes_per_week < 0:
            raise ValidationError("Maximum weekly contact minutes cannot be negative.")
        if (
            rule.min_contact_minutes_per_week is not None
            and rule.max_contact_minutes_per_week is not None
            and rule.min_contact_minutes_per_week > rule.max_contact_minutes_per_week
        ):
            raise ValidationError(
                f"Minimum weekly contact minutes ({rule.min_contact_minutes_per_week}) cannot exceed maximum "
                f"contact minutes ({rule.max_contact_minutes_per_week})."
            )

        # Per-class limits validation
        if rule.min_periods_per_class_per_week is not None and rule.min_periods_per_class_per_week < 0:
            raise ValidationError("Minimum per-class weekly periods cannot be negative.")
        if rule.max_periods_per_class_per_week is not None and rule.max_periods_per_class_per_week < 1:
            raise ValidationError("Maximum per-class weekly periods must be at least 1.")
        if (
            rule.min_periods_per_class_per_week is not None
            and rule.max_periods_per_class_per_week is not None
            and rule.min_periods_per_class_per_week > rule.max_periods_per_class_per_week
        ):
            raise ValidationError(
                "Minimum per-class weekly periods cannot exceed maximum per-class weekly periods."
            )

        if rule.max_periods_per_class_per_day is not None and rule.max_periods_per_class_per_day < 1:
            raise ValidationError("Maximum per-class daily periods must be at least 1.")

        if rule.max_working_days is not None and rule.max_working_days < 1:
            raise ValidationError("Maximum working days per week must be at least 1.")

    @staticmethod
    def validate_preference_weight(weight: int) -> None:
        """Validates normalized weight is on 1..10 scale."""
        if not 1 <= weight <= 10:
            raise ValidationError(f"Preference weight must be between 1 and 10, got {weight}.")

    @staticmethod
    def validate_slot_weight(weight: int) -> None:
        """Validates slot weight is on -10..+10 scale."""
        if not -10 <= weight <= 10:
            raise ValidationError(f"Slot weight must be between -10 and +10, got {weight}.")

    @staticmethod
    def validate_preference(
        pref: DetailedTeacherPreference,
        institution: Optional[Institution] = None,
    ) -> None:
        """Validates a soft preference object."""
        if not pref.teacher_id or not pref.teacher_id.strip():
            raise ValidationError("Preference must reference a valid teacher_id.")
        WorkloadValidator.validate_preference_weight(pref.weight)

        if institution is not None:
            if pref.target_value is not None:
                if isinstance(pref.target_value, list):
                    for day in pref.target_value:
                        if isinstance(day, int) and day not in institution.working_days:
                            raise ValidationError(
                                f"Preference target day {day} is not in institution working days: {institution.working_days}."
                            )
                elif isinstance(pref.target_value, tuple) and len(pref.target_value) == 2:
                    day, period = pref.target_value
                    WorkloadValidator.validate_slot(
                        day, period, institution.working_days, institution.periods_per_day
                    )

    @staticmethod
    def validate_profile(profile: WorkloadProfile) -> None:
        """Validates a workload profile definition."""
        if not profile.name or not profile.name.strip():
            raise ValidationError("WorkloadProfile name cannot be empty.")
        if profile.min_periods_per_week < 0:
            raise ValidationError("min_periods_per_week cannot be negative.")
        if profile.max_periods_per_week < profile.min_periods_per_week:
            raise ValidationError("max_periods_per_week cannot be less than min_periods_per_week.")
        if profile.max_periods_per_day < 1:
            raise ValidationError("max_periods_per_day must be at least 1.")
        if profile.max_consecutive_periods < 1:
            raise ValidationError("max_consecutive_periods must be at least 1.")
