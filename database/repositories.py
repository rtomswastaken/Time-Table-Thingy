"""Database repository implementations for Timetable Thingy domain entities.

Fully aligned with core.models and core.interfaces.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from core.exceptions import EntityNotFoundError, RepositoryError
from core.models import (
    AcademicYear,
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomAvailability,
    RoomType,
    ScheduledSession,
    Semester,
    SessionType,
    StudentGroup,
    Subject,
    SubjectOffering,
    SubjectSessionRequirement,
    Teacher,
    TeacherAvailability,
    TeacherPreference,
    TeacherQualification,
    TeacherWorkloadRule,
    Timetable,
    TimetableVersion,
)
from database.connection import DatabaseManager


class InstitutionRepository:
    """Repository for Institution domain entity."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[Institution]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM institutions WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Institution(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            working_days=json.loads(row["working_days"]),
            periods_per_day=row["periods_per_day"],
            period_duration_minutes=row["period_duration_minutes"],
            created_at=row["created_at"],
        )

    def get_default(self) -> Optional[Institution]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM institutions ORDER BY created_at ASC LIMIT 1;")
        row = cur.fetchone()
        if not row:
            return None
        return self.get_by_id(row["id"])

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Institution]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM institutions ORDER BY name ASC;")
        rows = cur.fetchall()
        return [
            Institution(
                id=r["id"],
                name=r["name"],
                code=r["code"],
                working_days=json.loads(r["working_days"]),
                periods_per_day=r["periods_per_day"],
                period_duration_minutes=r["period_duration_minutes"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def save(self, entity: Institution) -> Institution:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO institutions (id, name, code, working_days, periods_per_day, period_duration_minutes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    code=excluded.code,
                    working_days=excluded.working_days,
                    periods_per_day=excluded.periods_per_day,
                    period_duration_minutes=excluded.period_duration_minutes;
                """,
                (
                    entity.id,
                    entity.name,
                    entity.code,
                    json.dumps(entity.working_days),
                    entity.periods_per_day,
                    entity.period_duration_minutes,
                    entity.created_at,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM institutions WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0


class DepartmentRepository:
    """Repository for Department domain entity."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[Department]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM departments WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Department(
            id=row["id"],
            institution_id=row["institution_id"],
            name=row["name"],
            code=row["code"],
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Department]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM departments WHERE 1=1"
        params: List[Any] = []
        if filter_params and "institution_id" in filter_params:
            sql += " AND institution_id = ?"
            params.append(filter_params["institution_id"])
        sql += " ORDER BY name ASC;"
        cur = conn.execute(sql, params)
        return [
            Department(
                id=r["id"],
                institution_id=r["institution_id"],
                name=r["name"],
                code=r["code"],
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: Department) -> Department:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO departments (id, institution_id, name, code)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    institution_id=excluded.institution_id,
                    name=excluded.name,
                    code=excluded.code;
                """,
                (entity.id, entity.institution_id, entity.name, entity.code),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM departments WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0


class AcademicPeriodRepository:
    """Repository for Academic Years and Semesters."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_year(self, year_id: str) -> Optional[AcademicYear]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM academic_years WHERE id = ?;", (year_id,))
        row = cur.fetchone()
        if not row:
            return None
        return AcademicYear(
            id=row["id"],
            name=row["name"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            is_current=bool(row["is_current"]),
        )

    def get_current_year(self) -> Optional[AcademicYear]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM academic_years WHERE is_current = 1 LIMIT 1;")
        row = cur.fetchone()
        if not row:
            return None
        return self.get_year(row["id"])

    def list_years(self) -> List[AcademicYear]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM academic_years ORDER BY start_date DESC;")
        return [
            AcademicYear(
                id=r["id"],
                name=r["name"],
                start_date=r["start_date"],
                end_date=r["end_date"],
                is_current=bool(r["is_current"]),
            )
            for r in cur.fetchall()
        ]

    def save_year(self, year: AcademicYear) -> AcademicYear:
        with self.db.transaction() as conn:
            if year.is_current:
                conn.execute("UPDATE academic_years SET is_current = 0;")
            conn.execute(
                """
                INSERT INTO academic_years (id, name, start_date, end_date, is_current)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    start_date=excluded.start_date,
                    end_date=excluded.end_date,
                    is_current=excluded.is_current;
                """,
                (year.id, year.name, year.start_date, year.end_date, 1 if year.is_current else 0),
            )
        return year

    def delete_year(self, year_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM academic_years WHERE id = ?;", (year_id,))
            return cur.rowcount > 0

    def get_semester(self, semester_id: str) -> Optional[Semester]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM semesters WHERE id = ?;", (semester_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Semester(
            id=row["id"],
            academic_year_id=row["academic_year_id"],
            number=row["number"],
            term_name=row["term_name"],
        )

    def list_semesters(self, academic_year_id: Optional[str] = None) -> List[Semester]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM semesters WHERE 1=1"
        params: List[Any] = []
        if academic_year_id:
            sql += " AND academic_year_id = ?"
            params.append(academic_year_id)
        sql += " ORDER BY number ASC;"
        cur = conn.execute(sql, params)
        return [
            Semester(
                id=r["id"],
                academic_year_id=r["academic_year_id"],
                number=r["number"],
                term_name=r["term_name"],
            )
            for r in cur.fetchall()
        ]

    def save_semester(self, semester: Semester) -> Semester:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO semesters (id, academic_year_id, number, term_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    academic_year_id=excluded.academic_year_id,
                    number=excluded.number,
                    term_name=excluded.term_name;
                """,
                (semester.id, semester.academic_year_id, semester.number, semester.term_name),
            )
        return semester

    def delete_semester(self, semester_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM semesters WHERE id = ?;", (semester_id,))
            return cur.rowcount > 0


class ClassRepository:
    """Repository for ClassGroups and StudentGroups."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[ClassGroup]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM class_groups WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return ClassGroup(
            id=row["id"],
            department_id=row["department_id"],
            semester_id=row["semester_id"],
            name=row["name"],
            student_count=row["student_count"],
            home_room_id=row["home_room_id"],
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[ClassGroup]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM class_groups WHERE 1=1"
        params: List[Any] = []
        if filter_params:
            if "department_id" in filter_params:
                sql += " AND department_id = ?"
                params.append(filter_params["department_id"])
            if "semester_id" in filter_params:
                sql += " AND semester_id = ?"
                params.append(filter_params["semester_id"])
        sql += " ORDER BY name ASC;"
        cur = conn.execute(sql, params)
        return [
            ClassGroup(
                id=r["id"],
                department_id=r["department_id"],
                semester_id=r["semester_id"],
                name=r["name"],
                student_count=r["student_count"],
                home_room_id=r["home_room_id"],
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: ClassGroup) -> ClassGroup:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO class_groups (id, department_id, semester_id, name, student_count, home_room_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    department_id=excluded.department_id,
                    semester_id=excluded.semester_id,
                    name=excluded.name,
                    student_count=excluded.student_count,
                    home_room_id=excluded.home_room_id;
                """,
                (
                    entity.id,
                    entity.department_id,
                    entity.semester_id,
                    entity.name,
                    entity.student_count,
                    entity.home_room_id,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM class_groups WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0

    def get_student_group(self, group_id: str) -> Optional[StudentGroup]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM student_groups WHERE id = ?;", (group_id,))
        row = cur.fetchone()
        if not row:
            return None
        return StudentGroup(
            id=row["id"],
            class_group_id=row["class_group_id"],
            name=row["name"],
            student_count=row["student_count"],
        )

    def list_student_groups(self, class_group_id: Optional[str] = None) -> List[StudentGroup]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM student_groups WHERE 1=1"
        params: List[Any] = []
        if class_group_id:
            sql += " AND class_group_id = ?"
            params.append(class_group_id)
        sql += " ORDER BY name ASC;"
        cur = conn.execute(sql, params)
        return [
            StudentGroup(
                id=r["id"],
                class_group_id=r["class_group_id"],
                name=r["name"],
                student_count=r["student_count"],
            )
            for r in cur.fetchall()
        ]

    def save_student_group(self, group: StudentGroup) -> StudentGroup:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO student_groups (id, class_group_id, name, student_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    class_group_id=excluded.class_group_id,
                    name=excluded.name,
                    student_count=excluded.student_count;
                """,
                (group.id, group.class_group_id, group.name, group.student_count),
            )
        return group

    def delete_student_group(self, group_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM student_groups WHERE id = ?;", (group_id,))
            return cur.rowcount > 0


class TeacherRepository:
    """Repository for Teachers, Qualifications, Availabilities, Preferences, and Workload Rules."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[Teacher]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM teachers WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Teacher(
            id=row["id"],
            department_id=row["department_id"],
            name=row["name"],
            employee_id=row["employee_id"],
            email=row["email"],
            is_full_time=bool(row["is_full_time"]),
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Teacher]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM teachers WHERE 1=1"
        params: List[Any] = []
        if filter_params:
            if "department_id" in filter_params:
                sql += " AND department_id = ?"
                params.append(filter_params["department_id"])
            if "search" in filter_params:
                term = f"%{filter_params['search'].strip()}%"
                sql += " AND (name LIKE ? OR employee_id LIKE ?)"
                params.extend([term, term])
        sql += " ORDER BY name ASC;"
        cur = conn.execute(sql, params)
        return [
            Teacher(
                id=r["id"],
                department_id=r["department_id"],
                name=r["name"],
                employee_id=r["employee_id"],
                email=r["email"],
                is_full_time=bool(r["is_full_time"]),
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: Teacher) -> Teacher:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO teachers (id, department_id, name, employee_id, email, is_full_time)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    department_id=excluded.department_id,
                    name=excluded.name,
                    employee_id=excluded.employee_id,
                    email=excluded.email,
                    is_full_time=excluded.is_full_time;
                """,
                (
                    entity.id,
                    entity.department_id,
                    entity.name,
                    entity.employee_id,
                    entity.email,
                    1 if entity.is_full_time else 0,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM teachers WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0

    # Qualifications
    def get_qualifications(self, teacher_id: Optional[str] = None) -> List[TeacherQualification]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM teacher_qualifications WHERE 1=1"
        params: List[Any] = []
        if teacher_id:
            sql += " AND teacher_id = ?"
            params.append(teacher_id)
        cur = conn.execute(sql, params)
        return [
            TeacherQualification(
                id=r["id"],
                teacher_id=r["teacher_id"],
                subject_id=r["subject_id"],
                competency_level=r["competency_level"],
                preference_score=r["preference_score"],
            )
            for r in cur.fetchall()
        ]

    def save_qualification(self, qual: TeacherQualification) -> TeacherQualification:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO teacher_qualifications (id, teacher_id, subject_id, competency_level, preference_score)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    competency_level=excluded.competency_level,
                    preference_score=excluded.preference_score;
                """,
                (qual.id, qual.teacher_id, qual.subject_id, qual.competency_level, qual.preference_score),
            )
        return qual

    def delete_qualification(self, qual_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM teacher_qualifications WHERE id = ?;", (qual_id,))
            return cur.rowcount > 0

    # Availabilities
    def get_availabilities(self, teacher_id: Optional[str] = None) -> List[TeacherAvailability]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM teacher_availabilities WHERE 1=1"
        params: List[Any] = []
        if teacher_id:
            sql += " AND teacher_id = ?"
            params.append(teacher_id)
        cur = conn.execute(sql, params)
        return [
            TeacherAvailability(
                id=r["id"],
                teacher_id=r["teacher_id"],
                day_of_week=r["day_of_week"],
                period_index=r["period_index"],
                is_available=bool(r["is_available"]),
            )
            for r in cur.fetchall()
        ]

    def set_availability(self, teacher_id: str, unavailable_slots: Set[Tuple[int, int]]) -> None:
        import uuid
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM teacher_availabilities WHERE teacher_id = ?;", (teacher_id,))
            for day, period in unavailable_slots:
                conn.execute(
                    """
                    INSERT INTO teacher_availabilities (id, teacher_id, day_of_week, period_index, is_available)
                    VALUES (?, ?, ?, ?, 0);
                    """,
                    (str(uuid.uuid4()), teacher_id, day, period),
                )

    # Preferences
    def get_preferences(self, teacher_id: Optional[str] = None) -> List[TeacherPreference]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM teacher_preferences WHERE 1=1"
        params: List[Any] = []
        if teacher_id:
            sql += " AND teacher_id = ?"
            params.append(teacher_id)
        cur = conn.execute(sql, params)
        return [
            TeacherPreference(
                id=r["id"],
                teacher_id=r["teacher_id"],
                day_of_week=r["day_of_week"],
                period_index=r["period_index"],
                preference_weight=r["preference_weight"],
            )
            for r in cur.fetchall()
        ]

    def set_preferences(self, teacher_id: str, preferences: Dict[Tuple[int, int], int]) -> None:
        import uuid
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM teacher_preferences WHERE teacher_id = ?;", (teacher_id,))
            for (day, period), weight in preferences.items():
                conn.execute(
                    """
                    INSERT INTO teacher_preferences (id, teacher_id, day_of_week, period_index, preference_weight)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (str(uuid.uuid4()), teacher_id, day, period, weight),
                )

    # Workload Rules
    def get_workload_rule(self, teacher_id: str) -> Optional[TeacherWorkloadRule]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM teacher_workload_rules WHERE teacher_id = ?;", (teacher_id,))
        row = cur.fetchone()
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

    def save_workload_rule(self, rule: TeacherWorkloadRule) -> TeacherWorkloadRule:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO teacher_workload_rules (id, teacher_id, max_periods_per_week, min_periods_per_week, max_periods_per_day, max_consecutive_periods)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(teacher_id) DO UPDATE SET
                    max_periods_per_week=excluded.max_periods_per_week,
                    min_periods_per_week=excluded.min_periods_per_week,
                    max_periods_per_day=excluded.max_periods_per_day,
                    max_consecutive_periods=excluded.max_consecutive_periods;
                """,
                (
                    rule.id,
                    rule.teacher_id,
                    rule.max_periods_per_week,
                    rule.min_periods_per_week,
                    rule.max_periods_per_day,
                    rule.max_consecutive_periods,
                ),
            )
        return rule


class SubjectRepository:
    """Repository for Subjects."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[Subject]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM subjects WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Subject(
            id=row["id"],
            department_id=row["department_id"],
            code=row["code"],
            name=row["name"],
            credits=row["credits"],
            is_elective=bool(row["is_elective"]),
        )

    def get_by_code(self, code: str) -> Optional[Subject]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM subjects WHERE code = ?;", (code,))
        row = cur.fetchone()
        if not row:
            return None
        return self.get_by_id(row["id"])

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Subject]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM subjects WHERE 1=1"
        params: List[Any] = []
        if filter_params:
            if "department_id" in filter_params:
                sql += " AND department_id = ?"
                params.append(filter_params["department_id"])
            if "search" in filter_params:
                term = f"%{filter_params['search'].strip()}%"
                sql += " AND (name LIKE ? OR code LIKE ?)"
                params.extend([term, term])
        sql += " ORDER BY code ASC;"
        cur = conn.execute(sql, params)
        return [
            Subject(
                id=r["id"],
                department_id=r["department_id"],
                code=r["code"],
                name=r["name"],
                credits=r["credits"],
                is_elective=bool(r["is_elective"]),
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: Subject) -> Subject:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO subjects (id, department_id, code, name, credits, is_elective)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    department_id=excluded.department_id,
                    code=excluded.code,
                    name=excluded.name,
                    credits=excluded.credits,
                    is_elective=excluded.is_elective;
                """,
                (
                    entity.id,
                    entity.department_id,
                    entity.code,
                    entity.name,
                    entity.credits,
                    1 if entity.is_elective else 0,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM subjects WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0


class SubjectOfferingRepository:
    """Repository for SubjectOfferings, SessionRequirements, and ClassSubjectAssignments."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[SubjectOffering]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM subject_offerings WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return SubjectOffering(
            id=row["id"],
            subject_id=row["subject_id"],
            semester_id=row["semester_id"],
            weekly_contact_hours=row["weekly_contact_hours"],
            weekly_periods=row["weekly_periods"],
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[SubjectOffering]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM subject_offerings WHERE 1=1"
        params: List[Any] = []
        if filter_params:
            if "semester_id" in filter_params:
                sql += " AND semester_id = ?"
                params.append(filter_params["semester_id"])
            if "subject_id" in filter_params:
                sql += " AND subject_id = ?"
                params.append(filter_params["subject_id"])
        sql += " ORDER BY id ASC;"
        cur = conn.execute(sql, params)
        return [
            SubjectOffering(
                id=r["id"],
                subject_id=r["subject_id"],
                semester_id=r["semester_id"],
                weekly_contact_hours=r["weekly_contact_hours"],
                weekly_periods=r["weekly_periods"],
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: SubjectOffering) -> SubjectOffering:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO subject_offerings (id, subject_id, semester_id, weekly_contact_hours, weekly_periods)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject_id=excluded.subject_id,
                    semester_id=excluded.semester_id,
                    weekly_contact_hours=excluded.weekly_contact_hours,
                    weekly_periods=excluded.weekly_periods;
                """,
                (
                    entity.id,
                    entity.subject_id,
                    entity.semester_id,
                    entity.weekly_contact_hours,
                    entity.weekly_periods,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM subject_offerings WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0

    # Session Requirements
    def get_requirements(self, offering_id: Optional[str] = None) -> List[SubjectSessionRequirement]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM subject_session_requirements WHERE 1=1"
        params: List[Any] = []
        if offering_id:
            sql += " AND offering_id = ?"
            params.append(offering_id)
        cur = conn.execute(sql, params)
        return [
            SubjectSessionRequirement(
                id=r["id"],
                offering_id=r["offering_id"],
                session_type=SessionType(r["session_type"]),
                consecutive_periods=r["consecutive_periods"],
                frequency_per_week=r["frequency_per_week"],
                requires_lab=bool(r["requires_lab"]),
                preferred_room_type=RoomType(r["preferred_room_type"]) if r["preferred_room_type"] else None,
            )
            for r in cur.fetchall()
        ]

    def save_requirement(self, req: SubjectSessionRequirement) -> SubjectSessionRequirement:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO subject_session_requirements (
                    id, offering_id, session_type, consecutive_periods, frequency_per_week, requires_lab, preferred_room_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    offering_id=excluded.offering_id,
                    session_type=excluded.session_type,
                    consecutive_periods=excluded.consecutive_periods,
                    frequency_per_week=excluded.frequency_per_week,
                    requires_lab=excluded.requires_lab,
                    preferred_room_type=excluded.preferred_room_type;
                """,
                (
                    req.id,
                    req.offering_id,
                    req.session_type.value,
                    req.consecutive_periods,
                    req.frequency_per_week,
                    1 if req.requires_lab else 0,
                    req.preferred_room_type.value if req.preferred_room_type else None,
                ),
            )
        return req

    def delete_requirement(self, req_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM subject_session_requirements WHERE id = ?;", (req_id,))
            return cur.rowcount > 0

    # Class Subject Assignments
    def get_assignment(self, assignment_id: str) -> Optional[ClassSubjectAssignment]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM class_subject_assignments WHERE id = ?;", (assignment_id,))
        row = cur.fetchone()
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
        conn = self.db.get_connection()
        sql = "SELECT * FROM class_subject_assignments WHERE 1=1"
        params: List[Any] = []
        if class_group_id:
            sql += " AND class_group_id = ?"
            params.append(class_group_id)
        if offering_id:
            sql += " AND offering_id = ?"
            params.append(offering_id)
        cur = conn.execute(sql, params)
        return [
            ClassSubjectAssignment(
                id=r["id"],
                class_group_id=r["class_group_id"],
                offering_id=r["offering_id"],
                primary_teacher_id=r["primary_teacher_id"],
                secondary_teacher_id=r["secondary_teacher_id"],
                student_group_id=r["student_group_id"],
            )
            for r in cur.fetchall()
        ]

    def save_assignment(self, assign: ClassSubjectAssignment) -> ClassSubjectAssignment:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO class_subject_assignments (
                    id, class_group_id, offering_id, primary_teacher_id, secondary_teacher_id, student_group_id
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    class_group_id=excluded.class_group_id,
                    offering_id=excluded.offering_id,
                    primary_teacher_id=excluded.primary_teacher_id,
                    secondary_teacher_id=excluded.secondary_teacher_id,
                    student_group_id=excluded.student_group_id;
                """,
                (
                    assign.id,
                    assign.class_group_id,
                    assign.offering_id,
                    assign.primary_teacher_id,
                    assign.secondary_teacher_id,
                    assign.student_group_id,
                ),
            )
        return assign

    def delete_assignment(self, assign_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM class_subject_assignments WHERE id = ?;", (assign_id,))
            return cur.rowcount > 0


class RoomRepository:
    """Repository for Rooms and Room Availability."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, entity_id: str) -> Optional[Room]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM rooms WHERE id = ?;", (entity_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Room(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            room_type=RoomType(row["room_type"]),
            capacity=row["capacity"],
            building=row["building"],
            floor=row["floor"],
        )

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Room]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM rooms WHERE 1=1"
        params: List[Any] = []
        if filter_params:
            if "room_type" in filter_params:
                sql += " AND room_type = ?"
                params.append(filter_params["room_type"])
            if "search" in filter_params:
                term = f"%{filter_params['search'].strip()}%"
                sql += " AND (name LIKE ? OR code LIKE ?)"
                params.extend([term, term])
        sql += " ORDER BY name ASC;"
        cur = conn.execute(sql, params)
        return [
            Room(
                id=r["id"],
                name=r["name"],
                code=r["code"],
                room_type=RoomType(r["room_type"]),
                capacity=r["capacity"],
                building=r["building"],
                floor=r["floor"],
            )
            for r in cur.fetchall()
        ]

    def save(self, entity: Room) -> Room:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO rooms (id, name, code, room_type, capacity, building, floor)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    code=excluded.code,
                    room_type=excluded.room_type,
                    capacity=excluded.capacity,
                    building=excluded.building,
                    floor=excluded.floor;
                """,
                (
                    entity.id,
                    entity.name,
                    entity.code,
                    entity.room_type.value,
                    entity.capacity,
                    entity.building,
                    entity.floor,
                ),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM rooms WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0

    def get_availabilities(self, room_id: Optional[str] = None) -> List[RoomAvailability]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM room_availabilities WHERE 1=1"
        params: List[Any] = []
        if room_id:
            sql += " AND room_id = ?"
            params.append(room_id)
        cur = conn.execute(sql, params)
        return [
            RoomAvailability(
                id=r["id"],
                room_id=r["room_id"],
                day_of_week=r["day_of_week"],
                period_index=r["period_index"],
                is_available=bool(r["is_available"]),
            )
            for r in cur.fetchall()
        ]

    def set_availability(self, room_id: str, unavailable_slots: Set[Tuple[int, int]]) -> None:
        import uuid
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM room_availabilities WHERE room_id = ?;", (room_id,))
            for day, period in unavailable_slots:
                conn.execute(
                    """
                    INSERT INTO room_availabilities (id, room_id, day_of_week, period_index, is_available)
                    VALUES (?, ?, ?, ?, 0);
                    """,
                    (str(uuid.uuid4()), room_id, day, period),
                )


class TimetableRepository:
    """Specialized repository for Timetable containers and their assigned sessions."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def get_by_id(self, timetable_id: str) -> Optional[Timetable]:
        conn = self.db.get_connection()
        cur = conn.execute("SELECT * FROM timetables WHERE id = ?;", (timetable_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Timetable(
            id=row["id"],
            name=row["name"],
            academic_year_id=row["academic_year_id"],
            semester_id=row["semester_id"],
            version=row["version"],
            is_published=bool(row["is_published"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_timetables(self, semester_id: Optional[str] = None) -> List[Timetable]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM timetables WHERE 1=1"
        params: List[Any] = []
        if semester_id:
            sql += " AND semester_id = ?"
            params.append(semester_id)
        sql += " ORDER BY updated_at DESC;"
        cur = conn.execute(sql, params)
        return [
            Timetable(
                id=r["id"],
                name=r["name"],
                academic_year_id=r["academic_year_id"],
                semester_id=r["semester_id"],
                version=r["version"],
                is_published=bool(r["is_published"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in cur.fetchall()
        ]

    def get_sessions(self, timetable_id: str) -> List[ScheduledSession]:
        conn = self.db.get_connection()
        cur = conn.execute(
            "SELECT * FROM scheduled_sessions WHERE timetable_id = ? ORDER BY day_of_week ASC, start_period ASC;",
            (timetable_id,),
        )
        return [
            ScheduledSession(
                id=r["id"],
                timetable_id=r["timetable_id"],
                class_subject_assignment_id=r["class_subject_assignment_id"],
                day_of_week=r["day_of_week"],
                start_period=r["start_period"],
                duration_periods=r["duration_periods"],
                room_id=r["room_id"],
                teacher_id=r["teacher_id"],
                class_group_id=r["class_group_id"],
                secondary_teacher_id=r["secondary_teacher_id"],
                student_group_id=r["student_group_id"],
                is_locked=bool(r["is_locked"]),
            )
            for r in cur.fetchall()
        ]

    def save_timetable(self, timetable: Timetable, sessions: List[ScheduledSession]) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO timetables (id, name, academic_year_id, semester_id, version, is_published, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    academic_year_id=excluded.academic_year_id,
                    semester_id=excluded.semester_id,
                    version=excluded.version,
                    is_published=excluded.is_published,
                    updated_at=excluded.updated_at;
                """,
                (
                    timetable.id,
                    timetable.name,
                    timetable.academic_year_id,
                    timetable.semester_id,
                    timetable.version,
                    1 if timetable.is_published else 0,
                    timetable.created_at,
                    timetable.updated_at,
                ),
            )

            # Preserve locked sessions or replace
            conn.execute("DELETE FROM scheduled_sessions WHERE timetable_id = ?;", (timetable.id,))
            for s in sessions:
                conn.execute(
                    """
                    INSERT INTO scheduled_sessions (
                        id, timetable_id, class_subject_assignment_id, day_of_week, start_period,
                        duration_periods, room_id, teacher_id, class_group_id, secondary_teacher_id,
                        student_group_id, is_locked
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        s.id,
                        timetable.id,
                        s.class_subject_assignment_id,
                        s.day_of_week,
                        s.start_period,
                        s.duration_periods,
                        s.room_id,
                        s.teacher_id,
                        s.class_group_id,
                        s.secondary_teacher_id,
                        s.student_group_id,
                        1 if s.is_locked else 0,
                    ),
                )

    def update_session(self, session: ScheduledSession) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE scheduled_sessions
                SET day_of_week = ?, start_period = ?, duration_periods = ?, room_id = ?, is_locked = ?
                WHERE id = ?;
                """,
                (
                    session.day_of_week,
                    session.start_period,
                    session.duration_periods,
                    session.room_id,
                    1 if session.is_locked else 0,
                    session.id,
                ),
            )

    def delete_session(self, session_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM scheduled_sessions WHERE id = ?;", (session_id,))
            return cur.rowcount > 0

    def delete_timetable(self, timetable_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM timetables WHERE id = ?;", (timetable_id,))
            return cur.rowcount > 0

    def save_version(self, version: TimetableVersion) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO timetable_versions (id, timetable_id, version, notes, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (version.id, version.timetable_id, version.version, version.notes, version.created_at),
            )

    def list_versions(self, timetable_id: str) -> List[TimetableVersion]:
        conn = self.db.get_connection()
        cur = conn.execute(
            "SELECT * FROM timetable_versions WHERE timetable_id = ? ORDER BY version DESC;",
            (timetable_id,),
        )
        return [
            TimetableVersion(
                id=r["id"],
                timetable_id=r["timetable_id"],
                version=r["version"],
                notes=r["notes"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]
