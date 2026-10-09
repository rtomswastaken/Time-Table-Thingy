"""Solution extraction, metrics calculation, alternatives, and partial regeneration.

Handles mapping OR-Tools CP-SAT solutions into domain entities, calculating
optimization quality metrics, and orchestrating alternative generation and partial regeneration.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from core.models import (
    ConstraintViolation,
    OptimizationMetrics,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SchedulingStatus,
)
from solver.constraints import ConstraintModelBuilder, ModelVariables
from solver.optimizer import ObjectiveOptimizer
from solver.validator import DeterministicScheduleValidator


class ResultBuilder:
    """Extracts solutions and constructs SchedulingResult records."""

    @classmethod
    def extract_sessions(
        cls,
        solver: cp_model.CpSolver,
        bundle: SchedulingInputBundle,
        variables: ModelVariables,
    ) -> List[ScheduledSession]:
        """Extracts scheduled sessions from a solved CP-SAT model."""
        sessions: List[ScheduledSession] = []

        for unit in bundle.units:
            candidates = variables.candidates_by_unit.get(unit.unit_id, [])
            for (day, period, room_id) in candidates:
                var = variables.unit_assignment_vars[(unit.unit_id, day, period, room_id)]
                if solver.Value(var) == 1:
                    is_locked = (unit.locked_day is not None and unit.locked_period is not None)
                    session = ScheduledSession(
                        id=unit.unit_id,
                        timetable_id=bundle.academic_year_id,
                        class_subject_assignment_id=unit.assignment_id,
                        day_of_week=day,
                        start_period=period,
                        duration_periods=unit.duration_periods,
                        room_id=room_id,
                        teacher_id=unit.teacher_id,
                        class_group_id=unit.class_group_id,
                        secondary_teacher_id=unit.secondary_teacher_id,
                        student_group_id=unit.student_group_id,
                        is_locked=is_locked,
                    )
                    sessions.append(session)
                    break

        return sessions

    @classmethod
    def build_result(
        cls,
        status: SchedulingStatus,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        violations: Optional[List[ConstraintViolation]] = None,
        runtime_seconds: float = 0.0,
        message: str = "",
    ) -> SchedulingResult:
        """Constructs a validated SchedulingResult with optimization metrics."""
        validator = DeterministicScheduleValidator()

        if sessions:
            validation_violations = validator.validate(sessions, bundle)
            combined_violations = list(violations or []) + validation_violations
            # Deduplicate violations by message
            seen_msgs = set()
            unique_violations: List[ConstraintViolation] = []
            for v in combined_violations:
                if v.message not in seen_msgs:
                    seen_msgs.add(v.message)
                    unique_violations.append(v)

            # Check if any hard violation exists in what was claimed to be feasible/optimal
            if any(v.is_hard for v in unique_violations) and status in (SchedulingStatus.OPTIMAL, SchedulingStatus.FEASIBLE):
                status = SchedulingStatus.INFEASIBLE

            metrics = validator.calculate_metrics(sessions, bundle, config, runtime_seconds)
        else:
            unique_violations = list(violations or [])
            metrics = None

        return SchedulingResult(
            status=status,
            sessions=sessions,
            violations=unique_violations,
            metrics=metrics,
            execution_time_seconds=round(runtime_seconds, 3),
            message=message,
        )


class AlternativeSolutionGenerator:
    """Finds multiple distinct, valid timetables for comparison."""

    @classmethod
    def generate_alternatives(
        cls,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        count: int = 3,
        solver_fn: Optional[Callable[..., SchedulingResult]] = None,
    ) -> List[SchedulingResult]:
        """Generates up to `count` distinct alternative valid timetables."""
        if count < 1:
            return []

        results: List[SchedulingResult] = []
        builder = ConstraintModelBuilder(bundle, config)
        model, variables = builder.build()
        ObjectiveOptimizer.apply_objective(model, bundle, config, variables)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = config.time_limit_seconds
        solver.parameters.random_seed = config.random_seed
        solver.parameters.num_workers = 1

        for alt_idx in range(count):
            start_time = time.perf_counter()
            # Vary seed slightly for diversity if needed
            solver.parameters.random_seed = config.random_seed + alt_idx * 17
            status_code = solver.Solve(model)
            elapsed = time.perf_counter() - start_time

            if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break

            status = SchedulingStatus.OPTIMAL if status_code == cp_model.OPTIMAL else SchedulingStatus.FEASIBLE
            sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
            res = ResultBuilder.build_result(
                status=status,
                sessions=sessions,
                bundle=bundle,
                config=config,
                runtime_seconds=elapsed,
                message=f"Alternative schedule candidate #{alt_idx + 1}",
            )
            results.append(res)

            # Add solution exclusion constraint to guarantee the next solution is distinct:
            # sum(var for var == 1 in current solution) <= total_assigned - 1
            chosen_vars: List[cp_model.BoolVar] = []
            for unit in bundle.units:
                candidates = variables.candidates_by_unit.get(unit.unit_id, [])
                for (day, period, room_id) in candidates:
                    var = variables.unit_assignment_vars[(unit.unit_id, day, period, room_id)]
                    if solver.Value(var) == 1:
                        chosen_vars.append(var)
                        break

            if chosen_vars:
                model.Add(sum(chosen_vars) <= len(chosen_vars) - 1)
            else:
                break

        return results


class PartialRegenerator:
    """Regenerates specific classes, teachers, or unlocked sessions while freezing the rest."""

    @classmethod
    def prepare_partial_bundle(
        cls,
        bundle: SchedulingInputBundle,
        existing_sessions: List[ScheduledSession],
        regenerate_class_ids: Optional[Set[str]] = None,
        regenerate_teacher_ids: Optional[Set[str]] = None,
        regenerate_days: Optional[Set[int]] = None,
    ) -> Tuple[SchedulingInputBundle, Dict[str, Tuple[int, int, str]]]:
        """Locks sessions that should remain unchanged and prepares the input bundle."""
        existing_by_unit: Dict[str, ScheduledSession] = {s.id: s for s in existing_sessions}
        baseline_assignments: Dict[str, Tuple[int, int, str]] = {}
        updated_units: List[SchedulableUnit] = []

        for unit in bundle.units:
            existing_s = existing_by_unit.get(unit.unit_id)
            if existing_s:
                baseline_assignments[unit.unit_id] = (
                    existing_s.day_of_week,
                    existing_s.start_period,
                    existing_s.room_id,
                )

            should_regenerate = False
            if regenerate_class_ids and unit.class_group_id in regenerate_class_ids:
                should_regenerate = True
            if regenerate_teacher_ids and unit.teacher_id in regenerate_teacher_ids:
                should_regenerate = True
            if existing_s and regenerate_days and existing_s.day_of_week in regenerate_days:
                should_regenerate = True

            # If user explicitly locked this unit, it never regenerates
            if unit.locked_day is not None and unit.locked_period is not None:
                updated_units.append(unit)
            elif should_regenerate or existing_s is None:
                # Keep unlocked for regeneration
                updated_units.append(
                    SchedulableUnit(
                        unit_id=unit.unit_id,
                        assignment_id=unit.assignment_id,
                        class_group_id=unit.class_group_id,
                        subject_id=unit.subject_id,
                        teacher_id=unit.teacher_id,
                        session_type=unit.session_type,
                        duration_periods=unit.duration_periods,
                        secondary_teacher_id=unit.secondary_teacher_id,
                        required_room_type=unit.required_room_type,
                        student_group_id=unit.student_group_id,
                        locked_day=None,
                        locked_period=None,
                        locked_room_id=None,
                    )
                )
            else:
                # Freeze existing session
                updated_units.append(
                    SchedulableUnit(
                        unit_id=unit.unit_id,
                        assignment_id=unit.assignment_id,
                        class_group_id=unit.class_group_id,
                        subject_id=unit.subject_id,
                        teacher_id=unit.teacher_id,
                        session_type=unit.session_type,
                        duration_periods=unit.duration_periods,
                        secondary_teacher_id=unit.secondary_teacher_id,
                        required_room_type=unit.required_room_type,
                        student_group_id=unit.student_group_id,
                        locked_day=existing_s.day_of_week,
                        locked_period=existing_s.start_period,
                        locked_room_id=existing_s.room_id,
                    )
                )

        partial_bundle = SchedulingInputBundle(
            institution_id=bundle.institution_id,
            academic_year_id=bundle.academic_year_id,
            semester_id=bundle.semester_id,
            days=bundle.days,
            periods_per_day=bundle.periods_per_day,
            break_periods=bundle.break_periods,
            units=updated_units,
            teachers=bundle.teachers,
            rooms=bundle.rooms,
            class_groups=bundle.class_groups,
            teacher_availability=bundle.teacher_availability,
            room_availability=bundle.room_availability,
            teacher_workload_rules=bundle.teacher_workload_rules,
            teacher_preferences=bundle.teacher_preferences,
        )

        return partial_bundle, baseline_assignments
