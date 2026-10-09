"""Workload Analytics and Department Summaries.

Provides departmental aggregations, unused capacity tracking, and institutional
fairness analysis evaluating workload distribution equity across faculty.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

from core.models import Institution, ScheduledSession, Teacher
from workload.calculator import WorkloadCalculator
from workload.models import (
    DepartmentWorkloadSummary,
    FairnessMetrics,
    TeacherWorkloadRuleExtended,
    TeacherWorkloadSummary,
)


class WorkloadAnalytics:
    """Analytical engine for department summaries and schedule fairness."""

    def __init__(self, calculator: Optional[WorkloadCalculator] = None) -> None:
        self.calculator = calculator or WorkloadCalculator()

    def compute_department_summary(
        self,
        department_id: str,
        department_name: str,
        teachers: List[Teacher],
        summaries: List[TeacherWorkloadSummary],
        unused_capacity_threshold: float = 0.3,
    ) -> DepartmentWorkloadSummary:
        """Compiles departmental overview from teacher summaries.

        Args:
            department_id: Department UUID.
            department_name: Display name.
            teachers: Faculty members belonging to department.
            summaries: Calculated TeacherWorkloadSummary list.
            unused_capacity_threshold: Fraction of maximum load unused to flag as high capacity (default 30%).
        """
        dept_teacher_ids = {t.id for t in teachers if t.department_id == department_id}
        dept_summaries = [s for s in summaries if s.teacher_id in dept_teacher_ids]

        total_teachers = len(dept_summaries)
        if total_teachers == 0:
            return DepartmentWorkloadSummary(
                department_id=department_id,
                department_name=department_name,
                total_teachers=0,
                total_assigned_periods=0,
                total_assigned_contact_hours=0.0,
                average_periods_per_teacher=0.0,
            )

        total_assigned_periods = sum(s.assigned_periods_per_week for s in dept_summaries)
        total_assigned_hours = round(sum(s.assigned_contact_hours_per_week for s in dept_summaries), 2)
        avg_periods = round(total_assigned_periods / total_teachers, 2)

        overloaded = [s.teacher_name for s in dept_summaries if s.is_overloaded]
        underloaded = [s.teacher_name for s in dept_summaries if s.is_underloaded]

        high_unused = []
        for s in dept_summaries:
            if s.max_periods_allowed > 0:
                unused_ratio = s.remaining_capacity_periods / s.max_periods_allowed
                if unused_ratio >= unused_capacity_threshold:
                    high_unused.append(s.teacher_name)

        # Standard deviation
        periods_list = [s.assigned_periods_per_week for s in dept_summaries]
        mean = avg_periods
        variance = sum((x - mean) ** 2 for x in periods_list) / total_teachers
        std_dev = round(math.sqrt(variance), 2)

        return DepartmentWorkloadSummary(
            department_id=department_id,
            department_name=department_name,
            total_teachers=total_teachers,
            total_assigned_periods=total_assigned_periods,
            total_assigned_contact_hours=total_assigned_hours,
            average_periods_per_teacher=avg_periods,
            overloaded_teachers=overloaded,
            underloaded_teachers=underloaded,
            teachers_with_high_unused_capacity=high_unused,
            workload_std_deviation=std_dev,
        )

    def analyze_fairness(
        self,
        summaries: List[TeacherWorkloadSummary],
        sessions: List[ScheduledSession],
        institution: Institution,
    ) -> FairnessMetrics:
        """Computes fairness and workload equity metrics across faculty members.

        Considers variance, spread, Gini coefficient, idle gaps, and unfavorable slot counts.
        """
        if not summaries:
            return FairnessMetrics(
                assigned_workload_variance=0.0,
                workload_spread_periods=0,
                average_idle_gaps_per_teacher=0.0,
            )

        # Workload spread and variance
        periods = [s.assigned_periods_per_week for s in summaries]
        n = len(periods)
        mean_load = sum(periods) / n
        variance = sum((x - mean_load) ** 2 for x in periods) / n
        spread = max(periods) - min(periods)

        # Gini Coefficient calculation
        gini = self._calculate_gini(periods)

        # Gaps analysis and undesirable slot counts
        last_period_index = institution.periods_per_day - 1
        undesirable_counts: Dict[str, int] = {}
        total_gaps = 0

        for s_summary in summaries:
            tid = s_summary.teacher_id
            t_sessions = [sess for sess in sessions if sess.teacher_id == tid]

            # Track undesirable slots (e.g. last period of any day)
            undesirable_hits = sum(
                1 for sess in t_sessions if last_period_index in sess.occupied_periods
            )
            undesirable_counts[s_summary.teacher_name] = undesirable_hits

            # Calculate idle gaps
            day_slots: Dict[int, List[int]] = {}
            for sess in t_sessions:
                if sess.day_of_week not in day_slots:
                    day_slots[sess.day_of_week] = []
                day_slots[sess.day_of_week].extend(sess.occupied_periods)

            teacher_gaps = 0
            for day, sls in day_slots.items():
                if len(sls) >= 2:
                    span = max(sls) - min(sls) + 1
                    gaps = span - len(set(sls))
                    teacher_gaps += max(0, gaps)

            total_gaps += teacher_gaps

        avg_gaps = round(total_gaps / n, 2)
        # Equitable if Gini <= 0.25 and variance is reasonable
        is_equitable = (gini <= 0.25) and (spread <= 8)

        return FairnessMetrics(
            assigned_workload_variance=round(variance, 2),
            workload_spread_periods=spread,
            average_idle_gaps_per_teacher=avg_gaps,
            undesirable_periods_count_per_teacher=undesirable_counts,
            gini_coefficient=round(gini, 3),
            is_equitably_distributed=is_equitable,
        )

    def _calculate_gini(self, values: List[int]) -> float:
        """Calculates standard Gini coefficient for a list of non-negative values."""
        if not values or all(v == 0 for v in values):
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        total = sum(sorted_vals)
        if total == 0:
            return 0.0

        cumulative = 0
        diff_sum = 0
        for i, val in enumerate(sorted_vals):
            cumulative += val
            diff_sum += (2 * (i + 1) - n - 1) * val

        gini = diff_sum / (n * total)
        return max(0.0, min(1.0, gini))
