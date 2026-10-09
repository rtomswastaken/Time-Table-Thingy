"""Soft Preferences and Timetable Preference Scoring Engine.

Manages soft teacher preferences and evaluates scheduled sessions against them,
computing structured penalties and satisfaction rates for Agent 5 (Solver)
and institutional analytics.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from core.models import Institution, ScheduledSession, TeacherPreference as CoreTeacherPreference
from workload.models import (
    DetailedTeacherPreference,
    PreferenceEvaluationItem,
    PreferenceEvaluationReport,
    SoftPreferenceType,
)


class PreferenceManager:
    """Manages teacher soft preferences and evaluates timetable quality against them."""

    def __init__(self) -> None:
        # teacher_id -> list of DetailedTeacherPreference
        self._preferences: Dict[str, List[DetailedTeacherPreference]] = {}
        # teacher_id -> (day, period) -> weight (-10..+10) for core model compatibility
        self._slot_weights: Dict[str, Dict[Tuple[int, int], int]] = {}

    def add_preference(self, preference: DetailedTeacherPreference) -> None:
        """Registers a soft preference for a teacher."""
        if preference.teacher_id not in self._preferences:
            self._preferences[preference.teacher_id] = []
        self._preferences[preference.teacher_id].append(preference)

    def set_preferences(
        self, teacher_id: str, preferences: List[DetailedTeacherPreference]
    ) -> None:
        """Replaces all soft preferences for a teacher."""
        self._preferences[teacher_id] = list(preferences)

    def get_preferences(self, teacher_id: str) -> List[DetailedTeacherPreference]:
        """Returns active soft preferences for a teacher."""
        return list(self._preferences.get(teacher_id, []))

    def set_slot_weights(
        self, teacher_id: str, slot_weights: Dict[Tuple[int, int], int]
    ) -> None:
        """Sets raw slot preferences (-10 to +10) for direct solver matrix export."""
        for (day, period), weight in slot_weights.items():
            if not -10 <= weight <= 10:
                raise ValidationError(
                    f"Slot preference weight for ({day}, {period}) must be between -10 and +10, got {weight}."
                )
        self._slot_weights[teacher_id] = dict(slot_weights)

    def get_slot_weights(self, teacher_id: str) -> Dict[Tuple[int, int], int]:
        """Returns slot weights map for a teacher."""
        return dict(self._slot_weights.get(teacher_id, {}))

    def build_solver_slot_preference_matrix(
        self,
        teacher_id: str,
        institution: Institution,
    ) -> Dict[Tuple[int, int], int]:
        """Combines discrete slot weights and high-level preferences into a unified

        (day, period) -> weight (-10..+10) map for Agent 5 solver.
        """
        matrix: Dict[Tuple[int, int], int] = dict(self._slot_weights.get(teacher_id, {}))

        prefs = self._preferences.get(teacher_id, [])
        half_day = institution.periods_per_day // 2

        for pref in prefs:
            if not pref.is_active:
                continue

            # Normalized 1..10 weight mapped into preference adjustment
            scaled_impact = max(1, min(10, pref.weight))

            if pref.preference_type == SoftPreferenceType.PREFER_MORNING:
                for day in institution.working_days:
                    for p in range(half_day):
                        matrix[(day, p)] = min(10, matrix.get((day, p), 0) + int(scaled_impact * 0.8))
                    for p in range(half_day, institution.periods_per_day):
                        matrix[(day, p)] = max(-10, matrix.get((day, p), 0) - int(scaled_impact * 0.5))

            elif pref.preference_type == SoftPreferenceType.AVOID_FINAL_PERIOD:
                last_p = institution.periods_per_day - 1
                for day in institution.working_days:
                    matrix[(day, last_p)] = max(-10, matrix.get((day, last_p), 0) - scaled_impact)

            elif pref.preference_type == SoftPreferenceType.PREFER_DAYS:
                preferred_days = set(pref.target_value or [])
                for day in preferred_days:
                    for p in range(institution.periods_per_day):
                        matrix[(day, p)] = min(10, matrix.get((day, p), 0) + int(scaled_impact * 0.5))

            elif pref.preference_type == SoftPreferenceType.AVOID_DAYS:
                avoided_days = set(pref.target_value or [])
                for day in avoided_days:
                    for p in range(institution.periods_per_day):
                        matrix[(day, p)] = max(-10, matrix.get((day, p), 0) - scaled_impact)

            elif pref.preference_type == SoftPreferenceType.SLOT_PREFERENCE:
                if isinstance(pref.target_value, tuple) and len(pref.target_value) == 2:
                    day, period = pref.target_value
                    matrix[(day, period)] = max(-10, min(10, matrix.get((day, period), 0) + pref.weight))

        return matrix

    def evaluate_preferences(
        self,
        teacher_id: str,
        sessions: List[ScheduledSession],
        institution: Institution,
    ) -> PreferenceEvaluationReport:
        """Evaluates a teacher's schedule against all registered soft preferences.

        Returns structured evaluation results, satisfaction scores, penalties, and explanations.
        """
        teacher_sessions = [s for s in sessions if s.teacher_id == teacher_id]
        prefs = self._preferences.get(teacher_id, [])

        # Build day -> list of occupied periods
        day_periods: Dict[int, List[int]] = {day: [] for day in institution.working_days}
        day_sessions: Dict[int, List[ScheduledSession]] = {day: [] for day in institution.working_days}
        for s in teacher_sessions:
            if s.day_of_week in day_periods:
                day_periods[s.day_of_week].extend(s.occupied_periods)
                day_sessions[s.day_of_week].append(s)

        for day in day_periods:
            day_periods[day].sort()

        evaluation_items: List[PreferenceEvaluationItem] = []
        total_penalty = 0.0
        total_possible_weight = 0.0
        earned_satisfaction_weight = 0.0

        for pref in prefs:
            if not pref.is_active:
                continue

            item = self._evaluate_single_preference(
                pref=pref,
                day_periods=day_periods,
                day_sessions=day_sessions,
                institution=institution,
            )
            evaluation_items.append(item)
            total_penalty += item.penalty_incurred
            total_possible_weight += pref.weight
            earned_satisfaction_weight += item.satisfaction_score * pref.weight

        # Also evaluate explicit slot preferences
        slot_matrix = self._slot_weights.get(teacher_id, {})
        for (day, p), weight in slot_matrix.items():
            if weight == 0:
                continue
            is_occupied = p in day_periods.get(day, [])
            abs_weight = abs(weight)
            total_possible_weight += abs_weight

            if weight > 0:  # Preferred slot
                if is_occupied:
                    score = 1.0
                    penalty = 0.0
                    msg = f"Teacher scheduled in preferred slot Day {day}, Period {p}."
                else:
                    score = 0.0
                    penalty = float(weight)
                    msg = f"Teacher was not scheduled in preferred slot Day {day}, Period {p}."
            else:  # Avoided slot
                if is_occupied:
                    score = 0.0
                    penalty = float(abs_weight)
                    msg = f"Teacher scheduled in avoided slot Day {day}, Period {p}."
                else:
                    score = 1.0
                    penalty = 0.0
                    msg = f"Teacher avoided undesirable slot Day {day}, Period {p}."

            earned_satisfaction_weight += score * abs_weight
            total_penalty += penalty
            evaluation_items.append(
                PreferenceEvaluationItem(
                    preference_id=f"slot_{day}_{p}",
                    preference_type=SoftPreferenceType.SLOT_PREFERENCE.value,
                    is_satisfied=(score >= 0.99),
                    satisfaction_score=score,
                    penalty_incurred=penalty,
                    weight_applied=abs_weight,
                    involved_sessions=[
                        s.id for s in day_sessions.get(day, []) if p in s.occupied_periods
                    ],
                    explanation=msg,
                )
            )

        overall_satisfaction = (
            earned_satisfaction_weight / total_possible_weight
            if total_possible_weight > 0
            else 1.0
        )

        return PreferenceEvaluationReport(
            teacher_id=teacher_id,
            total_penalty=round(total_penalty, 2),
            satisfaction_rate=round(overall_satisfaction, 4),
            items=evaluation_items,
        )

    def _evaluate_single_preference(
        self,
        pref: DetailedTeacherPreference,
        day_periods: Dict[int, List[int]],
        day_sessions: Dict[int, List[ScheduledSession]],
        institution: Institution,
    ) -> PreferenceEvaluationItem:
        """Evaluates one detailed soft preference against teacher schedule."""
        weight = pref.weight
        ptype = pref.preference_type

        if ptype == SoftPreferenceType.PREFER_MORNING:
            half_day = institution.periods_per_day // 2
            total_periods = sum(len(periods) for periods in day_periods.values())
            if total_periods == 0:
                score = 1.0
                msg = "No classes assigned."
            else:
                morning_periods = sum(
                    sum(1 for p in periods if p < half_day)
                    for periods in day_periods.values()
                )
                score = morning_periods / total_periods
                msg = f"{morning_periods}/{total_periods} periods scheduled in morning."

        elif ptype == SoftPreferenceType.AVOID_FINAL_PERIOD:
            last_p = institution.periods_per_day - 1
            final_period_hits = sum(
                1 for periods in day_periods.values() if last_p in periods
            )
            working_days_count = sum(1 for periods in day_periods.values() if len(periods) > 0)
            if working_days_count == 0 or final_period_hits == 0:
                score = 1.0
                msg = "No classes in final period."
            else:
                score = max(0.0, 1.0 - (final_period_hits / working_days_count))
                msg = f"Assigned to final period on {final_period_hits} days."

        elif ptype == SoftPreferenceType.PREFER_DAYS:
            preferred_days = set(pref.target_value or [])
            total_assigned = sum(len(p) for p in day_periods.values())
            if total_assigned == 0 or not preferred_days:
                score = 1.0
                msg = "Satisfied."
            else:
                in_pref_days = sum(len(day_periods.get(d, [])) for d in preferred_days)
                score = in_pref_days / total_assigned
                msg = f"{in_pref_days}/{total_assigned} periods in preferred days."

        elif ptype == SoftPreferenceType.AVOID_DAYS:
            avoided_days = set(pref.target_value or [])
            total_assigned = sum(len(p) for p in day_periods.values())
            if total_assigned == 0 or not avoided_days:
                score = 1.0
                msg = "Satisfied."
            else:
                in_avoided = sum(len(day_periods.get(d, [])) for d in avoided_days)
                score = max(0.0, 1.0 - (in_avoided / total_assigned))
                msg = f"{in_avoided} periods scheduled on avoided days."

        elif ptype == SoftPreferenceType.MINIMIZE_GAPS:
            # Gaps are idle periods between the first and last period of a day
            total_gaps = 0
            for day, periods in day_periods.items():
                if len(periods) >= 2:
                    span = max(periods) - min(periods) + 1
                    gaps = span - len(set(periods))
                    total_gaps += max(0, gaps)
            if total_gaps == 0:
                score = 1.0
                msg = "No idle gaps between teaching sessions."
            else:
                score = max(0.0, 1.0 - (total_gaps * 0.25))
                msg = f"{total_gaps} idle gap periods detected."

        elif ptype == SoftPreferenceType.PREFER_CONSECUTIVE:
            # Rewards having contiguous blocks rather than isolated single periods
            singletons = 0
            for day, periods in day_periods.items():
                if len(periods) == 1:
                    singletons += 1
                elif len(periods) > 1:
                    for i, p in enumerate(periods):
                        prev_c = (i > 0 and periods[i - 1] == p - 1)
                        next_c = (i < len(periods) - 1 and periods[i + 1] == p + 1)
                        if not prev_c and not next_c:
                            singletons += 1
            if singletons == 0:
                score = 1.0
                msg = "All sessions are consecutive."
            else:
                score = max(0.0, 1.0 - (singletons * 0.2))
                msg = f"{singletons} isolated non-consecutive periods."

        elif ptype == SoftPreferenceType.MINIMIZE_WORKING_DAYS:
            active_days = sum(1 for periods in day_periods.values() if len(periods) > 0)
            target_days = pref.target_value or 3
            if active_days <= target_days:
                score = 1.0
                msg = f"Teacher active on {active_days} days (target <= {target_days})."
            else:
                score = max(0.0, 1.0 - ((active_days - target_days) * 0.5))
                msg = f"Teacher scheduled on {active_days} days (target {target_days})."

        elif ptype == SoftPreferenceType.TARGET_DAILY_WORKLOAD:
            target = pref.target_value or 3
            deviations = [
                abs(len(periods) - target)
                for periods in day_periods.values()
                if len(periods) > 0
            ]
            if not deviations:
                score = 1.0
                msg = "No classes assigned."
            else:
                avg_dev = sum(deviations) / len(deviations)
                score = max(0.0, 1.0 - (avg_dev * 0.25))
                msg = f"Average daily load deviation from target {target} is {avg_dev:.1f} periods."

        elif ptype == SoftPreferenceType.DISTRIBUTE_EVENLY:
            loads = [len(p) for p in day_periods.values() if len(p) > 0]
            if len(loads) <= 1:
                score = 1.0
                msg = "Evenly distributed."
            else:
                mean = sum(loads) / len(loads)
                variance = sum((x - mean) ** 2 for x in loads) / len(loads)
                std_dev = math.sqrt(variance)
                score = max(0.0, 1.0 - (std_dev * 0.25))
                msg = f"Daily workload standard deviation is {std_dev:.2f} periods."

        elif ptype == SoftPreferenceType.AVOID_SINGLE_SESSIONS:
            single_session_days = sum(
                1 for periods in day_periods.values() if len(periods) == 1
            )
            if single_session_days == 0:
                score = 1.0
                msg = "No isolated single-session days."
            else:
                score = max(0.0, 1.0 - (single_session_days * 0.3))
                msg = f"{single_session_days} days with only a single teaching period."

        else:
            score = 1.0
            msg = "Custom preference evaluated as satisfied."

        penalty = round((1.0 - score) * weight, 2)
        all_involved = [s.id for day_s in day_sessions.values() for s in day_s]

        return PreferenceEvaluationItem(
            preference_id=pref.id,
            preference_type=ptype.value,
            is_satisfied=(score >= 0.9),
            satisfaction_score=round(score, 4),
            penalty_incurred=penalty,
            weight_applied=weight,
            involved_sessions=all_involved,
            explanation=msg,
        )

    def to_core_preferences(self, teacher_id: str) -> List[CoreTeacherPreference]:
        """Converts slot matrix preferences into a list of CoreTeacherPreference models."""
        matrix = self._slot_weights.get(teacher_id, {})
        records = []
        for (day, period), weight in matrix.items():
            records.append(
                CoreTeacherPreference(
                    teacher_id=teacher_id,
                    day_of_week=day,
                    period_index=period,
                    preference_weight=weight,
                )
            )
        return records
