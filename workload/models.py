"""Domain models for Teacher Preferences and Workload Engine.

This module defines models for workload rules, profiles, soft preferences,
violations, analytics, and preference evaluation reports.
All models integrate cleanly with core.models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from core.interfaces import FacultyWorkloadSummary as CoreFacultyWorkloadSummary
from core.models import (
    TeacherAvailability as CoreTeacherAvailability,
    TeacherPreference as CoreTeacherPreference,
    TeacherWorkloadRule as CoreTeacherWorkloadRule,
)


class WorkloadViolationType(str, Enum):
    """Types of workload rule violations."""
    WEEKLY_PERIODS_EXCEEDED = "WEEKLY_PERIODS_EXCEEDED"
    WEEKLY_PERIODS_BELOW_MIN = "WEEKLY_PERIODS_BELOW_MIN"
    WEEKLY_HOURS_EXCEEDED = "WEEKLY_HOURS_EXCEEDED"
    WEEKLY_HOURS_BELOW_MIN = "WEEKLY_HOURS_BELOW_MIN"
    DAILY_PERIODS_EXCEEDED = "DAILY_PERIODS_EXCEEDED"
    DAILY_PERIODS_BELOW_MIN = "DAILY_PERIODS_BELOW_MIN"
    DAILY_HOURS_EXCEEDED = "DAILY_HOURS_EXCEEDED"
    CONSECUTIVE_PERIODS_EXCEEDED = "CONSECUTIVE_PERIODS_EXCEEDED"
    CLASS_WEEKLY_PERIODS_EXCEEDED = "CLASS_WEEKLY_PERIODS_EXCEEDED"
    CLASS_WEEKLY_PERIODS_BELOW_MIN = "CLASS_WEEKLY_PERIODS_BELOW_MIN"
    CLASS_DAILY_PERIODS_EXCEEDED = "CLASS_DAILY_PERIODS_EXCEEDED"
    SUBJECT_LIMIT_EXCEEDED = "SUBJECT_LIMIT_EXCEEDED"
    UNAVAILABLE_SLOT_VIOLATED = "UNAVAILABLE_SLOT_VIOLATED"
    MAX_WORKING_DAYS_EXCEEDED = "MAX_WORKING_DAYS_EXCEEDED"


@dataclass
class WorkloadViolation:
    """Detailed record of a workload constraint violation."""
    violation_type: WorkloadViolationType
    severity: str  # "ERROR" for hard violations, "WARNING" for guidelines
    message: str
    teacher_id: str
    day: Optional[int] = None
    period: Optional[int] = None
    class_group_id: Optional[str] = None
    subject_id: Optional[str] = None
    current_value: float = 0.0
    limit_value: float = 0.0

    @property
    def is_hard(self) -> bool:
        return self.severity == "ERROR"


class SoftPreferenceType(str, Enum):
    """Categorization of institutional and teacher soft preferences."""
    PREFER_MORNING = "PREFER_MORNING"
    AVOID_FINAL_PERIOD = "AVOID_FINAL_PERIOD"
    PREFER_DAYS = "PREFER_DAYS"
    AVOID_DAYS = "AVOID_DAYS"
    PREFER_CONSECUTIVE = "PREFER_CONSECUTIVE"
    MINIMIZE_GAPS = "MINIMIZE_GAPS"
    MINIMIZE_WORKING_DAYS = "MINIMIZE_WORKING_DAYS"
    TARGET_DAILY_WORKLOAD = "TARGET_DAILY_WORKLOAD"
    AVOID_EXCESSIVE_CONSECUTIVE = "AVOID_EXCESSIVE_CONSECUTIVE"
    PREFER_TIME_RANGE = "PREFER_TIME_RANGE"
    DISTRIBUTE_EVENLY = "DISTRIBUTE_EVENLY"
    AVOID_SINGLE_SESSIONS = "AVOID_SINGLE_SESSIONS"
    SLOT_PREFERENCE = "SLOT_PREFERENCE"


@dataclass
class DetailedTeacherPreference:
    """Configurable soft preference with a normalized priority weight (1..10)."""
    teacher_id: str
    preference_type: SoftPreferenceType
    weight: int = 5  # Normalized 1 (low) to 10 (critical)
    target_value: Any = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_active: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.weight <= 10:
            raise ValidationError(f"Preference weight must be between 1 and 10, got {self.weight}.")


@dataclass
class WorkloadProfile:
    """Reusable workload limit profile (e.g. Full-Time, Part-Time 50%, Adjunct, Dean)."""
    id: str
    name: str
    description: str = ""
    max_periods_per_week: int = 20
    min_periods_per_week: int = 0
    max_periods_per_day: int = 5
    min_periods_per_day: int = 0
    max_consecutive_periods: int = 3
    max_contact_minutes_per_week: Optional[int] = None
    min_contact_minutes_per_week: Optional[int] = None
    max_contact_minutes_per_day: Optional[int] = None
    max_periods_per_class_per_week: Optional[int] = None
    min_periods_per_class_per_week: Optional[int] = None
    max_periods_per_class_per_day: Optional[int] = None
    max_working_days: Optional[int] = None

    def __post_init__(self) -> None:
        if self.max_periods_per_week < self.min_periods_per_week:
            raise ValidationError("max_periods_per_week cannot be less than min_periods_per_week.")
        if self.max_periods_per_day < 1:
            raise ValidationError("max_periods_per_day must be at least 1.")
        if self.max_consecutive_periods < 1:
            raise ValidationError("max_consecutive_periods must be at least 1.")


@dataclass
class TeacherWorkloadRuleExtended:
    """Comprehensive workload configuration for a specific teacher.

    Wraps and extends core.models.TeacherWorkloadRule with contractual, daily,
    consecutive, per-class, and contact-hour boundaries.
    """
    teacher_id: str
    max_periods_per_week: int = 20
    min_periods_per_week: int = 0
    max_periods_per_day: int = 5
    min_periods_per_day: int = 0
    max_consecutive_periods: int = 3
    max_contact_minutes_per_week: Optional[int] = None
    min_contact_minutes_per_week: Optional[int] = None
    max_contact_minutes_per_day: Optional[int] = None
    max_periods_per_class_per_week: Optional[int] = None
    min_periods_per_class_per_week: Optional[int] = None
    max_periods_per_class_per_day: Optional[int] = None
    max_working_days: Optional[int] = None
    profile_id: Optional[str] = None
    subject_limits: Dict[str, int] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.min_periods_per_week < 0:
            raise ValidationError("min_periods_per_week cannot be negative.")
        if self.max_periods_per_week < self.min_periods_per_week:
            raise ValidationError("max_periods_per_week cannot be less than min_periods_per_week.")
        if self.max_periods_per_day < 1:
            raise ValidationError("max_periods_per_day must be at least 1.")
        if self.min_periods_per_day < 0:
            raise ValidationError("min_periods_per_day cannot be negative.")
        if self.max_periods_per_day < self.min_periods_per_day:
            raise ValidationError("max_periods_per_day cannot be less than min_periods_per_day.")
        if self.max_consecutive_periods < 1:
            raise ValidationError("max_consecutive_periods must be at least 1.")
        if (
            self.max_contact_minutes_per_week is not None
            and self.min_contact_minutes_per_week is not None
            and self.max_contact_minutes_per_week < self.min_contact_minutes_per_week
        ):
            raise ValidationError("max_contact_minutes_per_week cannot be less than min_contact_minutes_per_week.")

    def to_core_rule(self) -> CoreTeacherWorkloadRule:
        """Converts to standard CoreTeacherWorkloadRule for solver consumption."""
        return CoreTeacherWorkloadRule(
            teacher_id=self.teacher_id,
            max_periods_per_week=self.max_periods_per_week,
            min_periods_per_week=self.min_periods_per_week,
            max_periods_per_day=self.max_periods_per_day,
            max_consecutive_periods=self.max_consecutive_periods,
            id=self.id,
        )

    @classmethod
    def from_core_rule(cls, core_rule: CoreTeacherWorkloadRule) -> TeacherWorkloadRuleExtended:
        """Constructs an extended rule from a CoreTeacherWorkloadRule."""
        return cls(
            teacher_id=core_rule.teacher_id,
            max_periods_per_week=core_rule.max_periods_per_week,
            min_periods_per_week=core_rule.min_periods_per_week,
            max_periods_per_day=core_rule.max_periods_per_day,
            max_consecutive_periods=core_rule.max_consecutive_periods,
            id=core_rule.id,
        )

    @classmethod
    def from_profile(cls, teacher_id: str, profile: WorkloadProfile) -> TeacherWorkloadRuleExtended:
        """Instantiates teacher rules from a shared profile template."""
        return cls(
            teacher_id=teacher_id,
            max_periods_per_week=profile.max_periods_per_week,
            min_periods_per_week=profile.min_periods_per_week,
            max_periods_per_day=profile.max_periods_per_day,
            min_periods_per_day=profile.min_periods_per_day,
            max_consecutive_periods=profile.max_consecutive_periods,
            max_contact_minutes_per_week=profile.max_contact_minutes_per_week,
            min_contact_minutes_per_week=profile.min_contact_minutes_per_week,
            max_contact_minutes_per_day=profile.max_contact_minutes_per_day,
            max_periods_per_class_per_week=profile.max_periods_per_class_per_week,
            min_periods_per_class_per_week=profile.min_periods_per_class_per_week,
            max_periods_per_class_per_day=profile.max_periods_per_class_per_day,
            max_working_days=profile.max_working_days,
            profile_id=profile.id,
        )


@dataclass
class AvailabilityException:
    """Special override or exception to a teacher's recurring availability."""
    teacher_id: str
    day_of_week: int
    period_index: int
    is_available: bool
    reason: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class TeacherWorkloadSummary(CoreFacultyWorkloadSummary):
    """Detailed summary of a teacher's assigned workload, capacity, and violations."""
    assigned_contact_minutes: int = 0
    required_periods_per_week: int = 0
    remaining_capacity_periods: int = 0
    remaining_capacity_hours: float = 0.0
    teaching_days_count: int = 0
    assigned_classes_count: int = 0
    daily_contact_minutes: Dict[int, int] = field(default_factory=dict)
    subject_wise_periods: Dict[str, int] = field(default_factory=dict)
    class_wise_periods: Dict[str, int] = field(default_factory=dict)
    violations: List[WorkloadViolation] = field(default_factory=list)


