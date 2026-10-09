"""
Academic Management Engine Package (Agent 3).
"""

from academic.academic_service import AcademicService
from academic.institution_service import InstitutionService
from academic.period_service import AcademicPeriodService
from academic.class_service import ClassService
from academic.teacher_service import TeacherService
from academic.subject_service import SubjectService
from academic.room_service import RoomService

__all__ = [
    "AcademicService",
    "InstitutionService",
    "AcademicPeriodService",
    "ClassService",
    "TeacherService",
    "SubjectService",
    "RoomService",
]
