"""
Repository for Institution, AcademicYear, and Semester entities.
Implements core.interfaces.Repository[Institution].
"""

import json
from typing import Any, Dict, List, Optional
from core.models import AcademicYear, Institution, Semester
from .base import BaseRepository


class InstitutionRepository(BaseRepository):
    """Persistence operations for institutions, academic years, and semesters."""

    # --- Institution Operations (Repository[Institution]) ---

    def get_by_id(self, entity_id: Any) -> Optional[Institution]:
        sql = """
            SELECT id, name, code, working_days, periods_per_day, period_duration_minutes, created_at
            FROM institutions WHERE id = ?;
        """
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return self._row_to_institution(row)

    def get_by_code(self, code: str) -> Optional[Institution]:
        sql = """
            SELECT id, name, code, working_days, periods_per_day, period_duration_minutes, created_at
            FROM institutions WHERE code = ?;
        """
        row = self.fetchone(sql, (code,))
        if not row:
            return None
        return self._row_to_institution(row)

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Institution]:
        sql = """
            SELECT id, name, code, working_days, periods_per_day, period_duration_minutes, created_at
            FROM institutions ORDER BY name ASC;
        """
        rows = self.fetchall(sql)
        return [self._row_to_institution(r) for r in rows]

    def save(self, entity: Institution) -> Institution:
        """Creates or updates an Institution record."""
        existing = self.get_by_id(str(entity.id))
        days_json = json.dumps(entity.working_days)
        if existing is None:
            sql = """
                INSERT INTO institutions (id, name, code, working_days, periods_per_day, period_duration_minutes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (
                    str(entity.id),
                    entity.name,
                    entity.code,
                    days_json,
                    entity.periods_per_day,
                    entity.period_duration_minutes,
                    entity.created_at,
                ),
            )
        else:
            sql = """
                UPDATE institutions
                SET name = ?, code = ?, working_days = ?, periods_per_day = ?, period_duration_minutes = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (
                    entity.name,
                    entity.code,
                    days_json,
                    entity.periods_per_day,
                    entity.period_duration_minutes,
                    str(entity.id),
                ),
            )
        return entity

    def create(self, entity: Institution) -> Institution:
        return self.save(entity)

    def update(self, entity: Institution) -> bool:
        self.save(entity)
        return True

    def delete(self, entity_id: Any) -> bool:
        sql = "DELETE FROM institutions WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0

    # --- Academic Year Operations ---

    def save_academic_year(self, year: AcademicYear) -> AcademicYear:
        existing = self.get_academic_year_by_id(str(year.id))
        if existing is None:
            sql = """
                INSERT INTO academic_years (id, name, start_date, end_date, is_current)
                VALUES (?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (str(year.id), year.name, year.start_date, year.end_date, 1 if year.is_current else 0),
            )
        else:
            sql = """
                UPDATE academic_years
                SET name = ?, start_date = ?, end_date = ?, is_current = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (year.name, year.start_date, year.end_date, 1 if year.is_current else 0, str(year.id)),
            )
        return year

    def create_academic_year(self, year: AcademicYear) -> AcademicYear:
        return self.save_academic_year(year)

    def get_academic_year_by_id(self, year_id: Any) -> Optional[AcademicYear]:
        sql = "SELECT id, name, start_date, end_date, is_current FROM academic_years WHERE id = ?;"
        row = self.fetchone(sql, (str(year_id),))
        if not row:
            return None
        return AcademicYear(
            id=row["id"],
            name=row["name"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            is_current=bool(row["is_current"]),
        )

    def list_academic_years(self, institution_id: Optional[Any] = None) -> List[AcademicYear]:
        sql = "SELECT id, name, start_date, end_date, is_current FROM academic_years ORDER BY name DESC;"
        rows = self.fetchall(sql)
        return [
            AcademicYear(
                id=r["id"],
                name=r["name"],
                start_date=r["start_date"],
                end_date=r["end_date"],
                is_current=bool(r["is_current"]),
            )
            for r in rows
        ]

    # --- Semester Operations ---

    def save_semester(self, semester: Semester) -> Semester:
        existing = self.get_semester_by_id(str(semester.id))
        if existing is None:
            sql = """
                INSERT INTO semesters (id, academic_year_id, number, term_name)
                VALUES (?, ?, ?, ?);
            """
            self.execute(
                sql,
                (str(semester.id), str(semester.academic_year_id), semester.number, semester.term_name),
            )
        else:
            sql = """
                UPDATE semesters
                SET academic_year_id = ?, number = ?, term_name = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (str(semester.academic_year_id), semester.number, semester.term_name, str(semester.id)),
            )
        return semester

    def create_semester(self, semester: Semester) -> Semester:
        return self.save_semester(semester)

    def get_semester_by_id(self, semester_id: Any) -> Optional[Semester]:
        sql = """
            SELECT id, academic_year_id, number, term_name
            FROM semesters WHERE id = ?;
        """
        row = self.fetchone(sql, (str(semester_id),))
        if not row:
            return None
        return Semester(
            id=row["id"],
            academic_year_id=row["academic_year_id"],
            number=row["number"],
            term_name=row["term_name"],
        )

    def list_semesters(self, academic_year_id: Optional[Any] = None) -> List[Semester]:
        if academic_year_id is not None:
            sql = """
                SELECT id, academic_year_id, number, term_name
                FROM semesters WHERE academic_year_id = ? ORDER BY number ASC;
            """
            rows = self.fetchall(sql, (str(academic_year_id),))
        else:
            sql = """
                SELECT id, academic_year_id, number, term_name
                FROM semesters ORDER BY number ASC;
            """
            rows = self.fetchall(sql)
        return [
            Semester(
                id=r["id"],
                academic_year_id=r["academic_year_id"],
                number=r["number"],
                term_name=r["term_name"],
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_institution(row) -> Institution:
        days = json.loads(row["working_days"]) if row["working_days"] else [0, 1, 2, 3, 4]
        return Institution(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            working_days=days,
            periods_per_day=row["periods_per_day"],
            period_duration_minutes=row["period_duration_minutes"],
            created_at=row["created_at"],
        )
