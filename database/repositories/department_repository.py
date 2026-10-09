"""
Repository for Department entities.
Implements core.interfaces.Repository[Department].
"""

from typing import Any, Dict, List, Optional
from core.models import Department
from .base import BaseRepository


class DepartmentRepository(BaseRepository):
    """Persistence operations for academic departments."""

    def get_by_id(self, entity_id: str) -> Optional[Department]:
        sql = "SELECT id, institution_id, name, code FROM departments WHERE id = ?;"
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return Department(
            id=row["id"],
            institution_id=row["institution_id"],
            name=row["name"],
            code=row["code"],
        )

    def get_by_code(self, institution_id: str, code: str) -> Optional[Department]:
        sql = "SELECT id, institution_id, name, code FROM departments WHERE institution_id = ? AND code = ?;"
        row = self.fetchone(sql, (str(institution_id), code))
        if not row:
            return None
        return Department(
            id=row["id"],
            institution_id=row["institution_id"],
            name=row["name"],
            code=row["code"],
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Department]:
        sql = "SELECT id, institution_id, name, code FROM departments"
        params = []
        if filter_params and "institution_id" in filter_params:
            sql += " WHERE institution_id = ?"
            params.append(str(filter_params["institution_id"]))
        sql += " ORDER BY code ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [
            Department(
                id=r["id"],
                institution_id=r["institution_id"],
                name=r["name"],
                code=r["code"],
            )
            for r in rows
        ]

    def list_by_institution(self, institution_id: str) -> List[Department]:
        return self.list_all({"institution_id": institution_id})

    def save(self, entity: Department) -> Department:
        existing = self.get_by_id(str(entity.id))
        if existing is None:
            sql = """
                INSERT INTO departments (id, institution_id, name, code)
                VALUES (?, ?, ?, ?);
            """
            self.execute(sql, (str(entity.id), str(entity.institution_id), entity.name, entity.code))
        else:
            sql = """
                UPDATE departments
                SET institution_id = ?, name = ?, code = ?
                WHERE id = ?;
            """
            self.execute(sql, (str(entity.institution_id), entity.name, entity.code, str(entity.id)))
        return entity

    def delete(self, entity_id: str) -> bool:
        sql = "DELETE FROM departments WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0
