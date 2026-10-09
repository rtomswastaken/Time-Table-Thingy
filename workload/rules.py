"""Workload rules and profile management.

Defines default institutional workload profiles (Full-time, Part-time, Adjunct, etc.),
allows creating and modifying teacher workload rules, and validates limits.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.exceptions import EntityNotFoundError, ValidationError
from workload.models import (
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
)


class WorkloadRuleManager:
    """Manages workload profiles and teacher-specific workload rules."""

    # Built-in standard institutional profiles
    DEFAULT_PROFILES: Dict[str, WorkloadProfile] = {
        "full_time_standard": WorkloadProfile(
            id="full_time_standard",
            name="Full-Time Standard",
            description="Standard 18-20 period weekly load with max 4-5 periods daily.",
            max_periods_per_week=20,
            min_periods_per_week=12,
            max_periods_per_day=5,
            min_periods_per_day=1,
            max_consecutive_periods=3,
            max_contact_minutes_per_week=1200,  # 20 hours * 60 min
            min_contact_minutes_per_week=720,   # 12 hours * 60 min
            max_periods_per_class_per_week=6,
            max_periods_per_class_per_day=2,
            max_working_days=5,
        ),
        "part_time_half": WorkloadProfile(
            id="part_time_half",
            name="Part-Time (50%)",
            description="Half-time faculty with 8-10 periods weekly.",
            max_periods_per_week=10,
            min_periods_per_week=6,
            max_periods_per_day=4,
            min_periods_per_day=1,
            max_consecutive_periods=2,
            max_contact_minutes_per_week=600,
            min_contact_minutes_per_week=360,
            max_periods_per_class_per_week=4,
            max_periods_per_class_per_day=2,
            max_working_days=3,
        ),
        "adjunct_lecturer": WorkloadProfile(
            id="adjunct_lecturer",
            name="Adjunct / Visiting Faculty",
            description="Visiting faculty teaching limited specific modules.",
            max_periods_per_week=6,
            min_periods_per_week=2,
            max_periods_per_day=4,
            min_periods_per_day=1,
            max_consecutive_periods=2,
            max_contact_minutes_per_week=360,
            min_contact_minutes_per_week=120,
            max_periods_per_class_per_week=4,
            max_periods_per_class_per_day=2,
            max_working_days=2,
        ),
        "department_head": WorkloadProfile(
            id="department_head",
            name="Department Head / Administrator",
            description="Administrative reduction: 6-10 teaching periods weekly.",
            max_periods_per_week=10,
            min_periods_per_week=4,
            max_periods_per_day=3,
            min_periods_per_day=0,
            max_consecutive_periods=2,
            max_contact_minutes_per_week=600,
            min_contact_minutes_per_week=240,
            max_periods_per_class_per_week=4,
            max_periods_per_class_per_day=2,
            max_working_days=4,
        ),
    }

    def __init__(self) -> None:
        self._profiles: Dict[str, WorkloadProfile] = dict(self.DEFAULT_PROFILES)
        self._rules: Dict[str, TeacherWorkloadRuleExtended] = {}

    def register_profile(self, profile: WorkloadProfile) -> None:
        """Adds or updates a workload profile."""
        self._profiles[profile.id] = profile

    def get_profile(self, profile_id: str) -> WorkloadProfile:
        """Retrieves a workload profile by ID."""
        if profile_id not in self._profiles:
            raise EntityNotFoundError(f"Workload profile '{profile_id}' not found.")
        return self._profiles[profile_id]

    def list_profiles(self) -> List[WorkloadProfile]:
        """Returns all registered workload profiles."""
        return list(self._profiles.values())

    def create_or_update_rule(self, rule: TeacherWorkloadRuleExtended) -> TeacherWorkloadRuleExtended:
        """Saves a teacher workload rule."""
        self._rules[rule.teacher_id] = rule
        return rule

    def apply_profile_to_teacher(self, teacher_id: str, profile_id: str) -> TeacherWorkloadRuleExtended:
        """Generates and sets a teacher workload rule from an existing profile."""
        profile = self.get_profile(profile_id)
        rule = TeacherWorkloadRuleExtended.from_profile(teacher_id, profile)
        self._rules[teacher_id] = rule
        return rule

    def get_rule_for_teacher(self, teacher_id: str) -> TeacherWorkloadRuleExtended:
        """Returns the workload rule for a teacher, defaulting to full-time if none registered."""
        if teacher_id in self._rules:
            return self._rules[teacher_id]
        # Return default full-time standard rule
        default_rule = TeacherWorkloadRuleExtended.from_profile(
            teacher_id=teacher_id,
            profile=self._profiles["full_time_standard"],
        )
        return default_rule

    def list_all_rules(self) -> List[TeacherWorkloadRuleExtended]:
        """Returns all registered teacher rules."""
        return list(self._rules.values())

    def delete_rule(self, teacher_id: str) -> bool:
        """Removes a custom teacher workload rule."""
        if teacher_id in self._rules:
            del self._rules[teacher_id]
            return True
        return False
