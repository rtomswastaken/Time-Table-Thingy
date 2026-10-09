"""
Unified Academic Management Service.
Implements the core.interfaces.AcademicService contract and integrates all domain sub-services.
"""

from typing import List, Optional
from core.interfaces import AcademicService as IAcademicService
from core.models import (
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomType,
    Subject,
    SubjectOffering,
    Teacher,
)
from database.connection import DatabaseManager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    RoomRepository,
    SubjectRepository,
    TeacherRepository,
)
from academic.class_service import ClassService
from academic.institution_service import InstitutionService
from academic.period_service import AcademicPeriodService
from academic.room_service import RoomService
from academic.subject_service import SubjectService
from academic.teacher_service import TeacherService


class AcademicService:
    """
    Unified academic management service fulfilling the core.interfaces.AcademicService protocol.
    Provides coordinated access to institutional, curricular, and physical resource operations.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        institution_repo: Optional[InstitutionRepository] = None,
        department_repo: Optional[DepartmentRepository] = None,
        class_repo: Optional[ClassGroupRepository] = None,
        teacher_repo: Optional[TeacherRepository] = None,
        subject_repo: Optional[SubjectRepository] = None,
        room_repo: Optional[RoomRepository] = None,
    ) -> None:
        self.db_manager = db_manager

        # Initialize repositories
        self.institution_repo = institution_repo or InstitutionRepository(db_manager)
        self.department_repo = department_repo or DepartmentRepository(db_manager)
        self.class_repo = class_repo or ClassGroupRepository(db_manager)
        self.teacher_repo = teacher_repo or TeacherRepository(db_manager)
        self.subject_repo = subject_repo or SubjectRepository(db_manager)
        self.room_repo = room_repo or RoomRepository(db_manager)

        # Initialize sub-services
        self.institution_service = InstitutionService(
            self.institution_repo, self.department_repo
        )
        self.period_service = AcademicPeriodService(self.institution_repo)
        self.class_service = ClassService(
            self.class_repo, self.department_repo, self.room_repo
        )
        self.teacher_service = TeacherService(
            self.teacher_repo, self.department_repo, self.subject_repo
        )
        self.subject_service = SubjectService(
            self.subject_repo, self.department_repo, self.class_repo, self.teacher_repo
        )
        self.room_service = RoomService(self.room_repo)

    # -------------------------------------------------------------------------
    # core.interfaces.AcademicService Protocol Implementation
    # -------------------------------------------------------------------------

    def create_department(self, institution_id: str, name: str, code: str) -> Department:
        return self.institution_service.create_department(institution_id, name, code)

    def create_teacher(
        self,
        department_id: str,
        name: str,
        employee_id: str,
        email: Optional[str] = None,
        is_full_time: bool = True,
    ) -> Teacher:
        return self.teacher_service.create_teacher(
            department_id=department_id,
            name=name,
            employee_id=employee_id,
            email=email,
            is_full_time=is_full_time,
        )

    def create_subject(
        self,
        department_id: str,
        code: str,
        name: str,
        credits: float,
        is_elective: bool = False,
    ) -> Subject:
        return self.subject_service.create_subject(
            department_id=department_id,
            code=code,
            name=name,
            credits=credits,
            is_elective=is_elective,
        )

    def create_offering(
        self,
        subject_id: str,
        semester_id: str,
        weekly_contact_hours: float,
        weekly_periods: int,
    ) -> SubjectOffering:
        return self.subject_service.create_offering(
            subject_id=subject_id,
            semester_id=semester_id,
            weekly_contact_hours=weekly_contact_hours,
            weekly_periods=weekly_periods,
        )

    def create_class_group(
        self,
        department_id: str,
        semester_id: str,
        name: str,
        student_count: int,
        home_room_id: Optional[str] = None,
    ) -> ClassGroup:
        return self.class_service.create_class_group(
            department_id=department_id,
            semester_id=semester_id,
            name=name,
            student_count=student_count,
            home_room_id=home_room_id,
        )

    def create_room(
        self,
        name: str,
        code: str,
        room_type: RoomType,
        capacity: int,
        building: Optional[str] = None,
    ) -> Room:
        return self.room_service.create_room(
            name=name,
            code=code,
            room_type=room_type,
            capacity=capacity,
            building=building,
        )

    def assign_subject_to_class(
        self,
        class_group_id: str,
        offering_id: str,
        primary_teacher_id: str,
        secondary_teacher_id: Optional[str] = None,
        student_group_id: Optional[str] = None,
    ) -> ClassSubjectAssignment:
        return self.subject_service.assign_subject_to_class(
            class_group_id=class_group_id,
            offering_id=offering_id,
            primary_teacher_id=primary_teacher_id,
            secondary_teacher_id=secondary_teacher_id,
            student_group_id=student_group_id,
        )
