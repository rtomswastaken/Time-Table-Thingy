"""Diagnostic reporting for scheduling conflicts, infeasibility, and unscheduled curricular units."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import (
    ConstraintType,
    ConstraintViolation,
    SchedulableUnit,
    ScheduledSession,
    SchedulingResult,
    SchedulingStatus,
)
from exchange.models import ConflictReportRow, UnscheduledSessionRow


def generate_remediation_suggestion(violation: ConstraintViolation) -> str:
    """Provides actionable guidance based on the constraint type."""
    ctype = violation.violation_type
    if ctype == ConstraintType.TEACHER_DOUBLE_BOOKING:
        return "Reschedule one session to an open period or assign an alternate qualified instructor."
    elif ctype == ConstraintType.ROOM_DOUBLE_BOOKING:
        return "Move one session to another available classroom or laboratory of matching capacity."
    elif ctype == ConstraintType.CLASS_DOUBLE_BOOKING:
        return "Resolve curriculum overlap; student cohort cannot attend two simultaneous lectures."
    elif ctype == ConstraintType.TEACHER_UNAVAILABLE:
        return "Move session outside instructor's blocked time slot or adjust faculty availability settings."
    elif ctype == ConstraintType.ROOM_UNAVAILABLE:
        return "Facility is marked unavailable for maintenance/institutional booking; allocate alternate room."
    elif ctype == ConstraintType.ROOM_CAPACITY_EXCEEDED:
        return "Assign a larger lecture hall or partition class cohort into laboratory batches."
    elif ctype == ConstraintType.ROOM_TYPE_MISMATCH:
        return "Practical/laboratory sessions require designated specialized facility (e.g. Computer Lab)."
    elif ctype == ConstraintType.TEACHER_MAX_HOURS_EXCEEDED:
        return "Reduce weekly assignments for this teacher or raise contract maximum limit."
    elif ctype == ConstraintType.TEACHER_CONSECUTIVE_LIMIT:
        return "Insert a rest period or break between consecutive lectures."
    elif ctype == ConstraintType.LAB_CONTINUITY_BROKEN:
        return "Laboratory practicals must occupy consecutive contiguous periods without interruption."
    return "Review constraints and re-run schedule generation."


class ConflictReportGenerator:
    """Compiles constraint violation breakdowns and remediation reports."""

    @classmethod
    def generate_conflict_report(
        cls,
        result: Optional[SchedulingResult] = None,
        violations: Optional[List[ConstraintViolation]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ConflictReportRow]:
        """Generates structured conflict records from solver results or manual validator output."""
        all_violations = list(violations or [])
        if result and result.violations:
            all_violations.extend(result.violations)

        conflict_rows: List[ConflictReportRow] = []

        # If solver had an infeasible status or timeout, add a summary diagnostic row
        if result:
            if result.status == SchedulingStatus.INFEASIBLE:
                conflict_rows.append(ConflictReportRow(
                    violation_type="SOLVER_PROVEN_INFEASIBLE",
                    severity="ERROR",
                    is_hard=True,
                    description=result.message or "The CP-SAT solver proved that no mathematically valid schedule exists with the given constraints.",
                    remediation_suggestion="Identify bottleneck resources (over-subscribed teachers or specialized labs) or relax hard constraints.",
                ))
            elif result.status == SchedulingStatus.TIMEOUT:
                conflict_rows.append(ConflictReportRow(
                    violation_type="SOLVER_TIMEOUT",
                    severity="WARNING",
                    is_hard=False,
                    description=result.message or "Solver search time limit was reached before finding a provably complete solution.",
                    remediation_suggestion="Increase solver time limit in scheduling configuration, or allow partial solutions.",
                ))
            elif result.status == SchedulingStatus.ERROR:
                conflict_rows.append(ConflictReportRow(
                    violation_type="SCHEDULING_ENGINE_ERROR",
                    severity="ERROR",
                    is_hard=True,
                    description=result.message or "Scheduling engine encountered a configuration or formulation error.",
                    remediation_suggestion="Verify pre-flight validity of all curricular units, rooms, and teachers.",
                ))

        for v in all_violations:
            suggestion = generate_remediation_suggestion(v)
            conflict_rows.append(ConflictReportRow(
                violation_type=v.violation_type.value if hasattr(v.violation_type, "value") else str(v.violation_type),
                severity=v.severity,
                is_hard=v.is_hard,
                description=v.message,
                involved_teachers=list(v.involved_teachers),
                involved_rooms=list(v.involved_rooms),
                involved_classes=list(v.involved_classes),
                involved_sessions=list(v.involved_sessions),
                remediation_suggestion=suggestion,
            ))

        return conflict_rows

    @classmethod
    def generate_unscheduled_report(
        cls,
        required_units: List[SchedulableUnit],
        scheduled_sessions: List[ScheduledSession],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[UnscheduledSessionRow]:
        """Identifies curricular units that failed to be scheduled in the timetable."""
        meta = metadata or {}
        placed_unit_ids = {s.id for s in scheduled_sessions}

        # Track placed counts per assignment
        placed_counts_by_assignment: Dict[str, int] = {}
        for s in scheduled_sessions:
            placed_counts_by_assignment[s.class_subject_assignment_id] = (
                placed_counts_by_assignment.get(s.class_subject_assignment_id, 0) + 1
            )

        unscheduled_rows: List[UnscheduledSessionRow] = []

        sub_code_map = meta.get("sub_code_map", {})
        sub_name_map = meta.get("sub_name_map", {})
        class_name_map = meta.get("class_name_map", {})
        teacher_name_map = meta.get("teacher_name_map", {})

        for unit in required_units:
            if unit.unit_id not in placed_unit_ids:
                s_code = sub_code_map.get(unit.subject_id, unit.subject_id)
                s_name = sub_name_map.get(unit.subject_id, "")
                c_name = class_name_map.get(unit.class_group_id, unit.class_group_id)
                t_name = teacher_name_map.get(unit.teacher_id, unit.teacher_id)

                unscheduled_rows.append(UnscheduledSessionRow(
                    offering_id=unit.assignment_id,
                    subject_code=s_code,
                    subject_name=s_name,
                    class_name=c_name,
                    teacher_name=t_name,
                    required_sessions=1,
                    placed_sessions=0,
                    missing_count=1,
                    reason="No feasible conflict-free timeslot or facility available during solver execution.",
                ))

        return unscheduled_rows
