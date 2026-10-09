"""
Repository for ScheduledSession entities.
"""

from typing import List, Optional
from core.models import ScheduledSession
from .base import BaseRepository


class ScheduledSessionRepository(BaseRepository):
    """Persistence operations for individual scheduled periods in a timetable."""

    def get_by_id(self, session_id: str) -> Optional[ScheduledSession]:
        sql = """
            SELECT id, timetable_id, class_subject_assignment_id, day_of_week, start_period,
                   duration_periods, room_id, teacher_id, class_group_id, secondary_teacher_id,
                   student_group_id, is_locked
            FROM scheduled_sessions WHERE id = ?;
        """
        row = self.fetchone(sql, (str(session_id),))
        if not row:
            return None
        return self._row_to_session(row)

    def list_by_timetable(
        self,
        timetable_id: str,
        teacher_id: Optional[str] = None,
        room_id: Optional[str] = None,
        class_group_id: Optional[str] = None,
        day_of_week: Optional[int] = None,
    ) -> List[ScheduledSession]:
        conditions = ["timetable_id = ?"]
        params = [str(timetable_id)]

        if teacher_id is not None:
            conditions.append("teacher_id = ?")
            params.append(str(teacher_id))
        if room_id is not None:
            conditions.append("room_id = ?")
            params.append(str(room_id))
        if class_group_id is not None:
            conditions.append("class_group_id = ?")
            params.append(str(class_group_id))
        if day_of_week is not None:
            conditions.append("day_of_week = ?")
            params.append(day_of_week)

        sql = f"""
            SELECT id, timetable_id, class_subject_assignment_id, day_of_week, start_period,
                   duration_periods, room_id, teacher_id, class_group_id, secondary_teacher_id,
                   student_group_id, is_locked
            FROM scheduled_sessions
            WHERE {" AND ".join(conditions)}
            ORDER BY day_of_week ASC, start_period ASC;
        """
        rows = self.fetchall(sql, tuple(params))
        return [self._row_to_session(r) for r in rows]

    def save(self, session: ScheduledSession) -> ScheduledSession:
        sql = """
            INSERT INTO scheduled_sessions (
                id, timetable_id, class_subject_assignment_id, day_of_week,
                start_period, duration_periods, room_id, teacher_id,
                class_group_id, secondary_teacher_id, student_group_id, is_locked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                class_subject_assignment_id = excluded.class_subject_assignment_id,
                day_of_week = excluded.day_of_week,
                start_period = excluded.start_period,
                duration_periods = excluded.duration_periods,
                room_id = excluded.room_id,
                teacher_id = excluded.teacher_id,
                class_group_id = excluded.class_group_id,
                secondary_teacher_id = excluded.secondary_teacher_id,
                student_group_id = excluded.student_group_id,
                is_locked = excluded.is_locked;
        """
        self.execute(
            sql,
            (
                str(session.id),
                str(session.timetable_id),
                str(session.class_subject_assignment_id),
                session.day_of_week,
                session.start_period,
                session.duration_periods,
                str(session.room_id),
                str(session.teacher_id),
                str(session.class_group_id),
                str(session.secondary_teacher_id) if session.secondary_teacher_id else None,
                str(session.student_group_id) if session.student_group_id else None,
                1 if session.is_locked else 0,
            ),
        )
        return session

    def delete(self, session_id: str) -> bool:
        sql = "DELETE FROM scheduled_sessions WHERE id = ?;"
        cursor = self.execute(sql, (str(session_id),))
        return cursor.rowcount > 0

    def lock_session(self, session_id: str) -> bool:
        sql = "UPDATE scheduled_sessions SET is_locked = 1 WHERE id = ?;"
        cursor = self.execute(sql, (str(session_id),))
        return cursor.rowcount > 0

    def unlock_session(self, session_id: str) -> bool:
        sql = "UPDATE scheduled_sessions SET is_locked = 0 WHERE id = ?;"
        cursor = self.execute(sql, (str(session_id),))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_session(row) -> ScheduledSession:
        return ScheduledSession(
            id=row["id"],
            timetable_id=row["timetable_id"],
            class_subject_assignment_id=row["class_subject_assignment_id"],
            day_of_week=int(row["day_of_week"]),
            start_period=int(row["start_period"]),
            duration_periods=int(row["duration_periods"]),
            room_id=row["room_id"],
            teacher_id=row["teacher_id"],
            class_group_id=row["class_group_id"],
            secondary_teacher_id=row["secondary_teacher_id"],
            student_group_id=row["student_group_id"],
            is_locked=bool(row["is_locked"]),
        )
