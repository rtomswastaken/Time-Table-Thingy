"""Database and persistence package."""

from database.connection import DatabaseConnection, DatabaseManager, get_db, get_db_manager
from database.repositories import (
    BaseRepository,
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    PreferenceRepository,
    RoomRepository,
    ScheduledSessionRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from database.schema import check_foreign_keys, check_integrity, initialize_database

# Convenience aliases
ClassRepository = ClassGroupRepository

__all__ = [
    "DatabaseConnection",
    "DatabaseManager",
    "get_db",
    "get_db_manager",
    "initialize_database",
    "check_integrity",
    "check_foreign_keys",
    "BaseRepository",
    "InstitutionRepository",
    "DepartmentRepository",
    "ClassGroupRepository",
    "ClassRepository",
    "TeacherRepository",
    "SubjectRepository",
    "RoomRepository",
    "TimetableRepository",
    "ScheduledSessionRepository",
    "PreferenceRepository",
]
