"""Teacher workload report generation and analytics.

Evaluates assigned periods, contact hours, weekly/daily bounds,
consecutive limits, and capacity balance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import (
    Institution,
    ScheduledSession,
    Teacher,
    TeacherWorkloadRule,
)
from exchange.models import WorkloadReportRow


class WorkloadReportGenerator:
    """Generates comprehensive faculty teaching load evaluations."""

    @classmethod
    def generate_report(
        cls,
        teachers: List[Teacher],
        sessions: List[ScheduledSession],
        rules: Optional[Dict[str, TeacherWorkloadRule]] = None,
        institution: Optional[Institution] = None,
        department_filter: Optional[str] = None,
        department_names: Optional[Dict[str, str]] = None,
    ) -> List[WorkloadReportRow]:
        """Calculates workload statistics per faculty member.

        Distinguishes missing configuration from actual workload violations.
        """
        rules_map = rules or {}
        dept_names = department_names or {}
        period_duration_minutes = institution.period_duration_minutes if institution else 60

        # Index sessions by teacher
        sessions_by_teacher: Dict[str, List[ScheduledSession]] = {}
        for s in sessions:
            sessions_by_teacher.setdefault(s.teacher_id, []).append(s)

        report_rows: List[WorkloadReportRow] = []

        for teacher in teachers:
            # Department filter
            if department_filter and teacher.department_id != department_filter:
                continue

            t_sessions = sessions_by_teacher.get(teacher.id, [])

            # Compute assigned periods and contact hours
            total_periods = sum(s.duration_periods for s in t_sessions)
            contact_hours = (total_periods * period_duration_minutes) / 60.0

            # Daily periods & consecutive periods
            daily_periods: Dict[int, int] = {}
            # Map of day -> set of occupied period indices
            occupied_slots_by_day: Dict[int, set[int]] = {}

            for s in t_sessions:
                daily_periods[s.day_of_week] = daily_periods.get(s.day_of_week, 0) + s.duration_periods
                for p in range(s.start_period, s.start_period + s.duration_periods):
                    occupied_slots_by_day.setdefault(s.day_of_week, set()).add(p)

            # Max consecutive periods observed
            max_consecutive = 0
            for day_idx, slot_set in occupied_slots_by_day.items():
                if not slot_set:
                    continue
                sorted_slots = sorted(slot_set)
                current_consec = 1
                for i in range(1, len(sorted_slots)):
                    if sorted_slots[i] == sorted_slots[i - 1] + 1:
                        current_consec += 1
                    else:
                        max_consecutive = max(max_consecutive, current_consec)
                        current_consec = 1
                max_consecutive = max(max_consecutive, current_consec)

            # Check rule configuration
            rule = rules_map.get(teacher.id)
            has_rule = rule is not None

            min_periods = rule.min_periods_per_week if rule else None
            max_periods = rule.max_periods_per_week if rule else None
            remaining_cap = None
            if max_periods is not None:
                remaining_cap = max(0, max_periods - total_periods)

            is_overloaded = False
            is_underloaded = False
            warnings_list = []

            if has_rule:
                if max_periods is not None and total_periods > max_periods:
                    is_overloaded = True
                    warnings_list.append(f"Exceeds max weekly limit by {total_periods - max_periods} periods.")

                if min_periods is not None and min_periods > 0 and total_periods < min_periods:
                    is_underloaded = True
                    warnings_list.append(f"Under minimum weekly requirement by {min_periods - total_periods} periods.")

                if rule.max_periods_per_day:
                    for d, count in daily_periods.items():
                        if count > rule.max_periods_per_day:
                            warnings_list.append(f"Day {d} load ({count}) exceeds daily limit ({rule.max_periods_per_day}).")

                if rule.max_consecutive_periods and max_consecutive > rule.max_consecutive_periods:
                    warnings_list.append(f"Consecutive periods ({max_consecutive}) exceeds limit ({rule.max_consecutive_periods}).")
            else:
                warnings_list.append("No specific workload rule configured; default institutional norms apply.")

            dept_name = dept_names.get(teacher.department_id, teacher.department_id)

            report_rows.append(WorkloadReportRow(
                teacher_id=teacher.id,
                teacher_name=teacher.name,
                employee_id=teacher.employee_id,
                department_name=dept_name,
                assigned_periods=total_periods,
                assigned_contact_hours=round(contact_hours, 2),
                min_periods=min_periods,
                max_periods=max_periods,
                remaining_capacity=remaining_cap,
                daily_periods=daily_periods,
                max_consecutive_observed=max_consecutive,
                is_overloaded=is_overloaded,
                is_underloaded=is_underloaded,
                has_workload_rule=has_rule,
                warning_message=" | ".join(warnings_list) if warnings_list else "Normal workload",
            ))

        return sorted(report_rows, key=lambda r: r.teacher_name)
