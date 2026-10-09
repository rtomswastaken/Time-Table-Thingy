"""
Repository for ClassGroup and StudentGroup entities.
Implements core.interfaces.Repository[ClassGroup].
"""

from typing import Any, Dict, List, Optional
from core.models import ClassGroup, StudentGroup
from .base import BaseRepository


class ClassGroupRepository(BaseRepository):
    """Persistence operations for student cohorts and lab batches."""

    # --- ClassGroup Operations (Repository[ClassGroup]) ---

    def get_by_id(self, entity_id: str) -> Optional[ClassGroup]:
        sql = """
            SELECT id, department_id, semester_id, name, student_count, home_room_id
            FROM class_groups WHERE id = ?;
        """
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return self._row_to_class_group(row)

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[ClassGroup]:
        conditions = []
        params = []
        if filter_params:
            if "department_id" in filter_params:
                conditions.append("department_id = ?")
                params.append(str(filter_params["department_id"]))
            if "semester_id" in filter_params:
                conditions.append("semester_id = ?")
                params.append(str(filter_params["semester_id"]))

        sql = "SELECT id, department_id, semester_id, name, student_count, home_room_id FROM class_groups"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY name ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [self._row_to_class_group(r) for r in rows]

    def list_by_department(self, department_id: str) -> List[ClassGroup]:
        return self.list_all({"department_id": department_id})

    def list_by_semester(self, semester_id: str) -> List[ClassGroup]:
        return self.list_all({"semester_id": semester_id})

    def save(self, entity: ClassGroup) -> ClassGroup:
        existing = self.get_by_id(str(entity.id))
        if existing is None:
            sql = """
                INSERT INTO class_groups (id, department_id, semester_id, name, student_count, home_room_id)
                VALUES (?, ?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (
                    str(entity.id),
                    str(entity.department_id),
                    str(entity.semester_id),
                    entity.name,
                    entity.student_count,
                    str(entity.home_room_id) if entity.home_room_id else None,
                ),
            )
        else:
            sql = """
                UPDATE class_groups
                SET department_id = ?, semester_id = ?, name = ?, student_count = ?, home_room_id = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (
                    str(entity.department_id),
                    str(entity.semester_id),
                    entity.name,
                    entity.student_count,
                    str(entity.home_room_id) if entity.home_room_id else None,
                    str(entity.id),
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        sql = "DELETE FROM class_groups WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0

    # --- StudentGroup Operations (Batches / Subgroups) ---

    def create_student_group(self, group: StudentGroup) -> StudentGroup:
        sql = """
            INSERT INTO student_groups (id, class_group_id, name, student_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(class_group_id, name) DO UPDATE SET student_count = excluded.student_count;
        """
        self.execute(sql, (str(group.id), str(group.class_group_id), group.name, group.student_count))
        return group

    def list_student_groups(self, class_group_id: str) -> List[StudentGroup]:
        sql = "SELECT id, class_group_id, name, student_count FROM student_groups WHERE class_group_id = ? ORDER BY name ASC;"
        rows = self.fetchall(sql, (str(class_group_id),))
        return [
            StudentGroup(
                id=r["id"],
                class_group_id=r["class_group_id"],
                name=r["name"],
                student_count=int(r["student_count"]),
            )
            for r in rows
        ]

    def delete_student_group(self, group_id: str) -> bool:
        sql = "DELETE FROM student_groups WHERE id = ?;"
        cursor = self.execute(sql, (str(group_id),))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_class_group(row) -> ClassGroup:
        return ClassGroup(
            id=row["id"],
            department_id=row["department_id"],
            semester_id=row["semester_id"],
            name=row["name"],
            student_count=int(row["student_count"]),
            home_room_id=row["home_room_id"],
        )
