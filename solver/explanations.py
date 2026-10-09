"""Diagnostics and explanations for scheduling failures and infeasibility.

Pinpoints root causes of scheduling failures and generates actionable
remediation guidance for institutional administrators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from core.models import (
    ConstraintType,
    ConstraintViolation,
    Room,
    SchedulableUnit,
    SchedulingConfig,
    SchedulingInputBundle,
    Teacher,
    TeacherWorkloadRule,
)
from solver.constraints import ConstraintModelBuilder
from solver.session_builder import PreflightValidator, PreflightIssue


class DiagnosticSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class DiagnosticRecord:
    """Structured diagnostic record for timetable conflicts and infeasibility."""
    category: str
    severity: str
    explanation: str
    entity_ids: List[str] = field(default_factory=list)
    potential_remediation: str = ""
    is_infeasible_cause: bool = True

    def to_constraint_violation(self) -> ConstraintViolation:
        ctype = ConstraintType.MISSING_SESSION_COUNT
        if "TEACHER" in self.category:
            if "WORKLOAD" in self.category:
                ctype = ConstraintType.TEACHER_MAX_HOURS_EXCEEDED
            elif "AVAILABILITY" in self.category:
                ctype = ConstraintType.TEACHER_UNAVAILABLE
            else:
                ctype = ConstraintType.TEACHER_DOUBLE_BOOKING
        elif "ROOM" in self.category:
            if "CAPACITY" in self.category:
                ctype = ConstraintType.ROOM_CAPACITY_EXCEEDED
            elif "TYPE" in self.category:
                ctype = ConstraintType.ROOM_TYPE_MISMATCH
            else:
                ctype = ConstraintType.ROOM_UNAVAILABLE
        elif "CLASS" in self.category:
            ctype = ConstraintType.CLASS_DOUBLE_BOOKING
        elif "LOCKED" in self.category:
            ctype = ConstraintType.LOCKED_ASSIGNMENT_VIOLATION

        return ConstraintViolation(
            violation_type=ctype,
            is_hard=self.is_infeasible_cause,
            severity=self.severity,
            message=self.explanation,
            involved_teachers=[eid for eid in self.entity_ids if "teacher" in eid.lower() or eid.startswith("t-")],
            involved_rooms=[eid for eid in self.entity_ids if "room" in eid.lower() or eid.startswith("r-")],
            involved_classes=[eid for eid in self.entity_ids if "class" in eid.lower() or eid.startswith("cg-")],
        )


class InfeasibilityExplainer:
    """Diagnoses root causes when CP-SAT proves a model is INFEASIBLE."""

    @classmethod
    def diagnose(
        cls,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
    ) -> List[DiagnosticRecord]:
        """Runs multi-tiered diagnostics to explain why no feasible timetable exists."""
        diagnostics: List[DiagnosticRecord] = []

        # 1. Check preflight issues
        preflight_issues = PreflightValidator.validate_bundle(bundle)
        for issue in preflight_issues:
            diagnostics.append(
                DiagnosticRecord(
                    category=issue.category,
                    severity=issue.severity,
                    explanation=issue.message,
                    entity_ids=issue.entity_ids,
                    potential_remediation=issue.potential_remediation,
                    is_infeasible_cause=issue.is_fatal,
                )
            )

        if any(d.is_infeasible_cause for d in diagnostics):
            return diagnostics

        # 2. Check individual class cohorts
        class_diagnostics = cls._diagnose_per_class(bundle, config)
        if class_diagnostics:
            diagnostics.extend(class_diagnostics)
            return diagnostics

        # 3. Check teacher workload rules relaxation
        workload_diagnostics = cls._diagnose_workload_bottlenecks(bundle, config)
        if workload_diagnostics:
            diagnostics.extend(workload_diagnostics)
            return diagnostics

        # 4. Check room capacity and scarcity
        room_diagnostics = cls._diagnose_room_scarcity(bundle, config)
        if room_diagnostics:
            diagnostics.extend(room_diagnostics)
            return diagnostics

        # 5. General fallback explanation
        diagnostics.append(
            DiagnosticRecord(
                category="OVERCONSTRAINED_SCHEDULE",
                severity="ERROR",
                explanation="The combination of teacher availability, room constraints, and simultaneous class requirements cannot be satisfied together.",
                potential_remediation="Consider expanding teacher availability slots, increasing room counts, or loosening workload limits.",
                is_infeasible_cause=True,
            )
        )
        return diagnostics

    @classmethod
    def _diagnose_per_class(
        cls,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
    ) -> List[DiagnosticRecord]:
        """Tests whether individual classes are infeasible in isolation."""
        results: List[DiagnosticRecord] = []
        for cg in bundle.class_groups:
            cg_units = [u for u in bundle.units if u.class_group_id == cg.id]
            if not cg_units:
                continue

            sub_bundle = SchedulingInputBundle(
                institution_id=bundle.institution_id,
                academic_year_id=bundle.academic_year_id,
                semester_id=bundle.semester_id,
                days=bundle.days,
                periods_per_day=bundle.periods_per_day,
                break_periods=bundle.break_periods,
                units=cg_units,
                teachers=bundle.teachers,
                rooms=bundle.rooms,
                class_groups=[cg],
                teacher_availability=bundle.teacher_availability,
                room_availability=bundle.room_availability,
                teacher_workload_rules=bundle.teacher_workload_rules,
                teacher_preferences={},
            )

            builder = ConstraintModelBuilder(sub_bundle, config)
            model, _ = builder.build()
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 2.0
            solver.parameters.num_workers = 1
            status = solver.Solve(model)

            if status == cp_model.INFEASIBLE:
                results.append(
                    DiagnosticRecord(
                        category="CLASS_ISOLATED_INFEASIBLE",
                        severity="ERROR",
                        explanation=f"Class cohort '{cg.name}' (id: {cg.id}) is impossible to schedule even in isolation.",
                        entity_ids=[cg.id],
                        potential_remediation=f"Inspect teacher availability, room requirements, or locked sessions for class '{cg.name}'.",
                        is_infeasible_cause=True,
                    )
                )
        return results

    @classmethod
    def _diagnose_workload_bottlenecks(
        cls,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
    ) -> List[DiagnosticRecord]:
        """Tests whether relaxing teacher workload rules yields a feasible solution."""
        if not bundle.teacher_workload_rules:
            return []

        relaxed_bundle = SchedulingInputBundle(
            institution_id=bundle.institution_id,
            academic_year_id=bundle.academic_year_id,
            semester_id=bundle.semester_id,
            days=bundle.days,
            periods_per_day=bundle.periods_per_day,
            break_periods=bundle.break_periods,
            units=bundle.units,
            teachers=bundle.teachers,
            rooms=bundle.rooms,
            class_groups=bundle.class_groups,
            teacher_availability=bundle.teacher_availability,
            room_availability=bundle.room_availability,
            teacher_workload_rules={},  # Relaxed!
            teacher_preferences={},
        )

        builder = ConstraintModelBuilder(relaxed_bundle, config)
        model, _ = builder.build()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3.0
        solver.parameters.num_workers = 1
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Workload rules were indeed the bottleneck!
            return [
                DiagnosticRecord(
                    category="TEACHER_WORKLOAD_BOTTLENECK",
                    severity="ERROR",
                    explanation="A feasible schedule exists without teacher workload restrictions, but teacher workload limits (e.g. daily max, consecutive periods, or weekly limits) make it impossible.",
                    entity_ids=list(bundle.teacher_workload_rules.keys()),
                    potential_remediation="Increase max_periods_per_day or max_consecutive_periods for heavily loaded teachers.",
                    is_infeasible_cause=True,
                )
            ]
        return []

    @classmethod
    def _diagnose_room_scarcity(
        cls,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
    ) -> List[DiagnosticRecord]:
        """Tests whether relaxing room constraints yields a feasible schedule."""
        # Create virtual unconstrained rooms
        unconstrained_rooms = [
            Room(id=f"virtual-room-{i}", name=f"Virtual Room {i}", code=f"VR-{i}", room_type=r.room_type, capacity=999)
            for i, r in enumerate(bundle.rooms * 3)
        ]
        relaxed_bundle = SchedulingInputBundle(
            institution_id=bundle.institution_id,
            academic_year_id=bundle.academic_year_id,
            semester_id=bundle.semester_id,
            days=bundle.days,
            periods_per_day=bundle.periods_per_day,
            break_periods=bundle.break_periods,
            units=bundle.units,
            teachers=bundle.teachers,
            rooms=unconstrained_rooms,
            class_groups=bundle.class_groups,
            teacher_availability=bundle.teacher_availability,
            room_availability={},
            teacher_workload_rules=bundle.teacher_workload_rules,
            teacher_preferences={},
        )

        builder = ConstraintModelBuilder(relaxed_bundle, config)
        model, _ = builder.build()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3.0
        solver.parameters.num_workers = 1
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return [
                DiagnosticRecord(
                    category="ROOM_SCARCITY_BOTTLENECK",
                    severity="ERROR",
                    explanation="The schedule is feasible with additional classrooms/laboratories, but current room availability or capacities are insufficient.",
                    entity_ids=[r.id for r in bundle.rooms],
                    potential_remediation="Add more classrooms/labs or expand room capacities.",
                    is_infeasible_cause=True,
                )
            ]
        return []
