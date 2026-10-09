"""
Repository for Subject, SubjectOffering, SubjectSessionRequirement, and ClassSubjectAssignment entities.
Implements core.interfaces.Repository[Subject].
"""

from typing import Any, Dict, List, Optional
from core.models import (
    ClassSubjectAssignment,
    RoomType,
    SessionType,
    Subject,
    SubjectOffering,
    SubjectSessionRequirement,
)
from .base import BaseRepository


class SubjectRepository(BaseRepository):
    """Persistence operations for subject catalogs, offerings, and session requirements."""

    # --- Subject Operations (Repository[Subject]) ---

    def get_by_id(self, entity_id: str) -> Optional[Subject]:
        sql = "SELECT id, department_id, code, name, credits, is_elective FROM subjects WHERE id = ?;"
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return self._row_to_subject(row)

    def get_by_code(self, department_id: str, code: str) -> Optional[Subject]:
        sql = "SELECT id, department_id, code, name, credits, is_elective FROM subjects WHERE department_id = ? AND code = ?;"
        row = self.fetchone(sql, (str(department_id), code))
        if not row:
            return None
        return self._row_to_subject(row)

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Subject]:
        sql = "SELECT id, department_id, code, name, credits, is_elective FROM subjects"
        params = []
        if filter_params and "department_id" in filter_params:
            sql += " WHERE department_id = ?"
            params.append(str(filter_params["department_id"]))
        sql += " ORDER BY code ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [self._row_to_subject(r) for r in rows]

    def list_by_department(self, department_id: str) -> List[Subject]:
        return self.list_all({"department_id": department_id})

    def save(self, entity: Subject) -> Subject:
        existing = self.get_by_id(str(entity.id))
        if existing is None:
            sql = """
                INSERT INTO subjects (id, department_id, code, name, credits, is_elective)
                VALUES (?, ?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (
                    str(entity.id),
                    str(entity.department_id),
                    entity.code,
                    entity.name,
                    entity.credits,
                    1 if entity.is_elective else 0,
                ),
            )
        else:
            sql = """
                UPDATE subjects
                SET department_id = ?, code = ?, name = ?, credits = ?, is_elective = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (
                    str(entity.department_id),
                    entity.code,
                    entity.name,
                    entity.credits,
                    1 if entity.is_elective else 0,
                    str(entity.id),
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        sql = "DELETE FROM subjects WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0

    # --- Subject Offerings ---

    def save_offering(self, offering: SubjectOffering) -> SubjectOffering:
        existing = self.get_offering_by_id(str(offering.id))
        if existing is None:
            sql = """
                INSERT INTO subject_offerings (id, subject_id, semester_id, weekly_contact_hours, weekly_periods)
                VALUES (?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (
                    str(offering.id),
                    str(offering.subject_id),
                    str(offering.semester_id),
                    offering.weekly_contact_hours,
                    offering.weekly_periods,
                ),
            )
        else:
            sql = """
                UPDATE subject_offerings
                SET subject_id = ?, semester_id = ?, weekly_contact_hours = ?, weekly_periods = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (
                    str(offering.subject_id),
                    str(offering.semester_id),
                    offering.weekly_contact_hours,
                    offering.weekly_periods,
                    str(offering.id),
                ),
            )
        return offering

    def get_offering_by_id(self, offering_id: str) -> Optional[SubjectOffering]:
        sql = """
            SELECT id, subject_id, semester_id, weekly_contact_hours, weekly_periods
            FROM subject_offerings WHERE id = ?;
        """
        row = self.fetchone(sql, (str(offering_id),))
        if not row:
            return None
        return SubjectOffering(
            id=row["id"],
            subject_id=row["subject_id"],
            semester_id=row["semester_id"],
            weekly_contact_hours=float(row["weekly_contact_hours"]),
            weekly_periods=int(row["weekly_periods"]),
        )

    def list_offerings(self, semester_id: Optional[str] = None) -> List[SubjectOffering]:
        if semester_id is not None:
            sql = """
                SELECT id, subject_id, semester_id, weekly_contact_hours, weekly_periods
                FROM subject_offerings WHERE semester_id = ? ORDER BY id ASC;
            """
            rows = self.fetchall(sql, (str(semester_id),))
        else:
            sql = """
                SELECT id, subject_id, semester_id, weekly_contact_hours, weekly_periods
                FROM subject_offerings ORDER BY id ASC;
            """
            rows = self.fetchall(sql)
        return [
            SubjectOffering(
                id=r["id"],
                subject_id=r["subject_id"],
                semester_id=r["semester_id"],
                weekly_contact_hours=float(r["weekly_contact_hours"]),
                weekly_periods=int(r["weekly_periods"]),
            )
            for r in rows
        ]

    def delete_offering(self, offering_id: str) -> bool:
        sql = "DELETE FROM subject_offerings WHERE id = ?;"
        cursor = self.execute(sql, (str(offering_id),))
        return cursor.rowcount > 0

    # --- Subject Session Requirements ---

    def save_session_requirement(self, req: SubjectSessionRequirement) -> SubjectSessionRequirement:
        sql = """
            INSERT INTO subject_session_requirements (
                id, offering_id, session_type, consecutive_periods,
                frequency_per_week, requires_lab, preferred_room_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                offering_id = excluded.offering_id,
                session_type = excluded.session_type,
                consecutive_periods = excluded.consecutive_periods,
                frequency_per_week = excluded.frequency_per_week,
                requires_lab = excluded.requires_lab,
                preferred_room_type = excluded.preferred_room_type;
        """
        self.execute(
            sql,
            (
                str(req.id),
                str(req.offering_id),
                req.session_type.value if isinstance(req.session_type, SessionType) else req.session_type,
                req.consecutive_periods,
                req.frequency_per_week,
                1 if req.requires_lab else 0,
                req.preferred_room_type.value if req.preferred_room_type else None,
            ),
        )
        return req

    def list_session_requirements(self, offering_id: str) -> List[SubjectSessionRequirement]:
        sql = """
            SELECT id, offering_id, session_type, consecutive_periods,
                   frequency_per_week, requires_lab, preferred_room_type
            FROM subject_session_requirements WHERE offering_id = ?;
        """
        rows = self.fetchall(sql, (str(offering_id),))
        return [
            SubjectSessionRequirement(
                id=r["id"],
                offering_id=r["offering_id"],
                session_type=SessionType(r["session_type"]),
                consecutive_periods=int(r["consecutive_periods"]),
                frequency_per_week=int(r["frequency_per_week"]),
                requires_lab=bool(r["requires_lab"]),
                preferred_room_type=RoomType(r["preferred_room_type"]) if r["preferred_room_type"] else None,
            )
            for r in rows
        ]

    # --- Class Subject Assignments ---

    def assign_subject_to_class(self, assignment: ClassSubjectAssignment) -> ClassSubjectAssignment:
        sql = """
            INSERT INTO class_subject_assignments (
                id, class_group_id, offering_id, primary_teacher_id,
                secondary_teacher_id, student_group_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(class_group_id, offering_id, student_group_id) DO UPDATE SET
                primary_teacher_id = excluded.primary_teacher_id,
                secondary_teacher_id = excluded.secondary_teacher_id;
        """
        self.execute(
            sql,
            (
                str(assignment.id),
                str(assignment.class_group_id),
                str(assignment.offering_id),
                str(assignment.primary_teacher_id),
                str(assignment.secondary_teacher_id) if assignment.secondary_teacher_id else None,
                str(assignment.student_group_id) if assignment.student_group_id else None,
            ),
        )
        return assignment

    def get_assignment_by_id(self, assignment_id: str) -> Optional[ClassSubjectAssignment]:
        sql = """
            SELECT id, class_group_id, offering_id, primary_teacher_id,
                   secondary_teacher_id, student_group_id
            FROM class_subject_assignments WHERE id = ?;
        """
        row = self.fetchone(sql, (str(assignment_id),))
        if not row:
            return None
        return ClassSubjectAssignment(
            id=row["id"],
            class_group_id=row["class_group_id"],
            offering_id=row["offering_id"],
            primary_teacher_id=row["primary_teacher_id"],
            secondary_teacher_id=row["secondary_teacher_id"],
            student_group_id=row["student_group_id"],
        )

    def list_assignments(
        self, class_group_id: Optional[str] = None, offering_id: Optional[str] = None
    ) -> List[ClassSubjectAssignment]:
        conditions = []
        params = []
        if class_group_id is not None:
            conditions.append("class_group_id = ?")
            params.append(str(class_group_id))
        if offering_id is not None:
            conditions.append("offering_id = ?")
            params.append(str(offering_id))

        sql = "SELECT id, class_group_id, offering_id, primary_teacher_id, secondary_teacher_id, student_group_id FROM class_subject_assignments"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY id ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [
            ClassSubjectAssignment(
                id=r["id"],
                class_group_id=r["class_group_id"],
                offering_id=r["offering_id"],
                primary_teacher_id=r["primary_teacher_id"],
                secondary_teacher_id=r["secondary_teacher_id"],
                student_group_id=r["student_group_id"],
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_subject(row) -> Subject:
        return Subject(
            id=row["id"],
            department_id=row["department_id"],
            code=row["code"],
            name=row["name"],
            credits=float(row["credits"]),
            is_elective=bool(row["is_elective"]),
        )
