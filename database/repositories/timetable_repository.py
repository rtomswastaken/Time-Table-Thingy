"""
Repository for Timetable and ScheduledSession persistence.
Implements core.interfaces.TimetableRepository.
"""

from datetime import datetime, timezone
from typing import List, Optional
from core.models import ScheduledSession, Timetable
from .base import BaseRepository


class TimetableRepository(BaseRepository):
    """Persistence operations for timetable containers and session grids."""

    # --- TimetableRepository Protocol Implementation ---

    def get_by_id(self, timetable_id: str) -> Optional[Timetable]:
        sql = """
            SELECT id, name, academic_year_id, semester_id, version, is_published, created_at, updated_at
            FROM timetables WHERE id = ?;
        """
        row = self.fetchone(sql, (str(timetable_id),))
        if not row:
            return None
        return self._row_to_timetable(row)

    def list_timetables(self, semester_id: Optional[str] = None) -> List[Timetable]:
        if semester_id is not None:
            sql = """
                SELECT id, name, academic_year_id, semester_id, version, is_published, created_at, updated_at
                FROM timetables WHERE semester_id = ? ORDER BY version DESC, updated_at DESC;
            """
            rows = self.fetchall(sql, (str(semester_id),))
        else:
            sql = """
                SELECT id, name, academic_year_id, semester_id, version, is_published, created_at, updated_at
                FROM timetables ORDER BY version DESC, updated_at DESC;
            """
            rows = self.fetchall(sql)
        return [self._row_to_timetable(r) for r in rows]

    def get_sessions(self, timetable_id: str) -> List[ScheduledSession]:
        sql = """
            SELECT id, timetable_id, class_subject_assignment_id, day_of_week, start_period,
                   duration_periods, room_id, teacher_id, class_group_id, secondary_teacher_id,
                   student_group_id, is_locked
            FROM scheduled_sessions
            WHERE timetable_id = ?
            ORDER BY day_of_week ASC, start_period ASC;
        """
        rows = self.fetchall(sql, (str(timetable_id),))
        return [self._row_to_session(r) for r in rows]

    def save_timetable(self, timetable: Timetable, sessions: List[ScheduledSession]) -> None:
        """
        Atomically saves a Timetable and its associated ScheduledSessions.
        Preserves pinned/locked sessions if timetable already exists.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        timetable.updated_at = now_str

        with self.db_manager.transaction() as tx:
            # 1. Upsert Timetable
            tx.execute(
                """
                INSERT INTO timetables (id, name, academic_year_id, semester_id, version, is_published, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    academic_year_id = excluded.academic_year_id,
                    semester_id = excluded.semester_id,
                    version = excluded.version,
                    is_published = excluded.is_published,
                    updated_at = excluded.updated_at;
                """,
                (
                    str(timetable.id),
                    timetable.name,
                    str(timetable.academic_year_id),
                    str(timetable.semester_id),
                    timetable.version,
                    1 if timetable.is_published else 0,
                    timetable.created_at,
                    now_str,
                ),
            )

            # 2. Find currently locked sessions to preserve
            cursor = tx.execute(
                "SELECT id FROM scheduled_sessions WHERE timetable_id = ? AND is_locked = 1;",
                (str(timetable.id),),
            )
            locked_ids = {r[0] for r in cursor.fetchall()}

            # 3. Clear non-locked sessions
            tx.execute(
                "DELETE FROM scheduled_sessions WHERE timetable_id = ? AND is_locked = 0;",
                (str(timetable.id),),
            )

            # 4. Insert or update sessions
            insert_sql = """
                INSERT INTO scheduled_sessions (
                    id, timetable_id, class_subject_assignment_id, day_of_week,
                    start_period, duration_periods, room_id, teacher_id,
                    class_group_id, secondary_teacher_id, student_group_id, is_locked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
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
            for s in sessions:
                # If session was already locked in database and not explicitly modified, keep locked
                is_locked_val = 1 if (s.is_locked or str(s.id) in locked_ids) else 0
                tx.execute(
                    insert_sql,
                    (
                        str(s.id),
                        str(timetable.id),
                        str(s.class_subject_assignment_id),
                        s.day_of_week,
                        s.start_period,
                        s.duration_periods,
                        str(s.room_id),
                        str(s.teacher_id),
                        str(s.class_group_id),
                        str(s.secondary_teacher_id) if s.secondary_teacher_id else None,
                        str(s.student_group_id) if s.student_group_id else None,
                        is_locked_val,
                    ),
                )

    def update_session(self, session: ScheduledSession) -> None:
        sql = """
            UPDATE scheduled_sessions
            SET class_subject_assignment_id = ?, day_of_week = ?, start_period = ?,
                duration_periods = ?, room_id = ?, teacher_id = ?, class_group_id = ?,
                secondary_teacher_id = ?, student_group_id = ?, is_locked = ?
            WHERE id = ?;
        """
        self.execute(
            sql,
            (
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
                str(session.id),
            ),
        )

    def delete_session(self, session_id: str) -> bool:
        sql = "DELETE FROM scheduled_sessions WHERE id = ?;"
        cursor = self.execute(sql, (str(session_id),))
        return cursor.rowcount > 0

    def delete_timetable(self, timetable_id: str) -> bool:
        sql = "DELETE FROM timetables WHERE id = ?;"
        cursor = self.execute(sql, (str(timetable_id),))
        return cursor.rowcount > 0

    # --- Versioning & Publication Workflows ---

    def publish(self, timetable_id: str) -> Timetable:
        """
        Publishes a timetable. Ensures earlier published timetables are preserved
        and not overwritten.
        """
        tt = self.get_by_id(timetable_id)
        if not tt:
            raise ValueError(f"Timetable with ID {timetable_id} does not exist.")

        now_str = datetime.now(timezone.utc).isoformat()
        with self.db_manager.transaction() as tx:
            # Query highest version for this semester
            cursor = tx.execute(
                "SELECT MAX(version) FROM timetables WHERE semester_id = ? AND id != ?;",
                (str(tt.semester_id), str(tt.id)),
            )
            max_v = cursor.fetchone()[0]
            new_v = tt.version
            if max_v is not None and max_v >= new_v:
                new_v = max_v + 1

            tx.execute(
                "UPDATE timetables SET is_published = 1, version = ?, updated_at = ? WHERE id = ?;",
                (new_v, now_str, str(tt.id)),
            )

        updated = self.get_by_id(timetable_id)
        assert updated is not None
        return updated

    def clone_as_new_version(self, timetable_id: str, new_name: Optional[str] = None) -> Timetable:
        """
        Clones a timetable and all its sessions into a new draft version.
        Guarantees that original published timetables remain intact.
        """
        source = self.get_by_id(timetable_id)
        if not source:
            raise ValueError(f"Timetable with ID {timetable_id} does not exist.")

        sessions = self.get_sessions(timetable_id)

        # Determine next version
        conn = self.connection
        cursor = conn.execute(
            "SELECT MAX(version) FROM timetables WHERE semester_id = ?;",
            (str(source.semester_id),),
        )
        max_v = cursor.fetchone()[0] or 1
        next_v = max_v + 1

        import uuid
        new_tt = Timetable(
            id=str(uuid.uuid4()),
            name=new_name or f"{source.name} (v{next_v})",
            academic_year_id=source.academic_year_id,
            semester_id=source.semester_id,
            version=next_v,
            is_published=False,
        )

        cloned_sessions = []
        for s in sessions:
            cloned_sessions.append(
                ScheduledSession(
                    id=str(uuid.uuid4()),
                    timetable_id=new_tt.id,
                    class_subject_assignment_id=s.class_subject_assignment_id,
                    day_of_week=s.day_of_week,
                    start_period=s.start_period,
                    duration_periods=s.duration_periods,
                    room_id=s.room_id,
                    teacher_id=s.teacher_id,
                    class_group_id=s.class_group_id,
                    secondary_teacher_id=s.secondary_teacher_id,
                    student_group_id=s.student_group_id,
                    is_locked=s.is_locked,
                )
            )

        self.save_timetable(new_tt, cloned_sessions)
        return new_tt

    @staticmethod
    def _row_to_timetable(row) -> Timetable:
        return Timetable(
            id=row["id"],
            name=row["name"],
            academic_year_id=row["academic_year_id"],
            semester_id=row["semester_id"],
            version=int(row["version"]),
            is_published=bool(row["is_published"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

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
