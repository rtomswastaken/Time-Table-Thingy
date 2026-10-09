"""Workload Calculation Engine.

Calculates faculty teaching loads, period counts vs actual contact hours/minutes,
breakdowns by day, class, subject, and detects violations against rules.
Guarantees zero floating-point drift by computing in exact integer minutes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.models import Institution, ScheduledSession
from workload.models import (
    TeacherWorkloadRuleExtended,
    TeacherWorkloadSummary,
    WorkloadViolation,
    WorkloadViolationType,
)


class WorkloadCalculator:
    """Computes teaching workloads and validates assignments against teacher rules."""

    def calculate_teacher_workload(
        self,
        teacher_id: str,
        teacher_name: str,
        sessions: List[ScheduledSession],
        rule: TeacherWorkloadRuleExtended,
        institution: Institution,
        unavailable_slots: Optional[Set[Tuple[int, int]]] = None,
        period_durations: Optional[Dict[int, int]] = None,
    ) -> TeacherWorkloadSummary:
        """Calculates complete workload summary and checks for violations.

        Args:
            teacher_id: Identifier of the teacher.
            teacher_name: Human-readable display name.
            sessions: All scheduled sessions in the timetable (filtered internally).
            rule: Configured workload rule for the teacher.
            institution: Operating institution (provides period_duration_minutes and working_days).
            unavailable_slots: Optional set of (day, period) hard restriction slots.
            period_durations: Optional map of period_index -> custom duration in minutes.

        Returns:
            TeacherWorkloadSummary with breakdowns and violations.
        """
        # Filter sessions assigned to this teacher
        assigned_sessions = [s for s in sessions if s.teacher_id == teacher_id]

        standard_period_minutes = institution.period_duration_minutes
        period_durations_map = period_durations or {}

        # 1. Total period count & contact minutes
        assigned_periods_per_week = 0
        assigned_contact_minutes = 0

        # Breakdowns
        daily_periods: Dict[int, int] = {day: 0 for day in institution.working_days}
        daily_contact_minutes: Dict[int, int] = {day: 0 for day in institution.working_days}
        daily_occupied_slots: Dict[int, List[int]] = {day: [] for day in institution.working_days}
        daily_class_periods: Dict[Tuple[int, str], int] = {}  # (day, class_id) -> periods
        class_wise_periods: Dict[str, int] = {}
        subject_wise_periods: Dict[str, int] = {}
        distinct_classes: Set[str] = set()

        violations: List[WorkloadViolation] = []

        for s in assigned_sessions:
            duration = s.duration_periods
            assigned_periods_per_week += duration
            day = s.day_of_week

            # Tally daily periods
            if day in daily_periods:
                daily_periods[day] += duration
                daily_occupied_slots[day].extend(s.occupied_periods)
            else:
                daily_periods[day] = daily_periods.get(day, 0) + duration
                daily_occupied_slots[day] = s.occupied_periods.copy()

            # Calculate exact contact minutes for this session
            session_minutes = 0
            for p in s.occupied_periods:
                p_min = period_durations_map.get(p, standard_period_minutes)
                session_minutes += p_min

            assigned_contact_minutes += session_minutes
            daily_contact_minutes[day] = daily_contact_minutes.get(day, 0) + session_minutes

            # Class breakdown
            cid = s.class_group_id
            distinct_classes.add(cid)
            class_wise_periods[cid] = class_wise_periods.get(cid, 0) + duration
            daily_class_key = (day, cid)
            daily_class_periods[daily_class_key] = daily_class_periods.get(daily_class_key, 0) + duration

            # Subject breakdown
            sub_id = s.class_subject_assignment_id
            subject_wise_periods[sub_id] = subject_wise_periods.get(sub_id, 0) + duration

            # Check if this assignment hits an unavailable slot
            if unavailable_slots:
                for p in s.occupied_periods:
                    if (day, p) in unavailable_slots:
                        violations.append(
                            WorkloadViolation(
                                violation_type=WorkloadViolationType.UNAVAILABLE_SLOT_VIOLATED,
                                severity="ERROR",
                                message=(
                                    f"Teacher {teacher_name} is scheduled during unavailable slot "
                                    f"Day {day}, Period {p}."
                                ),
                                teacher_id=teacher_id,
                                day=day,
                                period=p,
                                class_group_id=cid,
                            )
                        )

        # 2. Calculate consecutive periods observed per day
        max_consecutive_observed = 0
        for day, slots in daily_occupied_slots.items():
            if not slots:
                continue
            sorted_slots = sorted(set(slots))
            current_streak = 1
            day_max_consecutive = 1
            for i in range(1, len(sorted_slots)):
                if sorted_slots[i] == sorted_slots[i - 1] + 1:
                    current_streak += 1
                else:
                    current_streak = 1
                day_max_consecutive = max(day_max_consecutive, current_streak)

            max_consecutive_observed = max(max_consecutive_observed, day_max_consecutive)

            # Daily consecutive limit violation
            if day_max_consecutive > rule.max_consecutive_periods:
                violations.append(
                    WorkloadViolation(
                        violation_type=WorkloadViolationType.CONSECUTIVE_PERIODS_EXCEEDED,
                        severity="ERROR",
                        message=(
                            f"Teacher {teacher_name} teaches {day_max_consecutive} consecutive periods on "
                            f"Day {day}, exceeding the limit of {rule.max_consecutive_periods}."
                        ),
                        teacher_id=teacher_id,
                        day=day,
                        current_value=float(day_max_consecutive),
                        limit_value=float(rule.max_consecutive_periods),
                    )
                )

        # 3. Weekly period bounds checks
        is_overloaded = False
        is_underloaded = False

        if assigned_periods_per_week > rule.max_periods_per_week:
            is_overloaded = True
            violations.append(
                WorkloadViolation(
                    violation_type=WorkloadViolationType.WEEKLY_PERIODS_EXCEEDED,
                    severity="ERROR",
                    message=(
                        f"Assigned {assigned_periods_per_week} weekly periods, exceeding "
                        f"maximum allowance of {rule.max_periods_per_week}."
                    ),
                    teacher_id=teacher_id,
                    current_value=float(assigned_periods_per_week),
                    limit_value=float(rule.max_periods_per_week),
                )
            )

        if assigned_periods_per_week < rule.min_periods_per_week:
            is_underloaded = True
            violations.append(
                WorkloadViolation(
                    violation_type=WorkloadViolationType.WEEKLY_PERIODS_BELOW_MIN,
                    severity="WARNING",
                    message=(
                        f"Assigned {assigned_periods_per_week} weekly periods, below "
                        f"contractual minimum of {rule.min_periods_per_week}."
                    ),
                    teacher_id=teacher_id,
                    current_value=float(assigned_periods_per_week),
                    limit_value=float(rule.min_periods_per_week),
                )
            )

        # 4. Weekly contact hours / minutes checks
        assigned_contact_hours = round(assigned_contact_minutes / 60.0, 2)

        if rule.max_contact_minutes_per_week is not None and assigned_contact_minutes > rule.max_contact_minutes_per_week:
            max_hrs = round(rule.max_contact_minutes_per_week / 60.0, 2)
            violations.append(
                WorkloadViolation(
                    violation_type=WorkloadViolationType.WEEKLY_HOURS_EXCEEDED,
                    severity="ERROR",
                    message=(
                        f"Assigned {assigned_contact_hours} contact hours ({assigned_contact_minutes} mins), "
                        f"exceeding weekly contact hour limit of {max_hrs}h."
                    ),
                    teacher_id=teacher_id,
                    current_value=assigned_contact_hours,
                    limit_value=max_hrs,
                )
            )

        if rule.min_contact_minutes_per_week is not None and assigned_contact_minutes < rule.min_contact_minutes_per_week:
            min_hrs = round(rule.min_contact_minutes_per_week / 60.0, 2)
            violations.append(
                WorkloadViolation(
                    violation_type=WorkloadViolationType.WEEKLY_HOURS_BELOW_MIN,
                    severity="WARNING",
                    message=(
                        f"Assigned {assigned_contact_hours} contact hours ({assigned_contact_minutes} mins), "
                        f"below weekly minimum of {min_hrs}h."
                    ),
                    teacher_id=teacher_id,
                    current_value=assigned_contact_hours,
                    limit_value=min_hrs,
                )
            )

        # 5. Daily period and hours checks
        teaching_days_count = sum(1 for p in daily_periods.values() if p > 0)

        for day, p_count in daily_periods.items():
            if p_count > rule.max_periods_per_day:
                violations.append(
                    WorkloadViolation(
                        violation_type=WorkloadViolationType.DAILY_PERIODS_EXCEEDED,
                        severity="ERROR",
                        message=(
                            f"Assigned {p_count} periods on Day {day}, exceeding daily limit of {rule.max_periods_per_day}."
                        ),
                        teacher_id=teacher_id,
                        day=day,
                        current_value=float(p_count),
                        limit_value=float(rule.max_periods_per_day),
                    )
                )
            if p_count > 0 and rule.min_periods_per_day > 0 and p_count < rule.min_periods_per_day:
                violations.append(
                    WorkloadViolation(
                        violation_type=WorkloadViolationType.DAILY_PERIODS_BELOW_MIN,
                        severity="WARNING",
                        message=(
                            f"Assigned {p_count} periods on Day {day}, below daily minimum of {rule.min_periods_per_day}."
                        ),
                        teacher_id=teacher_id,
                        day=day,
                        current_value=float(p_count),
                        limit_value=float(rule.min_periods_per_day),
                    )
                )

            # Daily contact minutes limit
            day_mins = daily_contact_minutes.get(day, 0)
            if rule.max_contact_minutes_per_day is not None and day_mins > rule.max_contact_minutes_per_day:
                violations.append(
                    WorkloadViolation(
                        violation_type=WorkloadViolationType.DAILY_HOURS_EXCEEDED,
                        severity="ERROR",
                        message=(
                            f"Assigned {round(day_mins / 60.0, 1)}h on Day {day}, exceeding daily limit of "
                            f"{round(rule.max_contact_minutes_per_day / 60.0, 1)}h."
                        ),
                        teacher_id=teacher_id,
                        day=day,
                        current_value=round(day_mins / 60.0, 2),
                        limit_value=round(rule.max_contact_minutes_per_day / 60.0, 2),
                    )
                )

        # 6. Max working days check
        if rule.max_working_days is not None and teaching_days_count > rule.max_working_days:
            violations.append(
                WorkloadViolation(
                    violation_type=WorkloadViolationType.MAX_WORKING_DAYS_EXCEEDED,
                    severity="WARNING",
                    message=(
                        f"Teacher active on {teaching_days_count} days, exceeding maximum of {rule.max_working_days} days."
                    ),
                    teacher_id=teacher_id,
                    current_value=float(teaching_days_count),
                    limit_value=float(rule.max_working_days),
                )
            )

        # 7. Per-class limits check
        if rule.max_periods_per_class_per_week is not None:
            for cid, c_periods in class_wise_periods.items():
                if c_periods > rule.max_periods_per_class_per_week:
                    violations.append(
                        WorkloadViolation(
                            violation_type=WorkloadViolationType.CLASS_WEEKLY_PERIODS_EXCEEDED,
                            severity="WARNING",
                            message=(
                                f"Assigned {c_periods} weekly periods to class {cid}, exceeding limit of "
                                f"{rule.max_periods_per_class_per_week}."
                            ),
                            teacher_id=teacher_id,
                            class_group_id=cid,
                            current_value=float(c_periods),
                            limit_value=float(rule.max_periods_per_class_per_week),
                        )
                    )

        if rule.min_periods_per_class_per_week is not None:
            for cid, c_periods in class_wise_periods.items():
                if c_periods < rule.min_periods_per_class_per_week:
                    violations.append(
                        WorkloadViolation(
                            violation_type=WorkloadViolationType.CLASS_WEEKLY_PERIODS_BELOW_MIN,
                            severity="WARNING",
                            message=(
                                f"Assigned {c_periods} weekly periods to class {cid}, below required "
                                f"{rule.min_periods_per_class_per_week}."
                            ),
                            teacher_id=teacher_id,
                            class_group_id=cid,
                            current_value=float(c_periods),
                            limit_value=float(rule.min_periods_per_class_per_week),
                        )
                    )

        if rule.max_periods_per_class_per_day is not None:
            for (day, cid), count in daily_class_periods.items():
                if count > rule.max_periods_per_class_per_day:
                    violations.append(
                        WorkloadViolation(
                            violation_type=WorkloadViolationType.CLASS_DAILY_PERIODS_EXCEEDED,
                            severity="WARNING",
                            message=(
                                f"Assigned {count} periods on Day {day} to class {cid}, exceeding daily class limit "
                                f"of {rule.max_periods_per_class_per_day}."
                            ),
                            teacher_id=teacher_id,
                            day=day,
                            class_group_id=cid,
                            current_value=float(count),
                            limit_value=float(rule.max_periods_per_class_per_day),
                        )
                    )

        # 8. Subject specific limits check
        for sub_id, count in subject_wise_periods.items():
            if sub_id in rule.subject_limits and count > rule.subject_limits[sub_id]:
                limit = rule.subject_limits[sub_id]
                violations.append(
                    WorkloadViolation(
                        violation_type=WorkloadViolationType.SUBJECT_LIMIT_EXCEEDED,
                        severity="WARNING",
                        message=(
                            f"Assigned {count} periods for subject {sub_id}, exceeding limit of {limit}."
                        ),
                        teacher_id=teacher_id,
                        subject_id=sub_id,
                        current_value=float(count),
                        limit_value=float(limit),
                    )
                )

        remaining_capacity_periods = max(0, rule.max_periods_per_week - assigned_periods_per_week)
        remaining_capacity_hours = max(
            0.0,
            round(
                (rule.max_periods_per_week * standard_period_minutes - assigned_contact_minutes) / 60.0,
                2,
            ),
        )

        return TeacherWorkloadSummary(
            teacher_id=teacher_id,
            teacher_name=teacher_name,
            assigned_periods_per_week=assigned_periods_per_week,
            assigned_contact_hours_per_week=assigned_contact_hours,
            max_periods_allowed=rule.max_periods_per_week,
            min_periods_required=rule.min_periods_per_week,
            daily_periods=daily_periods,
            max_consecutive_observed=max_consecutive_observed,
            is_overloaded=is_overloaded,
            is_underloaded=is_underloaded,
            assigned_contact_minutes=assigned_contact_minutes,
            required_periods_per_week=rule.min_periods_per_week,
            remaining_capacity_periods=remaining_capacity_periods,
            remaining_capacity_hours=remaining_capacity_hours,
            teaching_days_count=teaching_days_count,
            assigned_classes_count=len(distinct_classes),
            daily_contact_minutes=daily_contact_minutes,
            subject_wise_periods=subject_wise_periods,
            class_wise_periods=class_wise_periods,
            violations=violations,
        )
