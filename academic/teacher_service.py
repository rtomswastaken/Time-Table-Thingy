"""
Teacher and Faculty Management Service.
Manages teacher profiles, departmental associations, and subject qualifications.
"""

from typing import List, Optional
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import Teacher, TeacherQualification
from database.repositories import DepartmentRepository, SubjectRepository, TeacherRepository
from academic.validation import validate_identifier


class TeacherService:
    """Service handling faculty profiles and subject qualifications."""

    def __init__(
        self,
        teacher_repo: TeacherRepository,
        department_repo: DepartmentRepository,
        subject_repo: Optional[SubjectRepository] = None,
    ) -> None:
        self.teacher_repo = teacher_repo
        self.department_repo = department_repo
        self.subject_repo = subject_repo

    def create_teacher(
        self,
        department_id: str,
        name: str,
        employee_id: str,
        email: Optional[str] = None,
        is_full_time: bool = True,
    ) -> Teacher:
        dept = self.department_repo.get_by_id(str(department_id))
        if not dept:
            raise EntityNotFoundError(f"Department with id '{department_id}' not found.")

        name = validate_identifier(name, "Teacher name")
        employee_id = validate_identifier(employee_id, "Teacher employee ID")

        # Check unique employee_id
        existing = self.teacher_repo.get_by_employee_id(employee_id)
        if existing:
            raise ValidationError(
                f"Teacher with employee ID '{employee_id}' already exists."
            )

        teacher = Teacher(
            department_id=str(department_id),
            name=name,
            employee_id=employee_id,
            email=email.strip() if email else None,
            is_full_time=is_full_time,
        )
        return self.teacher_repo.save(teacher)

    def update_teacher(
        self,
        teacher_id: str,
        name: str,
        employee_id: str,
        email: Optional[str] = None,
        is_full_time: bool = True,
    ) -> Teacher:
        teacher = self.teacher_repo.get_by_id(str(teacher_id))
        if not teacher:
            raise EntityNotFoundError(f"Teacher with id '{teacher_id}' not found.")

        name = validate_identifier(name, "Teacher name")
        employee_id = validate_identifier(employee_id, "Teacher employee ID")

        # Check uniqueness of employee_id if changed
        existing = self.teacher_repo.get_by_employee_id(employee_id)
        if existing and str(existing.id) != str(teacher.id):
            raise ValidationError(
                f"Teacher with employee ID '{employee_id}' already exists."
            )

        teacher.name = name
        teacher.employee_id = employee_id
        teacher.email = email.strip() if email else None
        teacher.is_full_time = is_full_time

        return self.teacher_repo.save(teacher)

    def get_teacher(self, teacher_id: str) -> Optional[Teacher]:
        return self.teacher_repo.get_by_id(str(teacher_id))

    def get_teacher_by_employee_id(self, employee_id: str) -> Optional[Teacher]:
        return self.teacher_repo.get_by_employee_id(employee_id.strip())

    def list_teachers(
        self,
        department_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Teacher]:
        filter_params = {}
        if department_id:
            filter_params["department_id"] = department_id
        teachers = self.teacher_repo.list_all(filter_params if filter_params else None)

        if search:
            query = search.strip().lower()
            teachers = [
                t
                for t in teachers
                if query in t.name.lower() or query in t.employee_id.lower()
            ]

        return teachers

    def delete_teacher(self, teacher_id: str) -> bool:
        t = self.teacher_repo.get_by_id(str(teacher_id))
        if not t:
            raise EntityNotFoundError(f"Teacher with id '{teacher_id}' not found.")
        return self.teacher_repo.delete(str(teacher_id))

    # --- Qualifications (Teacher - Subject Eligibility) ---

    def add_qualification(
        self,
        teacher_id: str,
        subject_id: str,
        competency_level: int = 1,
        preference_score: int = 5,
    ) -> TeacherQualification:
        teacher = self.teacher_repo.get_by_id(str(teacher_id))
        if not teacher:
            raise EntityNotFoundError(f"Teacher with id '{teacher_id}' not found.")

        if self.subject_repo:
            subject = self.subject_repo.get_by_id(str(subject_id))
            if not subject:
                raise EntityNotFoundError(f"Subject with id '{subject_id}' not found.")

        if not 1 <= competency_level <= 5:
            raise ValidationError("Competency level must be between 1 (Primary) and 5.")

        if not 1 <= preference_score <= 5:
            raise ValidationError("Preference score must be between 1 and 5.")

        qual = TeacherQualification(
            teacher_id=str(teacher_id),
            subject_id=str(subject_id),
            competency_level=competency_level,
            preference_score=preference_score,
        )
        return self.teacher_repo.add_qualification(qual)

    def get_qualifications_for_teacher(self, teacher_id: str) -> List[TeacherQualification]:
        return self.teacher_repo.list_qualifications_for_teacher(str(teacher_id))

    def get_teachers_qualified_for_subject(self, subject_id: str) -> List[Teacher]:
        sql = "SELECT teacher_id FROM teacher_qualifications WHERE subject_id = ?;"
        rows = self.teacher_repo.fetchall(sql, (str(subject_id),))
        teachers = []
        for r in rows:
            t = self.teacher_repo.get_by_id(r["teacher_id"])
            if t:
                teachers.append(t)
        return teachers

    def remove_qualification(self, teacher_id: str, subject_id: str) -> bool:
        return self.teacher_repo.remove_qualification(str(teacher_id), str(subject_id))
