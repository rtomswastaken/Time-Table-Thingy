"""
Subject, Curricular Offerings, and Class Assignment Service.
Manages course catalog, credit vs contact hour distinctions, session breakdown,
and teaching allocations.
"""

from typing import List, Optional
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import (
    ClassSubjectAssignment,
    RoomType,
    SessionType,
    Subject,
    SubjectOffering,
    SubjectSessionRequirement,
)
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    SubjectRepository,
    TeacherRepository,
)
from academic.validation import (
    validate_identifier,
    validate_non_negative_float,
    validate_non_negative_int,
    validate_session_requirements_consistency,
)


class SubjectService:
    """Service handling subjects, curricular offerings, session structures, and class assignments."""

    def __init__(
        self,
        subject_repo: SubjectRepository,
        department_repo: DepartmentRepository,
        class_repo: Optional[ClassGroupRepository] = None,
        teacher_repo: Optional[TeacherRepository] = None,
    ) -> None:
        self.subject_repo = subject_repo
        self.department_repo = department_repo
        self.class_repo = class_repo
        self.teacher_repo = teacher_repo

    # --- Subject Catalog Operations ---

    def create_subject(
        self,
        department_id: str,
        code: str,
        name: str,
        credits: float,
        is_elective: bool = False,
    ) -> Subject:
        dept = self.department_repo.get_by_id(str(department_id))
        if not dept:
            raise EntityNotFoundError(f"Department with id '{department_id}' not found.")

        code = validate_identifier(code, "Subject code")
        name = validate_identifier(name, "Subject name")
        credits = validate_non_negative_float(credits, "credits", min_val=0.0)

        # Unique code within department
        existing = self.subject_repo.get_by_code(str(department_id), code)
        if existing:
            raise ValidationError(
                f"Subject with code '{code}' already exists in this department."
            )

        subject = Subject(
            department_id=str(department_id),
            code=code,
            name=name,
            credits=credits,
            is_elective=is_elective,
        )
        return self.subject_repo.save(subject)

    def update_subject(
        self,
        subject_id: str,
        code: str,
        name: str,
        credits: float,
        is_elective: bool = False,
    ) -> Subject:
        subject = self.subject_repo.get_by_id(str(subject_id))
        if not subject:
            raise EntityNotFoundError(f"Subject with id '{subject_id}' not found.")

        code = validate_identifier(code, "Subject code")
        name = validate_identifier(name, "Subject name")
        credits = validate_non_negative_float(credits, "credits", min_val=0.0)

        existing = self.subject_repo.get_by_code(str(subject.department_id), code)
        if existing and str(existing.id) != str(subject.id):
            raise ValidationError(
                f"Subject with code '{code}' already exists in this department."
            )

        subject.code = code
        subject.name = name
        subject.credits = credits
        subject.is_elective = is_elective

        return self.subject_repo.save(subject)

    def get_subject(self, subject_id: str) -> Optional[Subject]:
        return self.subject_repo.get_by_id(str(subject_id))

    def get_subject_by_code(self, department_id: str, code: str) -> Optional[Subject]:
        return self.subject_repo.get_by_code(str(department_id), code)

    def list_subjects(
        self,
        department_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Subject]:
        filter_params = {}
        if department_id:
            filter_params["department_id"] = department_id
        subjects = self.subject_repo.list_all(filter_params if filter_params else None)

        if search:
            query = search.strip().lower()
            subjects = [
                s
                for s in subjects
                if query in s.name.lower() or query in s.code.lower()
            ]

        return subjects

    def delete_subject(self, subject_id: str) -> bool:
        s = self.subject_repo.get_by_id(str(subject_id))
        if not s:
            raise EntityNotFoundError(f"Subject with id '{subject_id}' not found.")
        return self.subject_repo.delete(str(subject_id))

    # --- Subject Offerings ---

    def create_offering(
        self,
        subject_id: str,
        semester_id: str,
        weekly_contact_hours: float,
        weekly_periods: int,
    ) -> SubjectOffering:
        subject = self.subject_repo.get_by_id(str(subject_id))
        if not subject:
            raise EntityNotFoundError(f"Subject with id '{subject_id}' not found.")

        weekly_contact_hours = validate_non_negative_float(
            weekly_contact_hours, "weekly_contact_hours", min_val=0.5
        )
        weekly_periods = validate_non_negative_int(
            weekly_periods, "weekly_periods", min_val=1
        )

        offering = SubjectOffering(
            subject_id=str(subject_id),
            semester_id=str(semester_id),
            weekly_contact_hours=weekly_contact_hours,
            weekly_periods=weekly_periods,
        )
        return self.subject_repo.save_offering(offering)

    def get_offering(self, offering_id: str) -> Optional[SubjectOffering]:
        return self.subject_repo.get_offering_by_id(str(offering_id))

    def list_offerings(self, semester_id: Optional[str] = None) -> List[SubjectOffering]:
        return self.subject_repo.list_offerings(semester_id)

    def delete_offering(self, offering_id: str) -> bool:
        offering = self.subject_repo.get_offering_by_id(str(offering_id))
        if not offering:
            raise EntityNotFoundError(f"Subject Offering with id '{offering_id}' not found.")
        return self.subject_repo.delete_offering(str(offering_id))

    # --- Session Requirements ---

    def add_session_requirement(
        self,
        offering_id: str,
        session_type: SessionType,
        consecutive_periods: int,
        frequency_per_week: int,
        requires_lab: bool = False,
        preferred_room_type: Optional[RoomType] = None,
    ) -> SubjectSessionRequirement:
        offering = self.subject_repo.get_offering_by_id(str(offering_id))
        if not offering:
            raise EntityNotFoundError(f"Subject Offering with id '{offering_id}' not found.")

        consecutive_periods = validate_non_negative_int(
            consecutive_periods, "consecutive_periods", min_val=1
        )
        frequency_per_week = validate_non_negative_int(
            frequency_per_week, "frequency_per_week", min_val=1
        )

        # Validate that adding this requirement doesn't exceed weekly_periods
        current_reqs = self.subject_repo.list_session_requirements(str(offering_id))
        projected_total = sum(r.total_periods for r in current_reqs) + (
            consecutive_periods * frequency_per_week
        )
        if projected_total > offering.weekly_periods:
            raise ValidationError(
                f"Adding this session requirement ({consecutive_periods}x{frequency_per_week} periods) "
                f"would bring total to {projected_total}, which exceeds offering's weekly_periods ({offering.weekly_periods})."
            )

        req = SubjectSessionRequirement(
            offering_id=str(offering_id),
            session_type=session_type,
            consecutive_periods=consecutive_periods,
            frequency_per_week=frequency_per_week,
            requires_lab=requires_lab,
            preferred_room_type=preferred_room_type,
        )
        return self.subject_repo.save_session_requirement(req)

    def list_session_requirements(
        self, offering_id: str
    ) -> List[SubjectSessionRequirement]:
        return self.subject_repo.list_session_requirements(str(offering_id))

    # --- Class Subject Assignments ---

    def assign_subject_to_class(
        self,
        class_group_id: str,
        offering_id: str,
        primary_teacher_id: str,
        secondary_teacher_id: Optional[str] = None,
        student_group_id: Optional[str] = None,
    ) -> ClassSubjectAssignment:
        offering = self.subject_repo.get_offering_by_id(str(offering_id))
        if not offering:
            raise EntityNotFoundError(f"Subject Offering with id '{offering_id}' not found.")

        if self.class_repo:
            cls = self.class_repo.get_by_id(str(class_group_id))
            if not cls:
                raise EntityNotFoundError(f"Class Group with id '{class_group_id}' not found.")

        if self.teacher_repo:
            t = self.teacher_repo.get_by_id(str(primary_teacher_id))
            if not t:
                raise EntityNotFoundError(f"Primary teacher with id '{primary_teacher_id}' not found.")

            if secondary_teacher_id:
                t2 = self.teacher_repo.get_by_id(str(secondary_teacher_id))
                if not t2:
                    raise EntityNotFoundError(
                        f"Secondary teacher with id '{secondary_teacher_id}' not found."
                    )

        assignment = ClassSubjectAssignment(
            class_group_id=str(class_group_id),
            offering_id=str(offering_id),
            primary_teacher_id=str(primary_teacher_id),
            secondary_teacher_id=str(secondary_teacher_id) if secondary_teacher_id else None,
            student_group_id=str(student_group_id) if student_group_id else None,
        )
        return self.subject_repo.assign_subject_to_class(assignment)

    def list_class_assignments(
        self,
        class_group_id: Optional[str] = None,
        offering_id: Optional[str] = None,
    ) -> List[ClassSubjectAssignment]:
        return self.subject_repo.list_assignments(class_group_id, offering_id)

    def delete_class_assignment(self, assignment_id: str) -> bool:
        return self.subject_repo.delete_class_assignment(str(assignment_id))
