"""
Repository package for Timetable Thingy database entities.
"""

from .base import BaseRepository
from .class_group_repository import ClassGroupRepository
from .department_repository import DepartmentRepository
from .institution_repository import InstitutionRepository
from .preference_repository import PreferenceRepository
from .room_repository import RoomRepository
from .scheduled_session_repository import ScheduledSessionRepository
from .subject_repository import SubjectRepository
from .teacher_repository import TeacherRepository
from .timetable_repository import TimetableRepository

# Backward-compatible aliases
AcademicPeriodRepository = InstitutionRepository
ClassRepository = ClassGroupRepository
SubjectOfferingRepository = SubjectRepository

__all__ = [
    "BaseRepository",
    "InstitutionRepository",
    "DepartmentRepository",
    "TeacherRepository",
    "SubjectRepository",
    "ClassGroupRepository",
    "RoomRepository",
    "TimetableRepository",
    "ScheduledSessionRepository",
    "PreferenceRepository",
    "AcademicPeriodRepository",
    "ClassRepository",
    "SubjectOfferingRepository",
]

