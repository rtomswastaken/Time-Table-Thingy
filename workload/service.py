"""Workload Service implementation conforming to core.interfaces.WorkloadService.

Coordinates availability management, workload calculations, soft preferences,
rule configuration, and analytics reporting.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.interfaces import FacultyWorkloadSummary, TimetableRepository, WorkloadService
from core.models import Institution, ScheduledSession, Teacher
from workload.analytics import WorkloadAnalytics
from workload.availability import AvailabilityManager
from workload.calculator import WorkloadCalculator
from workload.models import (
    DepartmentWorkloadSummary,
    DetailedTeacherPreference,
    FairnessMetrics,
    PreferenceEvaluationReport,
    TeacherWorkloadRuleExtended,
    TeacherWorkloadSummary,
    WorkloadProfile,
)
from workload.preferences import PreferenceManager
from workload.repository import BaseWorkloadRepository, InMemoryWorkloadRepository
from workload.rules import WorkloadRuleManager
from workload.solver_adapter import SolverWorkloadAdapter
from workload.validation import WorkloadValidator


class WorkloadServiceImpl:
    """Production implementation of the Agent 4 WorkloadService contract."""

    def __init__(
        self,
        repository: Optional[BaseWorkloadRepository] = None,
        timetable_repo: Optional[TimetableRepository] = None,
        institution: Optional[Institution] = None,
        teachers: Optional[List[Teacher]] = None,
    ) -> None:
        self.repository = repository or InMemoryWorkloadRepository()
        self.timetable_repo = timetable_repo
        self.institution = institution or Institution(
            name="Default Academy", code="DEF", working_days=[0, 1, 2, 3, 4], periods_per_day=6
        )
        self._teachers: Dict[str, Teacher] = {t.id: t for t in (teachers or [])}

        self.rule_manager = WorkloadRuleManager()
        self.availability_manager = AvailabilityManager()
        self.preference_manager = PreferenceManager()
        self.calculator = WorkloadCalculator()
        self.analytics = WorkloadAnalytics(self.calculator)

        self.solver_adapter = SolverWorkloadAdapter(
            availability_mgr=self.availability_manager,
            rule_mgr=self.rule_manager,
            pref_mgr=self.preference_manager,
        )

        # Load persisted profiles into rule manager
        for profile in self.repository.list_profiles():
            self.rule_manager.register_profile(profile)

    def register_teacher(self, teacher: Teacher) -> None:
        """Registers a teacher profile for name lookup and analysis."""
        self._teachers[teacher.id] = teacher

    def set_institution(self, institution: Institution) -> None:
        """Updates the active institution calendar and settings."""
        self.institution = institution

    # -------------------------------------------------------------------------
    # core.interfaces.WorkloadService Protocol Implementation
    # -------------------------------------------------------------------------

    def calculate_faculty_workload(
        self,
        teacher_id: str,
        sessions: List[ScheduledSession],
        institution: Optional[Institution] = None,
    ) -> FacultyWorkloadSummary:
        """Calculates workload for a specific faculty member conforming to core interface."""
        inst = institution or self.institution
        teacher = self._teachers.get(teacher_id)
        teacher_name = teacher.name if teacher else f"Teacher {teacher_id}"

        rule = self.get_workload_rule(teacher_id)
        unavailable = self.availability_manager.get_unavailable_slots(teacher_id, inst)

        summary = self.calculator.calculate_teacher_workload(
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            sessions=sessions,
            rule=rule,
            institution=inst,
            unavailable_slots=unavailable,
        )
        return summary

    def calculate_all_workloads(
        self,
        timetable_id: str,
    ) -> List[FacultyWorkloadSummary]:
        """Calculates workload summaries for all faculty in a timetable."""
        sessions: List[ScheduledSession] = []
        if self.timetable_repo is not None:
            sessions = self.timetable_repo.get_sessions(timetable_id)

        # Determine teachers to evaluate
        eval_teacher_ids = set(self._teachers.keys())
        eval_teacher_ids.update(s.teacher_id for s in sessions if s.teacher_id)

        summaries: List[FacultyWorkloadSummary] = []
        for tid in sorted(eval_teacher_ids):
            summaries.append(self.calculate_faculty_workload(tid, sessions, self.institution))
        return summaries

    def set_availability(
        self,
        teacher_id: str,
        unavailable_slots: Set[Tuple[int, int]],
    ) -> None:
        """Configures hard unavailable slots for a teacher."""
        WorkloadValidator.validate_availability_slots(
            unavailable_slots,
            self.institution.working_days,
            self.institution.periods_per_day,
        )
        self.availability_manager.set_unavailable_slots(teacher_id, unavailable_slots)
        self.repository.save_unavailable_slots(teacher_id, unavailable_slots)

    def set_preferences(
        self,
        teacher_id: str,
        preferences: Dict[Tuple[int, int], int],
    ) -> None:
        """Configures discrete slot preferences (-10 to +10) for a teacher."""
        for weight in preferences.values():
            WorkloadValidator.validate_slot_weight(weight)
        self.preference_manager.set_slot_weights(teacher_id, preferences)
        self.repository.save_slot_weights(teacher_id, preferences)

    # -------------------------------------------------------------------------
    # Extended Capabilities: Rules, Detailed Preferences, Analytics, Adapter
    # -------------------------------------------------------------------------

    def get_availability(self, teacher_id: str) -> Set[Tuple[int, int]]:
        """Returns the set of unavailable (day, period) slots for a teacher."""
        cached = self.availability_manager.get_unavailable_slots(teacher_id, self.institution)
        if cached:
            return cached
        persisted = self.repository.get_unavailable_slots(teacher_id)
        if persisted:
            self.availability_manager.set_unavailable_slots(teacher_id, persisted)
            return persisted
        return set()

    def get_preferences(self, teacher_id: str) -> Dict[Tuple[int, int], int]:
        """Returns raw slot preferences map for a teacher."""
        cached = self.preference_manager.get_slot_weights(teacher_id)
        if cached:
            return cached
        persisted = self.repository.get_slot_weights(teacher_id)
        if persisted:
            self.preference_manager.set_slot_weights(teacher_id, persisted)
            return persisted
        return {}

    def get_soft_preferences(self, teacher_id: str) -> List[DetailedTeacherPreference]:
        """Returns high-level soft preferences for a teacher."""
        cached = self.preference_manager.get_preferences(teacher_id)
        if cached:
            return cached
        persisted = self.repository.get_soft_preferences(teacher_id)
        if persisted:
            self.preference_manager.set_preferences(teacher_id, persisted)
            return persisted
        return []

    def set_soft_preferences(
        self, teacher_id: str, preferences: List[DetailedTeacherPreference]
    ) -> None:
        """Saves high-level soft preferences for a teacher."""
        for p in preferences:
            WorkloadValidator.validate_preference(p, self.institution)
        self.preference_manager.set_preferences(teacher_id, preferences)
        self.repository.save_soft_preferences(teacher_id, preferences)

    def add_soft_preference(self, preference: DetailedTeacherPreference) -> None:
        """Adds a single soft preference."""
        WorkloadValidator.validate_preference(preference, self.institution)
        self.preference_manager.add_preference(preference)
        all_prefs = self.preference_manager.get_preferences(preference.teacher_id)
        self.repository.save_soft_preferences(preference.teacher_id, all_prefs)

    def get_workload_rule(self, teacher_id: str) -> TeacherWorkloadRuleExtended:
        """Retrieves or loads the workload rule for a teacher."""
        rule = self.repository.get_workload_rule(teacher_id)
        if rule:
            self.rule_manager.create_or_update_rule(rule)
            return rule
        return self.rule_manager.get_rule_for_teacher(teacher_id)

    def set_workload_rule(self, rule: TeacherWorkloadRuleExtended) -> None:
        """Saves a workload rule for a teacher."""
        WorkloadValidator.validate_workload_rule(rule)
        self.rule_manager.create_or_update_rule(rule)
        self.repository.save_workload_rule(rule)

    def apply_profile(self, teacher_id: str, profile_id: str) -> TeacherWorkloadRuleExtended:
        """Applies a workload profile template to a teacher."""
        rule = self.rule_manager.apply_profile_to_teacher(teacher_id, profile_id)
        self.repository.save_workload_rule(rule)
        return rule

    def get_profile(self, profile_id: str) -> WorkloadProfile:
        """Retrieves a workload profile."""
        return self.rule_manager.get_profile(profile_id)

    def save_profile(self, profile: WorkloadProfile) -> None:
        """Saves a workload profile."""
        WorkloadValidator.validate_profile(profile)
        self.rule_manager.register_profile(profile)
        self.repository.save_profile(profile)

    def list_profiles(self) -> List[WorkloadProfile]:
        """Lists all registered profiles."""
        return self.rule_manager.list_profiles()

    def get_department_summary(
        self,
        department_id: str,
        department_name: str,
        timetable_id: str,
    ) -> DepartmentWorkloadSummary:
        """Generates departmental workload analytics."""
        all_summaries = [
            s for s in self.calculate_all_workloads(timetable_id) if isinstance(s, TeacherWorkloadSummary)
        ]
        return self.analytics.compute_department_summary(
            department_id=department_id,
            department_name=department_name,
            teachers=list(self._teachers.values()),
            summaries=all_summaries,
        )

    def analyze_fairness(self, timetable_id: str) -> FairnessMetrics:
        """Analyzes equity of workload distribution across faculty."""
        all_summaries = [
            s for s in self.calculate_all_workloads(timetable_id) if isinstance(s, TeacherWorkloadSummary)
        ]
        sessions = self.timetable_repo.get_sessions(timetable_id) if self.timetable_repo else []
        return self.analytics.analyze_fairness(all_summaries, sessions, self.institution)

    def evaluate_preferences_report(
        self, timetable_id: str
    ) -> Dict[str, PreferenceEvaluationReport]:
        """Evaluates all teacher preferences against the timetable sessions."""
        sessions = self.timetable_repo.get_sessions(timetable_id) if self.timetable_repo else []
        return self.solver_adapter.evaluate_timetable_preferences(
            teachers=list(self._teachers.values()),
            sessions=sessions,
            institution=self.institution,
        )
