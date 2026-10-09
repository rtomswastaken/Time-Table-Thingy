"""CP-SAT constraint formulation for Timetable Thingy.

Builds decision variables and encodes hard constraints:
- Non-overlapping assignments for teachers, rooms, and classes.
- Consecutive period placement for multi-period labs/workshops.
- Teacher workload limits (weekly, daily, consecutive).
- Room suitability and capacity.
- Break period exclusion.
- Locked session preservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from core.models import (
    ClassGroup,
    Room,
    SchedulableUnit,
    SchedulingConfig,
    SchedulingInputBundle,
    Teacher,
    TeacherWorkloadRule,
)


@dataclass
class ModelVariables:
    """Container for CP-SAT decision variables and lookup indexes."""
    # x[unit_id, day, start_period, room_id] -> BoolVar
    unit_assignment_vars: Dict[Tuple[str, int, int, str], cp_model.BoolVar]
    
    # candidate_options[unit_id] -> list of (day, start_period, room_id)
    candidates_by_unit: Dict[str, List[Tuple[int, int, str]]]
    
    # teacher_slot_vars[teacher_id, day, period] -> list of BoolVar
    teacher_active_vars: Dict[Tuple[str, int, int], List[cp_model.BoolVar]]
    
    # room_slot_vars[room_id, day, period] -> list of BoolVar
    room_active_vars: Dict[Tuple[str, int, int], List[cp_model.BoolVar]]
    
    # class_slot_vars[class_id, day, period] -> list of (subgroup_id, BoolVar)
    class_active_vars: Dict[Tuple[str, int, int], List[Tuple[Optional[str], cp_model.BoolVar]]]


class ConstraintModelBuilder:
    """Builds variables and hard constraints in an OR-Tools CpModel."""

    def __init__(self, bundle: SchedulingInputBundle, config: SchedulingConfig) -> None:
        self.bundle = bundle
        self.config = config
        self.model = cp_model.CpModel()
        self.variables = ModelVariables(
            unit_assignment_vars={},
            candidates_by_unit={},
            teacher_active_vars={},
            room_active_vars={},
            class_active_vars={},
        )
        self.class_map: Dict[str, ClassGroup] = {c.id: c for c in bundle.class_groups}
        self.room_map: Dict[str, Room] = {r.id: r for r in bundle.rooms}
        self.teacher_map: Dict[str, Teacher] = {t.id: t for t in bundle.teachers}

    def build(self) -> Tuple[cp_model.CpModel, ModelVariables]:
        """Formulates the complete decision model with all hard constraints."""
        self._create_variables()
        self._add_exactly_one_assignment_per_unit()
        self._add_teacher_no_overlap_constraints()
        self._add_room_no_overlap_constraints()
        self._add_class_no_overlap_constraints()
        self._add_teacher_workload_constraints()
        self._add_subject_daily_spread_constraints()
        return self.model, self.variables

    def _create_variables(self) -> None:
        """Prunes domains and instantiates Boolean decision variables."""
        for unit in self.bundle.units:
            unit_id = unit.unit_id
            candidates: List[Tuple[int, int, str]] = []

            cg = self.class_map.get(unit.class_group_id)
            needed_capacity = cg.student_count if cg else 1

            for day in self.bundle.days:
                # Locked day check
                if unit.locked_day is not None and day != unit.locked_day:
                    continue

                for start_period in range(self.bundle.periods_per_day - unit.duration_periods + 1):
                    # Locked period check
                    if unit.locked_period is not None and start_period != unit.locked_period:
                        continue

                    occupied_periods = list(range(start_period, start_period + unit.duration_periods))

                    # Break period check
                    if any(p in self.bundle.break_periods for p in occupied_periods):
                        continue

                    # Teacher availability check
                    t_unavail = self.bundle.teacher_availability.get(unit.teacher_id, set())
                    if any((day, p) in t_unavail for p in occupied_periods):
                        continue

                    if unit.secondary_teacher_id:
                        sec_unavail = self.bundle.teacher_availability.get(unit.secondary_teacher_id, set())
                        if any((day, p) in sec_unavail for p in occupied_periods):
                            continue

                    # Filter candidate rooms
                    for room in self.bundle.rooms:
                        # Locked room check
                        if unit.locked_room_id is not None and room.id != unit.locked_room_id:
                            continue

                        # Room type check
                        if unit.required_room_type is not None and room.room_type != unit.required_room_type:
                            continue

                        # Capacity check
                        if room.capacity < needed_capacity:
                            continue

                        # Room availability check
                        r_unavail = self.bundle.room_availability.get(room.id, set())
                        if any((day, p) in r_unavail for p in occupied_periods):
                            continue

                        # Valid candidate assignment found!
                        candidates.append((day, start_period, room.id))
                        var_name = f"x_{unit_id}_{day}_{start_period}_{room.id}"
                        var = self.model.NewBoolVar(var_name)
                        self.variables.unit_assignment_vars[(unit_id, day, start_period, room.id)] = var

                        # Register in active lookup maps for quick conflict indexing
                        for p in occupied_periods:
                            # Primary teacher
                            self.variables.teacher_active_vars.setdefault((unit.teacher_id, day, p), []).append(var)
                            # Secondary teacher (if any)
                            if unit.secondary_teacher_id:
                                self.variables.teacher_active_vars.setdefault((unit.secondary_teacher_id, day, p), []).append(var)
                            # Room
                            self.variables.room_active_vars.setdefault((room.id, day, p), []).append(var)
                            # Class
                            self.variables.class_active_vars.setdefault((unit.class_group_id, day, p), []).append((unit.student_group_id, var))

            self.variables.candidates_by_unit[unit_id] = candidates

    def _add_exactly_one_assignment_per_unit(self) -> None:
        """Every schedulable unit must be assigned to exactly one candidate slot & room."""
        for unit in self.bundle.units:
            candidates = self.variables.candidates_by_unit.get(unit.unit_id, [])
            if not candidates:
                # Impossible configuration: force model infeasibility
                dummy = self.model.NewBoolVar(f"impossible_{unit.unit_id}")
                self.model.Add(dummy == 0)
                self.model.Add(dummy == 1)
                continue

            assignment_vars = [
                self.variables.unit_assignment_vars[(unit.unit_id, day, period, room_id)]
                for (day, period, room_id) in candidates
            ]
            self.model.AddExactlyOne(assignment_vars)

    def _add_teacher_no_overlap_constraints(self) -> None:
        """A teacher cannot teach two sessions simultaneously."""
        for (t_id, day, p), vars_list in self.variables.teacher_active_vars.items():
            if len(vars_list) > 1:
                self.model.Add(sum(vars_list) <= 1)

    def _add_room_no_overlap_constraints(self) -> None:
        """A room cannot host two sessions simultaneously."""
        for (r_id, day, p), vars_list in self.variables.room_active_vars.items():
            if len(vars_list) > 1:
                self.model.Add(sum(vars_list) <= 1)

    def _add_class_no_overlap_constraints(self) -> None:
        """A class cohort cannot attend conflicting sessions simultaneously."""
        for (cg_id, day, p), items in self.variables.class_active_vars.items():
            if len(items) <= 1:
                continue

            # Check if all items are whole-class (subgroup is None)
            whole_class_vars = [var for (sg_id, var) in items if sg_id is None]
            batch_vars_by_group: Dict[str, List[cp_model.BoolVar]] = {}
            for sg_id, var in items:
                if sg_id is not None:
                    batch_vars_by_group.setdefault(sg_id, []).append(var)

            if not batch_vars_by_group:
                # All whole-class
                self.model.Add(sum(whole_class_vars) <= 1)
            else:
                # For every batch, sum(whole_class + this_batch) <= 1
                for sg_id, b_vars in batch_vars_by_group.items():
                    self.model.Add(sum(whole_class_vars + b_vars) <= 1)
                # And whole class sessions themselves cannot overlap
                if len(whole_class_vars) > 1:
                    self.model.Add(sum(whole_class_vars) <= 1)

    def _add_teacher_workload_constraints(self) -> None:
        """Enforces teacher workload rules: weekly max/min, daily max, and consecutive periods."""
        for t_id, rule in self.bundle.teacher_workload_rules.items():
            # 1. Weekly max/min periods
            all_unit_vars_for_teacher: List[Tuple[int, cp_model.BoolVar]] = []
            for unit in self.bundle.units:
                if unit.teacher_id == t_id or unit.secondary_teacher_id == t_id:
                    for (day, period, room_id) in self.variables.candidates_by_unit.get(unit.unit_id, []):
                        var = self.variables.unit_assignment_vars[(unit.unit_id, day, period, room_id)]
                        all_unit_vars_for_teacher.append((unit.duration_periods, var))

            if all_unit_vars_for_teacher:
                total_weekly_periods = sum(dur * var for dur, var in all_unit_vars_for_teacher)
                if rule.max_periods_per_week is not None:
                    self.model.Add(total_weekly_periods <= rule.max_periods_per_week)
                if rule.min_periods_per_week is not None and rule.min_periods_per_week > 0:
                    self.model.Add(total_weekly_periods >= rule.min_periods_per_week)

            # 2. Daily max periods
            for day in self.bundle.days:
                day_vars: List[Tuple[int, cp_model.BoolVar]] = []
                for unit in self.bundle.units:
                    if unit.teacher_id == t_id or unit.secondary_teacher_id == t_id:
                        for (d, period, room_id) in self.variables.candidates_by_unit.get(unit.unit_id, []):
                            if d == day:
                                var = self.variables.unit_assignment_vars[(unit.unit_id, d, period, room_id)]
                                day_vars.append((unit.duration_periods, var))

                if day_vars and rule.max_periods_per_day is not None:
                    self.model.Add(sum(dur * var for dur, var in day_vars) <= rule.max_periods_per_day)

            # 3. Consecutive teaching periods limit
            C = rule.max_consecutive_periods
            if C is not None and C < self.bundle.periods_per_day:
                window_size = C + 1
                for day in self.bundle.days:
                    for start_p in range(self.bundle.periods_per_day - window_size + 1):
                        # Periods in this window: start_p .. start_p + C
                        window_slot_vars: List[cp_model.BoolVar] = []
                        for p in range(start_p, start_p + window_size):
                            # The teacher is active at (day, p) if any session covering p is selected
                            active_at_p = self.variables.teacher_active_vars.get((t_id, day, p), [])
                            if active_at_p:
                                # Create or reuse indicator for whether teacher teaches at (day, p)
                                # Since sum(active_at_p) <= 1, sum(active_at_p) represents the binary active state!
                                window_slot_vars.extend(active_at_p)

                        if window_slot_vars:
                            # In any window of size C + 1, total teaching periods <= C
                            self.model.Add(sum(window_slot_vars) <= C)

    def _add_subject_daily_spread_constraints(self) -> None:
        """Prevents cramming too many sessions of the same subject on a single day for a class."""
        # Group units by (class_group_id, subject_id)
        class_subject_units: Dict[Tuple[str, str], List[SchedulableUnit]] = {}
        for unit in self.bundle.units:
            class_subject_units.setdefault((unit.class_group_id, unit.subject_id), []).append(unit)

        for (cg_id, sub_id), units in class_subject_units.items():
            if len(units) <= 1:
                continue

            # Limit sessions of this subject to at most 2 per day (or 1 if total periods <= days)
            max_sessions_per_day = 2 if len(units) > len(self.bundle.days) else 1

            for day in self.bundle.days:
                day_units_vars: List[cp_model.BoolVar] = []
                for unit in units:
                    for (d, p, r_id) in self.variables.candidates_by_unit.get(unit.unit_id, []):
                        if d == day:
                            day_units_vars.append(self.variables.unit_assignment_vars[(unit.unit_id, d, p, r_id)])

                if len(day_units_vars) > max_sessions_per_day:
                    self.model.Add(sum(day_units_vars) <= max_sessions_per_day)