@dataclass(frozen=True)
class PreferenceEvaluationItem:
    """Evaluation result for an individual soft preference."""
    preference_id: str
    preference_type: str
    is_satisfied: bool
    satisfaction_score: float  # 0.0 (completely violated) to 1.0 (fully satisfied)
    penalty_incurred: float    # (1.0 - score) * weight
    weight_applied: int
    involved_sessions: List[str] = field(default_factory=list)
    explanation: str = ""


@dataclass(frozen=True)
class PreferenceEvaluationReport:
    """Consolidated evaluation of all preferences for a teacher or timetable."""
    teacher_id: str
    total_penalty: float
    satisfaction_rate: float  # 0.0 to 1.0
    items: List[PreferenceEvaluationItem] = field(default_factory=list)


@dataclass(frozen=True)
class DepartmentWorkloadSummary:
    """Aggregated department-level workload metrics."""
    department_id: str
    department_name: str
    total_teachers: int
    total_assigned_periods: int
    total_assigned_contact_hours: float
    average_periods_per_teacher: float
    overloaded_teachers: List[str] = field(default_factory=list)
    underloaded_teachers: List[str] = field(default_factory=list)
    teachers_with_high_unused_capacity: List[str] = field(default_factory=list)
    workload_std_deviation: float = 0.0


@dataclass(frozen=True)
class FairnessMetrics:
    """Institutional fairness metrics evaluating workload equity."""
    assigned_workload_variance: float
    workload_spread_periods: int  # max - min assigned periods across comparable faculty
    average_idle_gaps_per_teacher: float
    undesirable_periods_count_per_teacher: Dict[str, int] = field(default_factory=dict)
    gini_coefficient: float = 0.0
    is_equitably_distributed: bool = True
