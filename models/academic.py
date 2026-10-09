"""
Academic structure domain models.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Institution:
    """An academic institution (university, college, school)."""
    id: Optional[int] = None
    code: str = ""
    name: str = ""
    address: str = ""
    contact_email: str = ""


@dataclass
class Department:
    """An academic department within an institution."""
    id: Optional[int] = None
    institution_id: int = 0
    code: str = ""
    name: str = ""


@dataclass
class AcademicYear:
    """An academic year cycle (e.g. 2026-2027)."""
    id: Optional[int] = None
    institution_id: int = 0
    name: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False


@dataclass
class Semester:
    """A semester or academic term within an academic year."""
    id: Optional[int] = None
    academic_year_id: int = 0
    name: str = ""
    semester_number: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True


@dataclass
class ClassGroup:
    """A cohort or section of students (e.g. S3AD, Section A)."""
    id: Optional[int] = None
    department_id: int = 0
    semester_id: int = 0
    name: str = ""
    section: str = ""
    student_count: int = 0


@dataclass
class StudentGroup:
    """A subgroup or lab batch within a class group."""
    id: Optional[int] = None
    class_group_id: int = 0
    name: str = ""
    student_count: int = 0
