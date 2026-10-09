"""
Repository for Teacher, TeacherQualification, TeacherAvailability, and TeacherWorkloadRule entities.
Implements core.interfaces.Repository[Teacher].
"""

from typing import Any, Dict, List, Optional
from core.models import Teacher, TeacherAvailability, TeacherQualification, TeacherWorkloadRule
from .base import BaseRepository


class TeacherRepository(BaseRepository):
    """Persistence operations for faculty members."""

    # --- Profile Operations (Repository[Teacher]) ---

    def get_by_id(self, entity_id: str) -> Optional[Teacher]:
        sql = "SELECT id, department_id, name, employee_id, email, is_full_time FROM teachers WHERE id = ?;"
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return self._row_to_teacher(row)

    def get_by_employee_id(self, employee_id: str) -> Optional[Teacher]:
        sql = "SELECT id, department_id, name, employee_id, email, is_full_time FROM teachers WHERE employee_id = ?;"
        row = self.fetchone(sql, (employee_id,))
        if not row:
            return None
        return self._row_to_teacher(row)

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Teacher]:
        sql = "SELECT id, department_id, name, employee_id, email, is_full_time FROM teachers"
        params = []
        if filter_params and "department_id" in filter_params:
            sql += " WHERE department_id = ?"
            params.append(str(filter_params["department_id"]))
        sql += " ORDER BY name ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [self._row_to_teacher(r) for r in rows]

    def list_by_department(self, department_id: str) -> List[Teacher]:
        return self.list_all({"department_id": department_id})

    def save(self, entity: Teacher) -> Teacher:
        existing = self.get_by_id(str(entity.id))
        if existing is None:
            sql = """
                INSERT INTO teachers (id, department_id, name, employee_id, email, is_full_time)
                VALUES (?, ?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (
                    str(entity.id),
                    str(entity.department_id),
                    entity.name,
                    entity.employee_id,
                    entity.email,
                    1 if entity.is_full_time else 0,
                ),
            )
        else:
            sql = """
                UPDATE teachers
                SET department_id = ?, name = ?, employee_id = ?, email = ?, is_full_time = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (
                    str(entity.department_id),
                    entity.name,
                    entity.employee_id,
                    entity.email,
                    1 if entity.is_full_time else 0,
                    str(entity.id),
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        sql = "DELETE FROM teachers WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0

    # --- Qualification Operations (Teacher-to-Subject Eligibility) ---

    def add_qualification(self, qual: TeacherQualification) -> TeacherQualification:
        sql = """
            INSERT INTO teacher_qualifications (id, teacher_id, subject_id, competency_level, preference_score)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(teacher_id, subject_id)
            DO UPDATE SET competency_level = excluded.competency_level, preference_score = excluded.preference_score;
        """
        self.execute(
            sql,
            (str(qual.id), str(qual.teacher_id), str(qual.subject_id), qual.competency_level, qual.preference_score),
        )
        return qual

    def remove_qualification(self, teacher_id: str, subject_id: str) -> bool:
        sql = "DELETE FROM teacher_qualifications WHERE teacher_id = ? AND subject_id = ?;"
        cursor = self.execute(sql, (str(teacher_id), str(subject_id)))
        return cursor.rowcount > 0

    def list_qualifications_for_teacher(self, teacher_id: str) -> List[TeacherQualification]:
        sql = "SELECT id, teacher_id, subject_id, competency_level, preference_score FROM teacher_qualifications WHERE teacher_id = ?;"
        rows = self.fetchall(sql, (str(teacher_id),))
        return [
            TeacherQualification(
                id=r["id"],
                teacher_id=r["teacher_id"],
                subject_id=r["subject_id"],
                competency_level=r["competency_level"],
                preference_score=r["preference_score"],
            )
            for r in rows
        ]

    # --- Availability Operations ---

    def set_availability(self, avail: TeacherAvailability) -> None:
        sql = """
            INSERT INTO teacher_availabilities (id, teacher_id, day_of_week, period_index, is_available)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(teacher_id, day_of_week, period_index)
            DO UPDATE SET is_available = excluded.is_available;
        """
        self.execute(
            sql,
            (str(avail.id), str(avail.teacher_id), avail.day_of_week, avail.period_index, 1 if avail.is_available else 0),
        )

    def is_teacher_available(self, teacher_id: str, day_of_week: int, period_index: int) -> bool:
        sql = "SELECT is_available FROM teacher_availabilities WHERE teacher_id = ? AND day_of_week = ? AND period_index = ?;"
        row = self.fetchone(sql, (str(teacher_id), day_of_week, period_index))
        if row is None:
            return True
        return bool(row["is_available"])

    # --- Workload Rule Operations ---

    def save_workload_rule(self, rule: TeacherWorkloadRule) -> TeacherWorkloadRule:
        sql = """
            INSERT INTO teacher_workload_rules (
                id, teacher_id, max_periods_per_week, min_periods_per_week,
                max_periods_per_day, max_consecutive_periods
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(teacher_id) DO UPDATE SET
                max_periods_per_week = excluded.max_periods_per_week,
                min_periods_per_week = excluded.min_periods_per_week,
                max_periods_per_day = excluded.max_periods_per_day,
                max_consecutive_periods = excluded.max_consecutive_periods;
        """
        self.execute(
            sql,
            (
                str(rule.id),
                str(rule.teacher_id),
                rule.max_periods_per_week,
                rule.min_periods_per_week,
                rule.max_periods_per_day,
                rule.max_consecutive_periods,
            ),
        )
        return rule

    def get_workload_rule(self, teacher_id: str) -> Optional[TeacherWorkloadRule]:
        sql = """
            SELECT id, teacher_id, max_periods_per_week, min_periods_per_week,
                   max_periods_per_day, max_consecutive_periods
            FROM teacher_workload_rules WHERE teacher_id = ?;
        """
        row = self.fetchone(sql, (str(teacher_id),))
        if not row:
            return None
        return TeacherWorkloadRule(
            id=row["id"],
            teacher_id=row["teacher_id"],
            max_periods_per_week=row["max_periods_per_week"],
            min_periods_per_week=row["min_periods_per_week"],
            max_periods_per_day=row["max_periods_per_day"],
            max_consecutive_periods=row["max_consecutive_periods"],
        )

    @staticmethod
    def _row_to_teacher(row) -> Teacher:
        return Teacher(
            id=row["id"],
            department_id=row["department_id"],
            name=row["name"],
            employee_id=row["employee_id"],
            email=row["email"],
            is_full_time=bool(row["is_full_time"]),
        )
