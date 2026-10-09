"""
Institution and Department Management Service.
Handles institutional setup and department administration.
"""

from typing import List, Optional
from core.exceptions import ValidationError, EntityNotFoundError
from core.models import Department, Institution
from database.repositories import DepartmentRepository, InstitutionRepository
from academic.validation import validate_identifier, validate_non_negative_int


class InstitutionService:
    """Service handling Institution and Department domain operations."""

    def __init__(
        self,
        institution_repo: InstitutionRepository,
        department_repo: DepartmentRepository,
    ) -> None:
        self.institution_repo = institution_repo
        self.department_repo = department_repo

    # --- Institution Operations ---

    def get_or_create_default_institution(
        self, name: str = "Timetable Institute", code: str = "INST"
    ) -> Institution:
        institutions = self.institution_repo.list_all()
        if institutions:
            return institutions[0]

        inst = Institution(
            name=validate_identifier(name, "Institution name"),
            code=validate_identifier(code, "Institution code"),
            working_days=[0, 1, 2, 3, 4],
            periods_per_day=6,
            period_duration_minutes=60,
        )
        return self.institution_repo.save(inst)

    def get_institution(self, institution_id: str) -> Optional[Institution]:
        return self.institution_repo.get_by_id(str(institution_id))

    def update_institution(
        self,
        institution_id: str,
        name: str,
        code: str,
        working_days: List[int],
        periods_per_day: int,
        period_duration_minutes: int,
    ) -> Institution:
        inst = self.institution_repo.get_by_id(str(institution_id))
        if not inst:
            raise EntityNotFoundError(f"Institution with id '{institution_id}' not found.")

        name = validate_identifier(name, "Institution name")
        code = validate_identifier(code, "Institution code")
        periods_per_day = validate_non_negative_int(periods_per_day, "periods_per_day", min_val=1)
        period_duration_minutes = validate_non_negative_int(
            period_duration_minutes, "period_duration_minutes", min_val=15
        )

        if not working_days:
            raise ValidationError("Institution must have at least one working day.")

        for d in working_days:
            if not 0 <= d <= 6:
                raise ValidationError(f"Invalid day index: {d}. Must be 0 (Mon) to 6 (Sun).")

        inst.name = name
        inst.code = code
        inst.working_days = working_days
        inst.periods_per_day = periods_per_day
        inst.period_duration_minutes = period_duration_minutes

        return self.institution_repo.save(inst)

    def list_institutions(self) -> List[Institution]:
        return self.institution_repo.list_all()

    # --- Department Operations ---

    def create_department(self, institution_id: str, name: str, code: str) -> Department:
        inst = self.institution_repo.get_by_id(str(institution_id))
        if not inst:
            raise EntityNotFoundError(f"Institution with id '{institution_id}' not found.")

        name = validate_identifier(name, "Department name")
        code = validate_identifier(code, "Department code")

        # Check for duplicate code within this institution
        existing = self.department_repo.get_by_code(str(institution_id), code)
        if existing:
            raise ValidationError(
                f"Department with code '{code}' already exists in this institution."
            )

        dept = Department(
            institution_id=str(institution_id),
            name=name,
            code=code,
        )
        return self.department_repo.save(dept)

    def update_department(self, department_id: str, name: str, code: str) -> Department:
        dept = self.department_repo.get_by_id(str(department_id))
        if not dept:
            raise EntityNotFoundError(f"Department with id '{department_id}' not found.")

        name = validate_identifier(name, "Department name")
        code = validate_identifier(code, "Department code")

        # Check uniqueness if code is changed
        existing = self.department_repo.get_by_code(str(dept.institution_id), code)
        if existing and str(existing.id) != str(dept.id):
            raise ValidationError(
                f"Department with code '{code}' already exists in this institution."
            )

        dept.name = name
        dept.code = code
        return self.department_repo.save(dept)

    def get_department(self, department_id: str) -> Optional[Department]:
        return self.department_repo.get_by_id(str(department_id))

    def list_departments(self, institution_id: Optional[str] = None) -> List[Department]:
        if institution_id:
            return self.department_repo.list_by_institution(str(institution_id))
        return self.department_repo.list_all()

    def delete_department(self, department_id: str) -> bool:
        dept = self.department_repo.get_by_id(str(department_id))
        if not dept:
            raise EntityNotFoundError(f"Department with id '{department_id}' not found.")
        return self.department_repo.delete(str(department_id))
