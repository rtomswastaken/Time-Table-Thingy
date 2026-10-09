"""Session builder and preflight validation for Timetable Thingy.

Converts curricular requirements into schedulable units and performs
pre-flight validation to detect impossible problem instances before
invoking the CP-SAT solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import uuid

from core.models import (
    ClassGroup,
    ConstraintType,
    ConstraintViolation,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingInputBundle,
    SessionType,
    SubjectOffering,
    SubjectSessionRequirement,
    Teacher,
    TeacherWorkloadRule,
)


@dataclass(frozen=True)
class PreflightIssue:
    """Diagnostic issue detected before solving."""
    category: str
    severity: str  # "ERROR" or "WARNING"
    message: str
    entity_ids: List[str] = field(default_factory=list)
    is_fatal: bool = True
    potential_remediation: str = ""

    def to_constraint_violation(self) -> ConstraintViolation:
        # Map category to ConstraintType where possible
        ctype = ConstraintType.MISSING_SESSION_COUNT
        if "TEACHER_UNAVAILABLE" in self.category or "TEACHER_AVAILABILITY" in self.category:
            ctype = ConstraintType.TEACHER_UNAVAILABLE
        elif "ROOM_CAPACITY" in self.category:
            ctype = ConstraintType.ROOM_CAPACITY_EXCEEDED
        elif "ROOM_TYPE" in self.category:
            ctype = ConstraintType.ROOM_TYPE_MISMATCH
        elif "ROOM_UNAVAILABLE" in self.category:
            ctype = ConstraintType.ROOM_UNAVAILABLE
        elif "WORKLOAD" in self.category:
            ctype = ConstraintType.TEACHER_MAX_HOURS_EXCEEDED
        elif "LOCKED" in self.category:
            ctype = ConstraintType.LOCKED_ASSIGNMENT_VIOLATION
        elif "DOUBLE_BOOKING" in self.category:
            ctype = ConstraintType.TEACHER_DOUBLE_BOOKING

        return ConstraintViolation(
            violation_type=ctype,
            is_hard=self.is_fatal,
            severity=self.severity,
            message=self.message,
            involved_teachers=[eid for eid in self.entity_ids if eid.startswith("t-") or "teacher" in eid.lower()],
            involved_rooms=[eid for eid in self.entity_ids if eid.startswith("r-") or "room" in eid.lower()],
            involved_classes=[eid for eid in self.entity_ids if eid.startswith("cg-") or "class" in eid.lower()],
        )


class SessionBuilder:
    """Expands curricular offerings into atomic SchedulableUnit instances."""

    @staticmethod
    def expand_offering_requirements(
        assignment_id: str,
        class_group_id: str,
        subject_id: str,
        primary_teacher_id: str,
        requirements: List[SubjectSessionRequirement],
        secondary_teacher_id: Optional[str] = None,
        student_group_id: Optional[str] = None,
    ) -> List[SchedulableUnit]:
        """Expands a list of session requirements into schedulable units.
        
        For example: a requirement with frequency=3, duration=1 produces 3 units of duration 1.
        A lab requirement with frequency=1, duration=2 produces 1 unit of duration 2.
        """
        units: List[SchedulableUnit] = []
        for req in requirements:
            for seq in range(req.frequency_per_week):
                unit_id = f"unit-{assignment_id}-{req.session_type.value.lower()}-{req.consecutive_periods}p-{seq + 1}-{uuid.uuid4().hex[:6]}"
                units.append(
                    SchedulableUnit(
                        unit_id=unit_id,
                        assignment_id=assignment_id,
                        class_group_id=class_group_id,
                        subject_id=subject_id,
                        teacher_id=primary_teacher_id,
                        secondary_teacher_id=secondary_teacher_id,
                        session_type=req.session_type,
                        duration_periods=req.consecutive_periods,
                        required_room_type=req.preferred_room_type,
                        student_group_id=student_group_id,
                    )
                )
        return units

    @staticmethod
    def expand_default_weekly_periods(
        assignment_id: str,
        class_group_id: str,
        subject_id: str,
        primary_teacher_id: str,
        weekly_periods: int,
        session_duration: int = 1,
        session_type: SessionType = SessionType.THEORY,
        required_room_type: Optional[RoomType] = None,
        secondary_teacher_id: Optional[str] = None,
        student_group_id: Optional[str] = None,
    ) -> List[SchedulableUnit]:
        """Decomposes weekly periods into standard duration sessions."""
        if weekly_periods <= 0:
            return []
        if session_duration < 1:
            session_duration = 1

        full_sessions_count = weekly_periods // session_duration
        remainder = weekly_periods % session_duration

        units: List[SchedulableUnit] = []
        for seq in range(full_sessions_count):
            unit_id = f"unit-{assignment_id}-{session_type.value.lower()}-{seq + 1}-{uuid.uuid4().hex[:6]}"
            units.append(
                SchedulableUnit(
                    unit_id=unit_id,
                    assignment_id=assignment_id,
                    class_group_id=class_group_id,
                    subject_id=subject_id,
                    teacher_id=primary_teacher_id,
                    secondary_teacher_id=secondary_teacher_id,
                    session_type=session_type,
                    duration_periods=session_duration,
                    required_room_type=required_room_type,
                    student_group_id=student_group_id,
                )
            )

        if remainder > 0:
            unit_id = f"unit-{assignment_id}-{session_type.value.lower()}-rem-{uuid.uuid4().hex[:6]}"
            units.append(
                SchedulableUnit(
                    unit_id=unit_id,
                    assignment_id=assignment_id,
                    class_group_id=class_group_id,
                    subject_id=subject_id,
                    teacher_id=primary_teacher_id,
                    secondary_teacher_id=secondary_teacher_id,
                    session_type=session_type,
                    duration_periods=remainder,
                    required_room_type=required_room_type,
                    student_group_id=student_group_id,
                )
            )

        return units


class PreflightValidator:
    """Pre-flight feasibility checker before executing CP-SAT search."""

    @classmethod
    def validate_bundle(cls, bundle: SchedulingInputBundle) -> List[PreflightIssue]:
        issues: List[PreflightIssue] = []

        total_working_slots_per_day = bundle.periods_per_day - len(bundle.break_periods)
        total_weekly_slots = len(bundle.days) * max(0, total_working_slots_per_day)

        # 1. Basic structural checks
        if not bundle.days:
            issues.append(
                PreflightIssue(
                    category="SCHEDULE_STRUCTURE",
                    severity="ERROR",
                    message="No working days specified in scheduling bundle.",
                    is_fatal=True,
                    potential_remediation="Configure at least one working day for the institution.",
                )
            )
            return issues

        if bundle.periods_per_day < 1:
            issues.append(
                PreflightIssue(
                    category="SCHEDULE_STRUCTURE",
                    severity="ERROR",
                    message=f"Invalid periods_per_day: {bundle.periods_per_day}. Must be >= 1.",
                    is_fatal=True,
                    potential_remediation="Set periods_per_day to at least 1.",
                )
            )
            return issues

        if not bundle.rooms:
            issues.append(
                PreflightIssue(
                    category="ROOM_RESOURCES",
                    severity="ERROR",
                    message="No rooms configured in scheduling bundle.",
                    is_fatal=True,
                    potential_remediation="Add at least one classroom or lab facility.",
                )
            )

        teacher_map = {t.id: t for t in bundle.teachers}
        room_map = {r.id: r for r in bundle.rooms}
        class_map = {c.id: c for c in bundle.class_groups}

        # 2. Check each unit for basic validity and resources
        for unit in bundle.units:
            # Check unit duration
            if unit.duration_periods > bundle.periods_per_day:
                issues.append(
                    PreflightIssue(
                        category="SESSION_DURATION",
                        severity="ERROR",
                        message=f"Unit '{unit.unit_id}' has duration {unit.duration_periods} which exceeds periods_per_day ({bundle.periods_per_day}).",
                        entity_ids=[unit.unit_id, unit.subject_id],
                        is_fatal=True,
                        potential_remediation="Reduce session duration or increase periods per day.",
                    )
                )

            # Check teacher existence
            if unit.teacher_id not in teacher_map:
                issues.append(
                    PreflightIssue(
                        category="MISSING_TEACHER",
                        severity="ERROR",
                        message=f"Unit '{unit.unit_id}' references unknown teacher '{unit.teacher_id}'.",
                        entity_ids=[unit.unit_id, unit.teacher_id],
                        is_fatal=True,
                        potential_remediation="Assign a valid, registered teacher to the subject assignment.",
                    )
                )

            # Check secondary teacher existence if present
            if unit.secondary_teacher_id and unit.secondary_teacher_id not in teacher_map:
                issues.append(
                    PreflightIssue(
                        category="MISSING_TEACHER",
                        severity="ERROR",
                        message=f"Unit '{unit.unit_id}' references unknown secondary teacher '{unit.secondary_teacher_id}'.",
                        entity_ids=[unit.unit_id, unit.secondary_teacher_id],
                        is_fatal=True,
                        potential_remediation="Assign a valid secondary teacher or remove co-teaching requirement.",
                    )
                )

            # Check class group existence
            if unit.class_group_id not in class_map:
                issues.append(
                    PreflightIssue(
                        category="MISSING_CLASS",
                        severity="ERROR",
                        message=f"Unit '{unit.unit_id}' references unknown class group '{unit.class_group_id}'.",
                        entity_ids=[unit.unit_id, unit.class_group_id],
                        is_fatal=True,
                        potential_remediation="Ensure the class cohort exists in the academic database.",
                    )
                )

            # Check room compatibility
            cg = class_map.get(unit.class_group_id)
            req_capacity = cg.student_count if cg else 1
            compatible_rooms = [
                r for r in bundle.rooms
                if (unit.required_room_type is None or r.room_type == unit.required_room_type)
                and r.capacity >= req_capacity
            ]
            if not compatible_rooms:
                issues.append(
                    PreflightIssue(
                        category="ROOM_COMPATIBILITY",
                        severity="ERROR",
                        message=f"No compatible room found for unit '{unit.unit_id}' (required_room_type={unit.required_room_type}, min_capacity={req_capacity}).",
                        entity_ids=[unit.unit_id, unit.class_group_id],
                        is_fatal=True,
                        potential_remediation="Add a room of the required type and capacity, or split the class into smaller student groups.",
                    )
                )

            # Check locked assignment validity
            if unit.locked_day is not None or unit.locked_period is not None:
                if unit.locked_day is None or unit.locked_period is None:
                    issues.append(
                        PreflightIssue(
                            category="LOCKED_INCOMPLETE",
                            severity="ERROR",
                            message=f"Unit '{unit.unit_id}' has incomplete lock (day={unit.locked_day}, period={unit.locked_period}). Both must be set.",
                            entity_ids=[unit.unit_id],
                            is_fatal=True,
                            potential_remediation="Specify both locked_day and locked_period, or unlock the session.",
                        )
                    )
                else:
                    if unit.locked_day not in bundle.days:
                        issues.append(
                            PreflightIssue(
                                category="LOCKED_OUT_OF_BOUNDS",
                                severity="ERROR",
                                message=f"Unit '{unit.unit_id}' locked to non-working day {unit.locked_day}.",
                                entity_ids=[unit.unit_id],
                                is_fatal=True,
                                potential_remediation="Move locked session to an active working day.",
                            )
                        )
                    if unit.locked_period < 0 or unit.locked_period + unit.duration_periods > bundle.periods_per_day:
                        issues.append(
                            PreflightIssue(
                                category="LOCKED_OUT_OF_BOUNDS",
                                severity="ERROR",
                                message=f"Unit '{unit.unit_id}' locked to period {unit.locked_period} spanning beyond day length ({bundle.periods_per_day}).",
                                entity_ids=[unit.unit_id],
                                is_fatal=True,
                                potential_remediation="Adjust start period so the session fits within the daily period limit.",
                            )
                        )
                    # Check break overlap
                    for p in range(unit.locked_period, unit.locked_period + unit.duration_periods):
                        if p in bundle.break_periods:
                            issues.append(
                                PreflightIssue(
                                    category="LOCKED_BREAK_OVERLAP",
                                    severity="ERROR",
                                    message=f"Unit '{unit.unit_id}' locked across break period {p}.",
                                    entity_ids=[unit.unit_id],
                                    is_fatal=True,
                                    potential_remediation="Unlock session or reschedule away from break/recess periods.",
                                )
                            )
                    # Check locked room
                    if unit.locked_room_id:
                        if unit.locked_room_id not in room_map:
                            issues.append(
                                PreflightIssue(
                                    category="LOCKED_ROOM_NOT_FOUND",
                                    severity="ERROR",
                                    message=f"Unit '{unit.unit_id}' locked to unknown room '{unit.locked_room_id}'.",
                                    entity_ids=[unit.unit_id, unit.locked_room_id],
                                    is_fatal=True,
                                    potential_remediation="Select a valid room for the locked session.",
                                )
                            )
                        else:
                            lr = room_map[unit.locked_room_id]
                            if unit.required_room_type and lr.room_type != unit.required_room_type:
                                issues.append(
                                    PreflightIssue(
                                        category="LOCKED_ROOM_TYPE_MISMATCH",
                                        severity="ERROR",
                                        message=f"Unit '{unit.unit_id}' requires {unit.required_room_type} but is locked to room '{lr.name}' of type {lr.room_type}.",
                                        entity_ids=[unit.unit_id, unit.locked_room_id],
                                        is_fatal=True,
                                        potential_remediation="Lock to a room that matches the required room type.",
                                    )
                                )
                            if cg and lr.capacity < cg.student_count:
                                issues.append(
                                    PreflightIssue(
                                        category="LOCKED_ROOM_CAPACITY_EXCEEDED",
                                        severity="ERROR",
                                        message=f"Unit '{unit.unit_id}' class size ({cg.student_count}) exceeds locked room '{lr.name}' capacity ({lr.capacity}).",
                                        entity_ids=[unit.unit_id, unit.locked_room_id],
                                        is_fatal=True,
                                        potential_remediation="Assign to a room with sufficient seating capacity.",
                                    )
                                )

                    # Check teacher availability for locked slot
                    unavail = bundle.teacher_availability.get(unit.teacher_id, set())
                    for p in range(unit.locked_period, unit.locked_period + unit.duration_periods):
                        if (unit.locked_day, p) in unavail:
                            issues.append(
                                PreflightIssue(
                                    category="LOCKED_TEACHER_UNAVAILABLE",
                                    severity="ERROR",
                                    message=f"Unit '{unit.unit_id}' is locked to day {unit.locked_day}, period {p}, when teacher '{unit.teacher_id}' is marked unavailable.",
                                    entity_ids=[unit.unit_id, unit.teacher_id],
                                    is_fatal=True,
                                    potential_remediation="Update teacher availability or move the locked session.",
                                )
                            )

        # 3. Classload Pigeonhole Checks
        class_required_periods: Dict[str, int] = {}
        for unit in bundle.units:
            class_required_periods[unit.class_group_id] = class_required_periods.get(unit.class_group_id, 0) + unit.duration_periods

        for cg_id, req_periods in class_required_periods.items():
            if req_periods > total_weekly_slots:
                issues.append(
                    PreflightIssue(
                        category="CLASS_LOAD_EXCEEDED",
                        severity="ERROR",
                        message=f"Class '{cg_id}' requires {req_periods} periods, but only {total_weekly_slots} working periods exist in the weekly calendar.",
                        entity_ids=[cg_id],
                        is_fatal=True,
                        potential_remediation=f"Reduce required contact hours for class '{cg_id}' or increase periods per day.",
                    )
                )

        # 4. Teacher Workload & Availability Pigeonhole Checks
        teacher_required_periods: Dict[str, int] = {}
        for unit in bundle.units:
            teacher_required_periods[unit.teacher_id] = teacher_required_periods.get(unit.teacher_id, 0) + unit.duration_periods
            if unit.secondary_teacher_id:
                teacher_required_periods[unit.secondary_teacher_id] = teacher_required_periods.get(unit.secondary_teacher_id, 0) + unit.duration_periods

        for t_id, req_periods in teacher_required_periods.items():
            # Check workload rule
            rule = bundle.teacher_workload_rules.get(t_id)
            if rule and req_periods > rule.max_periods_per_week:
                issues.append(
                    PreflightIssue(
                        category="TEACHER_WORKLOAD_EXCEEDED",
                        severity="ERROR",
                        message=f"Teacher '{t_id}' assigned {req_periods} periods, exceeding max_periods_per_week limit of {rule.max_periods_per_week}.",
                        entity_ids=[t_id],
                        is_fatal=True,
                        potential_remediation=f"Increase max_periods_per_week for teacher '{t_id}' or distribute teaching assignments.",
                    )
                )

            # Check available slots count
            unavail_slots = bundle.teacher_availability.get(t_id, set())
            # Available slots that are not in break periods
            avail_slots_count = 0
            for d in bundle.days:
                for p in range(bundle.periods_per_day):
                    if p not in bundle.break_periods and (d, p) not in unavail_slots:
                        avail_slots_count += 1

            if req_periods > avail_slots_count:
                issues.append(
                    PreflightIssue(
                        category="TEACHER_INSUFFICIENT_AVAILABILITY",
                        severity="ERROR",
                        message=f"Teacher '{t_id}' needs {req_periods} teaching periods, but only has {avail_slots_count} available slots in their schedule.",
                        entity_ids=[t_id],
                        is_fatal=True,
                        potential_remediation=f"Open more available time slots for teacher '{t_id}' or reassign some subjects.",
                    )
                )

        # 5. Check overlapping locked assignments
        locked_teacher_slots: Dict[Tuple[str, int, int], str] = {}
        locked_room_slots: Dict[Tuple[str, int, int], str] = {}
        locked_class_slots: Dict[Tuple[str, int, int], str] = {}

        for unit in bundle.units:
            if unit.locked_day is not None and unit.locked_period is not None:
                for p in range(unit.locked_period, unit.locked_period + unit.duration_periods):
                    # Teacher check
                    t_key = (unit.teacher_id, unit.locked_day, p)
                    if t_key in locked_teacher_slots:
                        issues.append(
                            PreflightIssue(
                                category="LOCKED_TEACHER_DOUBLE_BOOKING",
                                severity="ERROR",
                                message=f"Conflicting locked assignments: Teacher '{unit.teacher_id}' double-booked on day {unit.locked_day}, period {p} between '{locked_teacher_slots[t_key]}' and '{unit.unit_id}'.",
                                entity_ids=[unit.teacher_id, locked_teacher_slots[t_key], unit.unit_id],
                                is_fatal=True,
                                potential_remediation="Resolve overlapping locked assignments for this teacher.",
                            )
                        )
                    else:
                        locked_teacher_slots[t_key] = unit.unit_id

                    # Room check (if locked)
                    if unit.locked_room_id:
                        r_key = (unit.locked_room_id, unit.locked_day, p)
                        if r_key in locked_room_slots:
                            issues.append(
                                PreflightIssue(
                                    category="LOCKED_ROOM_DOUBLE_BOOKING",
                                    severity="ERROR",
                                    message=f"Conflicting locked assignments: Room '{unit.locked_room_id}' double-booked on day {unit.locked_day}, period {p} between '{locked_room_slots[r_key]}' and '{unit.unit_id}'.",
                                    entity_ids=[unit.locked_room_id, locked_room_slots[r_key], unit.unit_id],
                                    is_fatal=True,
                                    potential_remediation="Assign different rooms to the overlapping locked sessions.",
                                )
                            )
                        else:
                            locked_room_slots[r_key] = unit.unit_id

                    # Class check (whole class)
                    if unit.student_group_id is None:
                        c_key = (unit.class_group_id, unit.locked_day, p)
                        if c_key in locked_class_slots:
                            issues.append(
                                PreflightIssue(
                                    category="LOCKED_CLASS_DOUBLE_BOOKING",
                                    severity="ERROR",
                                    message=f"Conflicting locked assignments: Class '{unit.class_group_id}' double-booked on day {unit.locked_day}, period {p} between '{locked_class_slots[c_key]}' and '{unit.unit_id}'.",
                                    entity_ids=[unit.class_group_id, locked_class_slots[c_key], unit.unit_id],
                                    is_fatal=True,
                                    potential_remediation="Reschedule one of the conflicting locked sessions.",
                                )
                            )
                        else:
                            locked_class_slots[c_key] = unit.unit_id

        return issues
