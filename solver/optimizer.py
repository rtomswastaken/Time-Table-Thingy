"""Soft preference optimization and objective formulation for Timetable Thingy.

Encodes multi-criteria objective terms into the CP-SAT model:
- Teacher temporal preferences (positive weights reward preferred slots, negative penalize disliked slots)
- Idle gap minimization for teachers and students
- Room suitability and home-room preference
- Subject distribution and workload balancing across the week
- Schedule stability when regenerating or modifying an existing schedule
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from core.models import (
    RoomType,
    SchedulableUnit,
    SchedulingConfig,
    SchedulingInputBundle,
    SessionType,
)
from solver.constraints import ModelVariables


class ObjectiveOptimizer:
    """Encodes weighted soft preferences and registers the objective function with CP-SAT."""

    @classmethod
    def apply_objective(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        baseline_assignments: Optional[Dict[str, Tuple[int, int, str]]] = None,
    ) -> None:
        """Constructs the total penalty expression and sets model.Minimize()."""
        penalties: List[cp_model.LinearExpr] = []

        # 1. Teacher Time-Slot Preferences
        cls._add_teacher_preference_terms(model, bundle, config, variables, penalties)

        # 2. Preferred Room & Specialist Conservation
        cls._add_room_preference_terms(model, bundle, config, variables, penalties)

        # 3. Balanced Subject Distribution Across Week
        cls._add_subject_distribution_terms(model, bundle, config, variables, penalties)

        # 4. Teacher Idle Gap Minimization
        cls._add_teacher_gap_terms(model, bundle, config, variables, penalties)

        # 5. Student Idle Gap Minimization
        cls._add_student_gap_terms(model, bundle, config, variables, penalties)

        # 6. Schedule Stability (if baseline provided)
        if baseline_assignments:
            cls._add_stability_terms(model, bundle, config, variables, baseline_assignments, penalties)

        if penalties:
            model.Minimize(sum(penalties))
        else:
            model.Minimize(0)

    @classmethod
    def _add_teacher_preference_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Rewards positive teacher preferences and penalizes disliked slots."""
        weight_factor = max(1, config.weight_teacher_preference)

        for unit in bundle.units:
            prefs = bundle.teacher_preferences.get(unit.teacher_id, {})
            if not prefs:
                continue

            for (day, start_p, r_id) in variables.candidates_by_unit.get(unit.unit_id, []):
                var = variables.unit_assignment_vars[(unit.unit_id, day, start_p, r_id)]
                # Check preferences for all occupied periods
                occupied = range(start_p, start_p + unit.duration_periods)
                total_unit_pref_score = sum(prefs.get((day, p), 0) for p in occupied)

                if total_unit_pref_score != 0:
                    # In CP-SAT, we minimize penalty:
                    # Positive preference -> negative penalty (reward)
                    # Negative preference -> positive penalty
                    penalty_coef = -int(total_unit_pref_score * weight_factor)
                    penalties.append(penalty_coef * var)

    @classmethod
    def _add_room_preference_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Penalizes assigning non-home rooms or unnecessarily consuming specialist labs."""
        weight_factor = max(1, config.weight_preferred_room)
        class_map = {c.id: c for c in bundle.class_groups}
        room_map = {r.id: r for r in bundle.rooms}

        for unit in bundle.units:
            cg = class_map.get(unit.class_group_id)
            home_room_id = cg.home_room_id if cg else None

            for (day, start_p, r_id) in variables.candidates_by_unit.get(unit.unit_id, []):
                var = variables.unit_assignment_vars[(unit.unit_id, day, start_p, r_id)]
                room = room_map.get(r_id)
                if not room:
                    continue

                cost = 0
                # Penalize non-home room if home room is configured and session is general theory
                if home_room_id and unit.session_type == SessionType.THEORY and r_id != home_room_id:
                    cost += 2 * weight_factor

                # Conservation of scarce specialist labs:
                # Do not assign Computer Lab / Hardware Lab for general lectures if not requested
                if unit.required_room_type is None and room.room_type in (RoomType.COMPUTER_LAB, RoomType.HARDWARE_LAB, RoomType.WORKSHOP):
                    cost += 5 * weight_factor

                if cost > 0:
                    penalties.append(cost * var)

    @classmethod
    def _add_subject_distribution_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Spreads multiple sessions of the same subject across different working days."""
        weight_factor = max(1, config.weight_balanced_daily_load)

        # Group units by (class_group_id, subject_id)
        class_sub_map: Dict[Tuple[str, str], List[SchedulableUnit]] = {}
        for unit in bundle.units:
            class_sub_map.setdefault((unit.class_group_id, unit.subject_id), []).append(unit)

        for (cg_id, sub_id), units in class_sub_map.items():
            if len(units) <= 1:
                continue

            # For each day, if more than 1 session occurs on that day, add penalty
            for day in bundle.days:
                day_vars: List[cp_model.BoolVar] = []
                for unit in units:
                    for (d, p, r_id) in variables.candidates_by_unit.get(unit.unit_id, []):
                        if d == day:
                            day_vars.append(variables.unit_assignment_vars[(unit.unit_id, d, p, r_id)])

                if len(day_vars) > 1:
                    # Penalize multiple sessions on same day
                    # excess_sessions = sum(day_vars) - 1 if sum(day_vars) >= 1
                    # A simple linear surrogate: sum(day_vars) contributes (len - 1)*cost when > 1
                    penalties.append(weight_factor * sum(day_vars))

    @classmethod
    def _add_teacher_gap_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Minimizes idle waiting periods between classes for teachers."""
        gap_weight = max(1, config.weight_minimize_teacher_gaps)

        for teacher in bundle.teachers:
            t_id = teacher.id
            for day in bundle.days:
                # Active indicator for each period p
                period_indicators: Dict[int, cp_model.IntVar] = {}
                for p in range(bundle.periods_per_day):
                    active_vars = variables.teacher_active_vars.get((t_id, day, p), [])
                    if active_vars:
                        # sum(active_vars) is in {0, 1}
                        ind = model.NewBoolVar(f"t_act_{t_id}_{day}_{p}")
                        model.Add(ind == sum(active_vars))
                        period_indicators[p] = ind

                if len(period_indicators) < 2:
                    continue

                # Check for potential middle gaps: period p is free, but earlier and later are active
                for p in range(1, bundle.periods_per_day - 1):
                    if p in bundle.break_periods:
                        continue

                    earlier_slots = [period_indicators[ep] for ep in period_indicators if ep < p]
                    later_slots = [period_indicators[lp] for lp in period_indicators if lp > p]

                    if not earlier_slots or not later_slots:
                        continue

                    # Teacher has early class today
                    has_earlier = model.NewBoolVar(f"t_earlier_{t_id}_{day}_{p}")
                    model.AddMaxEquality(has_earlier, earlier_slots)

                    # Teacher has later class today
                    has_later = model.NewBoolVar(f"t_later_{t_id}_{day}_{p}")
                    model.AddMaxEquality(has_later, later_slots)

                    # Is teacher active at period p?
                    is_active_p = period_indicators.get(p)

                    # Gap exists if has_earlier=1, has_later=1, and is_active_p=0
                    is_gap = model.NewBoolVar(f"t_gap_{t_id}_{day}_{p}")
                    if is_active_p is not None:
                        model.Add(is_gap >= has_earlier + has_later - 1 - is_active_p)
                    else:
                        model.Add(is_gap >= has_earlier + has_later - 1)

                    penalties.append(gap_weight * is_gap)

    @classmethod
    def _add_student_gap_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Minimizes idle holes in the daily schedule of student cohorts."""
        gap_weight = max(1, config.weight_minimize_student_gaps)

        for cg in bundle.class_groups:
            cg_id = cg.id
            for day in bundle.days:
                period_indicators: Dict[int, cp_model.IntVar] = {}
                for p in range(bundle.periods_per_day):
                    active_items = variables.class_active_vars.get((cg_id, day, p), [])
                    if active_items:
                        vars_at_p = [var for (_, var) in active_items]
                        ind = model.NewBoolVar(f"cg_act_{cg_id}_{day}_{p}")
                        # If any session active for this class at p, ind = 1
                        model.AddMaxEquality(ind, vars_at_p)
                        period_indicators[p] = ind

                if len(period_indicators) < 2:
                    continue

                for p in range(1, bundle.periods_per_day - 1):
                    if p in bundle.break_periods:
                        continue

                    earlier_slots = [period_indicators[ep] for ep in period_indicators if ep < p]
                    later_slots = [period_indicators[lp] for lp in period_indicators if lp > p]

                    if not earlier_slots or not later_slots:
                        continue

                    has_earlier = model.NewBoolVar(f"cg_earlier_{cg_id}_{day}_{p}")
                    model.AddMaxEquality(has_earlier, earlier_slots)

                    has_later = model.NewBoolVar(f"cg_later_{cg_id}_{day}_{p}")
                    model.AddMaxEquality(has_later, later_slots)

                    is_active_p = period_indicators.get(p)
                    is_gap = model.NewBoolVar(f"cg_gap_{cg_id}_{day}_{p}")
                    if is_active_p is not None:
                        model.Add(is_gap >= has_earlier + has_later - 1 - is_active_p)
                    else:
                        model.Add(is_gap >= has_earlier + has_later - 1)

                    penalties.append(gap_weight * is_gap)

    @classmethod
    def _add_stability_terms(
        cls,
        model: cp_model.CpModel,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        variables: ModelVariables,
        baseline_assignments: Dict[str, Tuple[int, int, str]],
        penalties: List[cp_model.LinearExpr],
    ) -> None:
        """Penalizes moving sessions away from an existing baseline draft during partial regeneration."""
        stability_penalty = 50  # Strong penalty for moving unpinned sessions

        for unit in bundle.units:
            if unit.unit_id not in baseline_assignments:
                continue

            base_day, base_period, base_room = baseline_assignments[unit.unit_id]
            for (day, period, room_id) in variables.candidates_by_unit.get(unit.unit_id, []):
                var = variables.unit_assignment_vars[(unit.unit_id, day, period, room_id)]
                if (day, period, room_id) != (base_day, base_period, base_room):
                    penalties.append(stability_penalty * var)
