"""Room utilization report and spatial scheduling efficiency analytics.

Formula:
    Utilization Rate (%) = (Occupied Periods / Total Available Periods) * 100.0

Note:
    A lower utilization rate does not automatically imply operational waste.
    Specialist facilities (e.g., Hardware Labs, Workshops) are intentionally
    reserved for specialized curricula with lower weekly meeting frequencies.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from core.models import Institution, Room, RoomAvailability, ScheduledSession
from exchange.models import RoomUtilizationRow


class RoomUtilizationReportGenerator:
    """Calculates spatial occupancy and facility efficiency across institutional rooms."""

    @classmethod
    def generate_report(
        cls,
        rooms: List[Room],
        sessions: List[ScheduledSession],
        institution: Optional[Institution] = None,
        room_availabilities: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    ) -> List[RoomUtilizationRow]:
        """Calculates utilization rates per physical space.

        Args:
            rooms: List of all physical facilities.
            sessions: Placed scheduled sessions.
            institution: Academic institution with working days and periods per day.
            room_availabilities: Map of room_id -> unavailable slots {(day, period)}.
        """
        # Default working days: 5 days, 6 periods/day = 30 total periods
        working_days_count = len(institution.working_days) if institution and institution.working_days else 5
        periods_per_day = institution.periods_per_day if institution else 6
        base_weekly_slots = working_days_count * periods_per_day

        unavail_map = room_availabilities or {}

        # Group sessions by room
        sessions_by_room: Dict[str, List[ScheduledSession]] = {}
        for s in sessions:
            sessions_by_room.setdefault(s.room_id, []).append(s)

        report_rows: List[RoomUtilizationRow] = []

        for room in rooms:
            r_sessions = sessions_by_room.get(room.id, [])
            sessions_count = len(r_sessions)
            occupied_periods = sum(s.duration_periods for s in r_sessions)

            # Available slots for this specific room
            unavailable_slots_count = len(unavail_map.get(room.id, set()))
            available_periods = max(0, base_weekly_slots - unavailable_slots_count)

            # Avoid division by zero
            if available_periods > 0:
                utilization_rate = (occupied_periods / available_periods) * 100.0
            else:
                utilization_rate = 0.0

            # Generate insightful notes
            notes_parts: List[str] = []
            if available_periods == 0:
                notes_parts.append("Zero available periods configured for scheduling.")
            elif utilization_rate > 95.0:
                notes_parts.append("High utilization (>95%); facility near saturation limit.")
            elif utilization_rate < 20.0 and room.room_type.value != "LECTURE_HALL":
                notes_parts.append("Specialist facility; reserved for specialized curricular tracks.")
            elif utilization_rate < 20.0:
                notes_parts.append("Under-utilized standard room; available for supplementary scheduling.")

            report_rows.append(RoomUtilizationRow(
                room_id=room.id,
                room_code=room.code,
                room_name=room.name,
                room_type=room.room_type.value,
                capacity=room.capacity,
                building=room.building or "Main Campus",
                scheduled_sessions_count=sessions_count,
                occupied_periods=occupied_periods,
                available_periods=available_periods,
                utilization_rate=round(utilization_rate, 2),
                notes=" ".join(notes_parts) if notes_parts else "Normal utilization",
            ))

        return sorted(report_rows, key=lambda r: r.utilization_rate, reverse=True)
