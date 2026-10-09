"""Solver Workload and Preference Adapter.

Provides the clean integration contract for Agent 5 (Scheduling Engine / CP-SAT solver),
supplying active hard availability sets, workload rule bounds, soft preference weights,
and post-solve preference evaluation helpers.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.models import (
    Institution,
    ScheduledSession,
    Teacher,
    TeacherWorkloadRule as CoreTeacherWorkloadRule,
)
from workload.availability import AvailabilityManager
from workload.preferences import PreferenceManager
from workload.rules import WorkloadRuleManager
from workload.models import (
    PreferenceEvaluationReport,
    TeacherWorkloadRuleExtended,
)


class SolverWorkloadAdapter:
    """Prepares solver data bundles and evaluates completed timetables for Agent 5."""

    def __init__(
        self,
        availability_mgr: AvailabilityManager,
        rule_mgr: WorkloadRuleManager,
        pref_mgr: PreferenceManager,
    ) -> None:
        self.availability_mgr = availability_mgr
        self.rule_mgr = rule_mgr
        self.pref_mgr = pref_mgr

    def export_solver_availability(
        self,
        teachers: List[Teacher],
        institution: Optional[Institution] = None,
    ) -> Dict[str, Set[Tuple[int, int]]]:
        """Builds `teacher_availability` mapping: teacher_id -> {(day, period)} of unavailable slots.

        This directly populates SchedulingInputBundle.teacher_availability.
        """
        result: Dict[str, Set[Tuple[int, int]]] = {}
        for teacher in teachers:
            unavailable = self.availability_mgr.get_unavailable_slots(teacher.id, institution)
            result[teacher.id] = unavailable
        return result

    def export_solver_workload_rules(
        self,
        teachers: List[Teacher],
    ) -> Dict[str, CoreTeacherWorkloadRule]:
        """Builds `teacher_workload_rules` mapping: teacher_id -> CoreTeacherWorkloadRule.

        This directly populates SchedulingInputBundle.teacher_workload_rules.
        """
        result: Dict[str, CoreTeacherWorkloadRule] = {}
        for teacher in teachers:
            ext_rule = self.rule_mgr.get_rule_for_teacher(teacher.id)
            result[teacher.id] = ext_rule.to_core_rule()
        return result

    def export_solver_preferences(
        self,
        teachers: List[Teacher],
        institution: Institution,
    ) -> Dict[str, Dict[Tuple[int, int], int]]:
        """Builds `teacher_preferences` mapping: teacher_id -> {(day, period) -> weight (-10..+10)}.

        This directly populates SchedulingInputBundle.teacher_preferences.
        """
        result: Dict[str, Dict[Tuple[int, int], int]] = {}
        for teacher in teachers:
            pref_matrix = self.pref_mgr.build_solver_slot_preference_matrix(
                teacher_id=teacher.id,
                institution=institution,
            )
            result[teacher.id] = pref_matrix
        return result

    def evaluate_timetable_preferences(
        self,
        teachers: List[Teacher],
        sessions: List[ScheduledSession],
        institution: Institution,
    ) -> Dict[str, PreferenceEvaluationReport]:
        """Evaluates a solved timetable across all faculty against their soft preferences.

        Returns teacher_id -> PreferenceEvaluationReport with satisfaction rates and penalties.
        """
        reports: Dict[str, PreferenceEvaluationReport] = {}
        for teacher in teachers:
            report = self.pref_mgr.evaluate_preferences(
                teacher_id=teacher.id,
                sessions=sessions,
                institution=institution,
            )
            reports[teacher.id] = report
        return reports

    def compute_total_penalty_score(
        self,
        teachers: List[Teacher],
        sessions: List[ScheduledSession],
        institution: Institution,
    ) -> float:
        """Computes the overall soft preference penalty score for OptimizationMetrics."""
        reports = self.evaluate_timetable_preferences(teachers, sessions, institution)
        return round(sum(r.total_penalty for r in reports.values()), 2)
