"""Executive timetable summary metrics compilation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import ConstraintViolation, ScheduledSession, Timetable
from exchange.models import RoomUtilizationRow, TimetableSummary


class TimetableSummaryReportGenerator:
    """Computes high-level institutional quality and density metrics for a timetable."""

    @classmethod
    def generate_summary(
        cls,
        timetable: Timetable,
        sessions: List[ScheduledSession],
        violations: Optional[List[ConstraintViolation]] = None,
        unscheduled_count: int = 0,
        room_utilization_rows: Optional[List[RoomUtilizationRow]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimetableSummary:
        meta = metadata or {}
        period_duration_minutes = meta.get("period_duration_minutes", 60)

        unique_classes = {s.class_group_id for s in sessions}
        unique_teachers = {s.teacher_id for s in sessions}
        unique_rooms = {s.room_id for s in sessions}

        total_periods_placed = sum(s.duration_periods for s in sessions)
        total_hours = (total_periods_placed * period_duration_minutes) / 60.0

        all_violations = violations or []
        hard_violations = [v for v in all_violations if v.is_hard]
        is_valid = len(hard_violations) == 0

        avg_room_util = 0.0
        if room_utilization_rows and len(room_utilization_rows) > 0:
            avg_room_util = sum(r.utilization_rate for r in room_utilization_rows) / len(room_utilization_rows)

        return TimetableSummary(
            timetable_id=timetable.id,
            name=timetable.name,
            academic_year=meta.get("academic_year_name", timetable.academic_year_id),
            semester=meta.get("semester_name", timetable.semester_id),
            version=timetable.version,
            status="PUBLISHED" if timetable.is_published else "DRAFT",
            total_classes=len(unique_classes),
            total_teachers=len(unique_teachers),
            total_rooms=len(unique_rooms),
            total_sessions=len(sessions),
            total_periods_placed=total_periods_placed,
            total_hours_scheduled=round(total_hours, 1),
            conflict_count=len(all_violations),
            unscheduled_count=unscheduled_count,
            average_room_utilization=round(avg_room_util, 1),
            is_valid=is_valid,
        )
