"""
Academic Period (Academic Year and Semester) Service.
Manages academic calendars, semesters, and terms.
"""

from typing import List, Optional
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import AcademicYear, Semester
from database.repositories import InstitutionRepository
from academic.validation import validate_date_range, validate_identifier, validate_non_negative_int


class AcademicPeriodService:
    """Service handling Academic Years and Semesters."""

    def __init__(self, institution_repo: InstitutionRepository) -> None:
        self.institution_repo = institution_repo

    # --- Academic Year Operations ---

    def create_academic_year(
        self,
        name: str,
        start_date: str,
        end_date: str,
        is_current: bool = False,
    ) -> AcademicYear:
        name = validate_identifier(name, "Academic Year name")
        validate_date_range(start_date, end_date)

        year = AcademicYear(
            name=name,
            start_date=start_date.strip() if start_date else "",
            end_date=end_date.strip() if end_date else "",
            is_current=is_current,
        )
        return self.institution_repo.save_academic_year(year)

    def update_academic_year(
        self,
        year_id: str,
        name: str,
        start_date: str,
        end_date: str,
        is_current: bool,
    ) -> AcademicYear:
        year = self.institution_repo.get_academic_year_by_id(str(year_id))
        if not year:
            raise EntityNotFoundError(f"Academic Year with id '{year_id}' not found.")

        name = validate_identifier(name, "Academic Year name")
        validate_date_range(start_date, end_date)

        year.name = name
        year.start_date = start_date.strip() if start_date else ""
        year.end_date = end_date.strip() if end_date else ""
        year.is_current = is_current

        return self.institution_repo.save_academic_year(year)

    def get_academic_year(self, year_id: str) -> Optional[AcademicYear]:
        return self.institution_repo.get_academic_year_by_id(str(year_id))

    def list_academic_years(self) -> List[AcademicYear]:
        return self.institution_repo.list_academic_years()

    # --- Semester Operations ---

    def create_semester(
        self,
        academic_year_id: str,
        number: int,
        term_name: str,
    ) -> Semester:
        ay = self.institution_repo.get_academic_year_by_id(str(academic_year_id))
        if not ay:
            raise EntityNotFoundError(f"Academic Year with id '{academic_year_id}' not found.")

        number = validate_non_negative_int(number, "Semester number", min_val=1)
        term_name = validate_identifier(term_name, "Semester term name")

        # Check existing semesters in this year
        existing_semesters = self.institution_repo.list_semesters(str(academic_year_id))
        for sem in existing_semesters:
            if sem.number == number:
                raise ValidationError(
                    f"Semester number {number} already exists for academic year '{ay.name}'."
                )

        sem = Semester(
            academic_year_id=str(academic_year_id),
            number=number,
            term_name=term_name,
        )
        return self.institution_repo.save_semester(sem)

    def update_semester(
        self,
        semester_id: str,
        number: int,
        term_name: str,
    ) -> Semester:
        sem = self.institution_repo.get_semester_by_id(str(semester_id))
        if not sem:
            raise EntityNotFoundError(f"Semester with id '{semester_id}' not found.")

        number = validate_non_negative_int(number, "Semester number", min_val=1)
        term_name = validate_identifier(term_name, "Semester term name")

        # Check number uniqueness within same year
        existing_semesters = self.institution_repo.list_semesters(str(sem.academic_year_id))
        for existing in existing_semesters:
            if str(existing.id) != str(sem.id) and existing.number == number:
                raise ValidationError(
                    f"Semester number {number} already exists for this academic year."
                )

        sem.number = number
        sem.term_name = term_name
        return self.institution_repo.save_semester(sem)

    def get_semester(self, semester_id: str) -> Optional[Semester]:
        return self.institution_repo.get_semester_by_id(str(semester_id))

    def list_semesters(self, academic_year_id: Optional[str] = None) -> List[Semester]:
        return self.institution_repo.list_semesters(academic_year_id)
