"""Deterministic Schedule Validator.

Implements the ScheduleValidator protocol defined in core.interfaces.
Detects hard constraint violations and evaluates soft preference warnings.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.exceptions import ValidationError
from core.interfaces import ScheduleValidator
from core.models import (
    ClassGroup,
    ConstraintType,
    ConstraintViolation,
    OptimizationMetrics,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    Teacher,
    TeacherWorkloadRule,
)


class DeterministicScheduleValidator:
    """Standalone, deterministic schedule validator satisfying ScheduleValidator protocol."""

    def validate(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
    ) -> List[ConstraintViolation]:
        """Validates all sessions against institutional constraints in bundle.

        Returns empty list if 100% valid.
        Returns hard errors and soft warnings otherwise.
        """
        violations: List[ConstraintViolation] = []

        # Index lookup maps
        teacher_map: Dict[str, Teacher] = {t.id: t for t in bundle.teachers}
        room_map: Dict[str, Room] = {r.id: r for r in bundle.rooms}
        class_map: Dict[str, ClassGroup] = {c.id: c for c in bundle.class_groups}
        unit_map: Dict[str, SchedulableUnit] = {u.assignment_id: u for u in bundle.units}
        # Also map by unit_id
        for u in bundle.units:
            unit_map[u.unit_id] = u

        # 1. Period bounds and break period overlap
        self._check_period_bounds_and_breaks(sessions, bundle, violations)

        # 2. Double-booking checks (Teacher, Class, Room)
        self._check_double_bookings(sessions, bundle, teacher_map, room_map, class_map, violations)

        # 3. Availability checks (Teacher and Room)
        self._check_availabilities(sessions, bundle, teacher_map, room_map, violations)

        # 4. Room compatibility & capacity
        self._check_room_compatibility(sessions, bundle, room_map, class_map, unit_map, violations)

        # 5. Teacher workload limits & consecutive limits
        self._check_teacher_workloads(sessions, bundle, teacher_map, violations)

        # 6. Soft preference evaluation
        self._check_soft_preferences(sessions, bundle, teacher_map, violations)

        # 7. Locked assignments and missing units
        self._check_locked_assignments(sessions, unit_map, violations)
        self._check_required_sessions(sessions, bundle, violations)

        return violations

    def validate_move(
        self,
        session_id: str,
        target_day: int,
        target_period: int,
        target_room_id: str,
        current_sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
    ) -> List[ConstraintViolation]:
        """Validates proposed move of a session to a target slot and room."""
        # Check if session exists
        target_session: Optional[ScheduledSession] = None
        simulated_sessions: List[ScheduledSession] = []

        for s in current_sessions:
            if s.id == session_id:
                target_session = s
            else:
                simulated_sessions.append(s)

        if not target_session:
            return [
                ConstraintViolation(
                    violation_type=ConstraintType.MISSING_SESSION_COUNT,
                    is_hard=True,
                    severity="ERROR",
                    message=f"Session with ID '{session_id}' not found.",
                )
            ]

        # Check if session is locked
        if target_session.is_locked:
            return [
                ConstraintViolation(
                    violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                    is_hard=True,
                    severity="ERROR",
                    message=f"Cannot move locked session '{session_id}'. Unlock it first.",
                    involved_sessions=[session_id],
                )
            ]

        # Create proposed session
        proposed_session = ScheduledSession(
            timetable_id=target_session.timetable_id,
            class_subject_assignment_id=target_session.class_subject_assignment_id,
            day_of_week=target_day,
            start_period=target_period,
            duration_periods=target_session.duration_periods,
            room_id=target_room_id,
            teacher_id=target_session.teacher_id,
            class_group_id=target_session.class_group_id,
            id=target_session.id,
            secondary_teacher_id=target_session.secondary_teacher_id,
            student_group_id=target_session.student_group_id,
            is_locked=target_session.is_locked,
        )
        simulated_sessions.append(proposed_session)

        # Run full validation on simulated state
        all_violations = self.validate(simulated_sessions, bundle)

        # Filter violations that involve the proposed session for clear reporting
        # but also return any newly triggered violations
        relevant_violations = [
            v for v in all_violations
            if session_id in v.involved_sessions or not v.involved_sessions
        ]
        return relevant_violations if relevant_violations else all_violations

    def _check_period_bounds_and_breaks(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        violations: List[ConstraintViolation],
    ) -> None:
        valid_days = set(bundle.days)
        max_period = bundle.periods_per_day

        for s in sessions:
            if s.day_of_week not in valid_days:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.LAB_CONTINUITY_BROKEN,
                        is_hard=True,
                        severity="ERROR",
                        message=f"Session scheduled on invalid day {s.day_of_week} (Institution working days: {sorted(valid_days)}).",
                        involved_sessions=[s.id],
                        involved_classes=[s.class_group_id],
                    )
                )

            if s.start_period < 0 or (s.start_period + s.duration_periods) > max_period:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.LAB_CONTINUITY_BROKEN,
                        is_hard=True,
                        severity="ERROR",
                        message=(
                            f"Session extends outside daily periods: start {s.start_period}, "
                            f"duration {s.duration_periods}, max periods per day {max_period}."
                        ),
                        involved_sessions=[s.id],
                        involved_classes=[s.class_group_id],
                    )
                )

            # Check overlap with break periods
            for p in s.occupied_periods:
                if p in bundle.break_periods:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.LAB_CONTINUITY_BROKEN,
                            is_hard=True,
                            severity="ERROR",
                            message=f"Session occupies designated break period {p} on day {s.day_of_week}.",
                            involved_sessions=[s.id],
                            involved_classes=[s.class_group_id],
                        )
                    )

    def _check_double_bookings(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        teacher_map: Dict[str, Teacher],
        room_map: Dict[str, Room],
        class_map: Dict[str, ClassGroup],
        violations: List[ConstraintViolation],
    ) -> None:
        teacher_slots: Dict[Tuple[str, int, int], List[ScheduledSession]] = {}
        class_slots: Dict[Tuple[str, int, int], List[ScheduledSession]] = {}
        room_slots: Dict[Tuple[str, int, int], List[ScheduledSession]] = {}

        for s in sessions:
            for p in s.occupied_periods:
                # Teacher slots (both primary and secondary)
                t_key = (s.teacher_id, s.day_of_week, p)
                teacher_slots.setdefault(t_key, []).append(s)

                if s.secondary_teacher_id:
                    sec_key = (s.secondary_teacher_id, s.day_of_week, p)
                    teacher_slots.setdefault(sec_key, []).append(s)

                # Class slots
                c_key = (s.class_group_id, s.day_of_week, p)
                class_slots.setdefault(c_key, []).append(s)

                # Room slots
                r_key = (s.room_id, s.day_of_week, p)
                room_slots.setdefault(r_key, []).append(s)

        # Check teacher double bookings
        for (teacher_id, day, period), sess_list in teacher_slots.items():
            if len(sess_list) > 1:
                t_name = teacher_map[teacher_id].name if teacher_id in teacher_map else teacher_id
                session_ids = [s.id for s in sess_list]
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.TEACHER_DOUBLE_BOOKING,
                        is_hard=True,
                        severity="ERROR",
                        message=(
                            f"Teacher '{t_name}' is double-booked on Day {day}, Period {period} "
                            f"across {len(sess_list)} sessions."
                        ),
                        involved_sessions=session_ids,
                        involved_teachers=[teacher_id],
                    )
                )

        # Check class double bookings
        for (class_id, day, period), sess_list in class_slots.items():
            if len(sess_list) > 1:
                # If sessions are for distinct student subgroups within the class, they might be parallel labs
                subgroups = [s.student_group_id for s in sess_list]
                has_none_subgroup = any(sg is None for sg in subgroups)
                # If there are duplicate non-None subgroups or any whole-class session alongside others
                if has_none_subgroup or len(subgroups) != len(set(subgroups)):
                    c_name = class_map[class_id].name if class_id in class_map else class_id
                    session_ids = [s.id for s in sess_list]
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.CLASS_DOUBLE_BOOKING,
                            is_hard=True,
                            severity="ERROR",
                            message=(
                                f"Class '{c_name}' has overlapping sessions on Day {day}, Period {period}."
                            ),
                            involved_sessions=session_ids,
                            involved_classes=[class_id],
                        )
                    )

        # Check room double bookings
        for (room_id, day, period), sess_list in room_slots.items():
            if len(sess_list) > 1:
                r_name = room_map[room_id].name if room_id in room_map else room_id
                session_ids = [s.id for s in sess_list]
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.ROOM_DOUBLE_BOOKING,
                        is_hard=True,
                        severity="ERROR",
                        message=(
                            f"Room '{r_name}' is double-booked on Day {day}, Period {period} "
                            f"by {len(sess_list)} sessions."
                        ),
                        involved_sessions=session_ids,
                        involved_rooms=[room_id],
                    )
                )

    def _check_availabilities(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        teacher_map: Dict[str, Teacher],
        room_map: Dict[str, Room],
        violations: List[ConstraintViolation],
    ) -> None:
        for s in sessions:
            # Teacher availability
            unavail_slots = bundle.teacher_availability.get(s.teacher_id, set())
            for p in s.occupied_periods:
                if (s.day_of_week, p) in unavail_slots:
                    t_name = teacher_map[s.teacher_id].name if s.teacher_id in teacher_map else s.teacher_id
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.TEACHER_UNAVAILABLE,
                            is_hard=True,
                            severity="ERROR",
                            message=f"Teacher '{t_name}' is marked unavailable on Day {s.day_of_week}, Period {p}.",
                            involved_sessions=[s.id],
                            involved_teachers=[s.teacher_id],
                        )
                    )

            # Room availability
            room_unavail = bundle.room_availability.get(s.room_id, set())
            for p in s.occupied_periods:
                if (s.day_of_week, p) in room_unavail:
                    r_name = room_map[s.room_id].name if s.room_id in room_map else s.room_id
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.ROOM_UNAVAILABLE,
                            is_hard=True,
                            severity="ERROR",
                            message=f"Room '{r_name}' is unavailable on Day {s.day_of_week}, Period {p}.",
                            involved_sessions=[s.id],
                            involved_rooms=[s.room_id],
                        )
                    )

    def _check_room_compatibility(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        room_map: Dict[str, Room],
        class_map: Dict[str, ClassGroup],
        unit_map: Dict[str, SchedulableUnit],
        violations: List[ConstraintViolation],
    ) -> None:
        for s in sessions:
            room = room_map.get(s.room_id)
            cls = class_map.get(s.class_group_id)

            if not room:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.ROOM_UNAVAILABLE,
                        is_hard=True,
                        severity="ERROR",
                        message=f"Assigned room '{s.room_id}' does not exist.",
                        involved_sessions=[s.id],
                        involved_rooms=[s.room_id],
                    )
                )
                continue

            # Capacity check
            if cls and room.capacity < cls.student_count:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.ROOM_CAPACITY_EXCEEDED,
                        is_hard=True,
                        severity="ERROR",
                        message=(
                            f"Room '{room.name}' capacity ({room.capacity}) is below "
                            f"class size ({cls.student_count}) for '{cls.name}'."
                        ),
                        involved_sessions=[s.id],
                        involved_rooms=[s.room_id],
                        involved_classes=[s.class_group_id],
                    )
                )

            # Room type compatibility check
            unit = unit_map.get(s.class_subject_assignment_id)
            if unit and unit.required_room_type and room.room_type != unit.required_room_type:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.ROOM_TYPE_MISMATCH,
                        is_hard=True,
                        severity="ERROR",
                        message=(
                            f"Room '{room.name}' type '{room.room_type.value}' does not match "
                            f"required type '{unit.required_room_type.value}'."
                        ),
                        involved_sessions=[s.id],
                        involved_rooms=[s.room_id],
                    )
                )

    def _check_teacher_workloads(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        teacher_map: Dict[str, Teacher],
        violations: List[ConstraintViolation],
    ) -> None:
        # Group sessions by teacher
        teacher_day_periods: Dict[str, Dict[int, List[int]]] = {}

        for s in sessions:
            day_map = teacher_day_periods.setdefault(s.teacher_id, {})
            day_map.setdefault(s.day_of_week, []).extend(s.occupied_periods)

        for teacher_id, rule in bundle.teacher_workload_rules.items():
            t_name = teacher_map[teacher_id].name if teacher_id in teacher_map else teacher_id
            day_map = teacher_day_periods.get(teacher_id, {})

            # Weekly total periods
            total_weekly = sum(len(periods) for periods in day_map.values())
            if total_weekly > rule.max_periods_per_week:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.TEACHER_MAX_HOURS_EXCEEDED,
                        is_hard=False,
                        severity="WARNING",
                        message=(
                            f"Teacher '{t_name}' assigned {total_weekly} periods/week, "
                            f"exceeding max rule ({rule.max_periods_per_week})."
                        ),
                        involved_teachers=[teacher_id],
                    )
                )

            # Daily periods & consecutive periods
            for day, periods in day_map.items():
                if len(periods) > rule.max_periods_per_day:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.TEACHER_MAX_HOURS_EXCEEDED,
                            is_hard=False,
                            severity="WARNING",
                            message=(
                                f"Teacher '{t_name}' assigned {len(periods)} periods on Day {day}, "
                                f"exceeding daily limit ({rule.max_periods_per_day})."
                            ),
                            involved_teachers=[teacher_id],
                        )
                    )

                # Calculate consecutive periods
                sorted_p = sorted(periods)
                current_consec = 0
                max_consec = 0
                prev = -99
                for p in sorted_p:
                    if p == prev + 1:
                        current_consec += 1
                    else:
                        current_consec = 1
                    prev = p
                    if current_consec > max_consec:
                        max_consec = current_consec

                if max_consec > rule.max_consecutive_periods:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.TEACHER_CONSECUTIVE_LIMIT,
                            is_hard=False,
                            severity="WARNING",
                            message=(
                                f"Teacher '{t_name}' has {max_consec} consecutive periods on Day {day}, "
                                f"exceeding limit of {rule.max_consecutive_periods}."
                            ),
                            involved_teachers=[teacher_id],
                        )
                    )

    def _check_soft_preferences(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        teacher_map: Dict[str, Teacher],
        violations: List[ConstraintViolation],
    ) -> None:
        for s in sessions:
            prefs = bundle.teacher_preferences.get(s.teacher_id, {})
            for p in s.occupied_periods:
                weight = prefs.get((s.day_of_week, p), 0)
                if weight < 0:
                    t_name = teacher_map[s.teacher_id].name if s.teacher_id in teacher_map else s.teacher_id
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.TEACHER_CONSECUTIVE_LIMIT,
                            is_hard=False,
                            severity="WARNING",
                            message=(
                                f"Teacher '{t_name}' prefers not to teach on Day {s.day_of_week}, "
                                f"Period {p} (dispreference weight: {weight})."
                            ),
                            involved_sessions=[s.id],
                            involved_teachers=[s.teacher_id],
                        )
                    )

    def _check_locked_assignments(
        self,
        sessions: List[ScheduledSession],
        unit_map: Dict[str, SchedulableUnit],
        violations: List[ConstraintViolation],
    ) -> None:
        for s in sessions:
            unit = unit_map.get(s.class_subject_assignment_id)
            if unit:
                if unit.locked_day is not None and s.day_of_week != unit.locked_day:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                            is_hard=True,
                            severity="ERROR",
                            message=(
                                f"Session '{s.id}' is placed on Day {s.day_of_week}, but is locked to Day {unit.locked_day}."
                            ),
                            involved_sessions=[s.id],
                        )
                    )
                if unit.locked_period is not None and s.start_period != unit.locked_period:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                            is_hard=True,
                            severity="ERROR",
                            message=(
                                f"Session '{s.id}' is placed at Period {s.start_period}, but is locked to Period {unit.locked_period}."
                            ),
                            involved_sessions=[s.id],
                        )
                    )
                if unit.locked_room_id is not None and s.room_id != unit.locked_room_id:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                            is_hard=True,
                            severity="ERROR",
                            message=(
                                f"Session '{s.id}' is assigned Room '{s.room_id}', but is locked to Room '{unit.locked_room_id}'."
                            ),
                            involved_sessions=[s.id],
                            involved_rooms=[s.room_id],
                        )
                    )

    def _check_locked_assignments(
        self,
        sessions: List[ScheduledSession],
        unit_map: Dict[str, SchedulableUnit],
        violations: List[ConstraintViolation],
    ) -> None:
        for s in sessions:
            unit = unit_map.get(s.id) or unit_map.get(s.class_subject_assignment_id)
            if not unit:
                continue
            if unit.locked_day is not None and s.day_of_week != unit.locked_day:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                        is_hard=True,
                        severity="ERROR",
                        message=f"Locked session '{s.id}' moved to day {s.day_of_week} (expected {unit.locked_day}).",
                        involved_sessions=[s.id],
                    )
                )
            if unit.locked_period is not None and s.start_period != unit.locked_period:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                        is_hard=True,
                        severity="ERROR",
                        message=f"Locked session '{s.id}' moved to period {s.start_period} (expected {unit.locked_period}).",
                        involved_sessions=[s.id],
                    )
                )
            if unit.locked_room_id is not None and s.room_id != unit.locked_room_id:
                violations.append(
                    ConstraintViolation(
                        violation_type=ConstraintType.LOCKED_ASSIGNMENT_VIOLATION,
                        is_hard=True,
                        severity="ERROR",
                        message=f"Locked session '{s.id}' moved to room '{s.room_id}' (expected '{unit.locked_room_id}').",
                        involved_sessions=[s.id],
                        involved_rooms=[s.room_id, unit.locked_room_id],
                    )
                )

    def _check_required_sessions(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        violations: List[ConstraintViolation],
        check_completeness: bool = False,
    ) -> None:
        if not check_completeness:
            return
        if len(bundle.units) > 0 and len(sessions) < len(bundle.units):
            scheduled_units = {s.class_subject_assignment_id for s in sessions} | {s.id for s in sessions}
            for u in bundle.units:
                if u.unit_id not in scheduled_units and u.assignment_id not in scheduled_units:
                    violations.append(
                        ConstraintViolation(
                            violation_type=ConstraintType.MISSING_SESSION_COUNT,
                            is_hard=True,
                            severity="ERROR",
                            message=f"Required session unit '{u.unit_id}' was not scheduled.",
                            involved_teachers=[u.teacher_id],
                            involved_classes=[u.class_group_id],
                        )
                    )


    @classmethod
    def calculate_metrics(
        cls,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        runtime_seconds: float = 0.0,
    ) -> OptimizationMetrics:
        """Calculates comprehensive schedule quality metrics."""
        validator = cls()
        violations = validator.validate(sessions, bundle)
        hard_violations = sum(1 for v in violations if v.is_hard)

        # 1. Teacher idle gaps
        teacher_day_slots: Dict[str, Dict[int, Set[int]]] = {}
        for s in sessions:
            for t_id in [s.teacher_id] + ([s.secondary_teacher_id] if s.secondary_teacher_id else []):
                teacher_day_slots.setdefault(t_id, {}).setdefault(s.day_of_week, set()).update(s.occupied_periods)

        total_teacher_gaps = 0
        for t_id, days_map in teacher_day_slots.items():
            for day, periods in days_map.items():
                if len(periods) > 1:
                    min_p = min(periods)
                    max_p = max(periods)
                    empty_in_span = 0
                    for p in range(min_p, max_p + 1):
                        if p not in periods and p not in bundle.break_periods:
                            empty_in_span += 1
                    total_teacher_gaps += empty_in_span

        # 2. Student idle gaps
        class_day_slots: Dict[str, Dict[int, Set[int]]] = {}
        for s in sessions:
            class_day_slots.setdefault(s.class_group_id, {}).setdefault(s.day_of_week, set()).update(s.occupied_periods)

        total_student_gaps = 0
        for c_id, days_map in class_day_slots.items():
            for day, periods in days_map.items():
                if len(periods) > 1:
                    min_p = min(periods)
                    max_p = max(periods)
                    empty_in_span = 0
                    for p in range(min_p, max_p + 1):
                        if p not in periods and p not in bundle.break_periods:
                            empty_in_span += 1
                    total_student_gaps += empty_in_span

        # 3. Teacher preference satisfaction
        total_prefs = 0
        satisfied_prefs = 0
        penalty_score = 0.0

        for s in sessions:
            prefs = bundle.teacher_preferences.get(s.teacher_id, {})
            for p in s.occupied_periods:
                slot = (s.day_of_week, p)
                if slot in prefs:
                    w = prefs[slot]
                    total_prefs += 1
                    if w > 0:
                        satisfied_prefs += 1
                        penalty_score -= w * (config.weight_teacher_preference / 10.0)
                    else:
                        penalty_score += abs(w) * (config.weight_teacher_preference / 10.0)

        pref_rate = (satisfied_prefs / total_prefs) if total_prefs > 0 else 1.0

        penalty_score += total_teacher_gaps * (config.weight_minimize_teacher_gaps / 10.0)
        penalty_score += total_student_gaps * (config.weight_minimize_student_gaps / 10.0)

        # 4. Room utilization
        total_room_slots = len(bundle.rooms) * len(bundle.days) * max(1, bundle.periods_per_day - len(bundle.break_periods))
        used_room_slots = sum(s.duration_periods for s in sessions)
        utilization = (used_room_slots / total_room_slots * 100.0) if total_room_slots > 0 else 0.0

        return OptimizationMetrics(
            total_hard_violations=hard_violations,
            soft_penalty_score=max(0.0, penalty_score),
            teacher_idle_gaps=total_teacher_gaps,
            student_idle_gaps=total_student_gaps,
            faculty_preference_satisfaction_rate=round(pref_rate, 3),
            room_utilization_percentage=round(min(100.0, utilization), 2),
            solver_runtime_seconds=round(runtime_seconds, 3),
        )
