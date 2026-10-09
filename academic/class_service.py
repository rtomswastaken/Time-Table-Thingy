"""
Class and Student Group Management Service.
Manages cohorts, class sections, fixed classroom allocations, and lab batches.
"""

from typing import List, Optional
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import ClassGroup, StudentGroup
from database.repositories import ClassGroupRepository, DepartmentRepository, RoomRepository
from academic.validation import validate_identifier, validate_non_negative_int


class ClassService:
    """Service handling classes, sections, and student subgroups."""

    def __init__(
        self,
        class_repo: ClassGroupRepository,
        department_repo: DepartmentRepository,
        room_repo: Optional[RoomRepository] = None,
    ) -> None:
        self.class_repo = class_repo
        self.department_repo = department_repo
        self.room_repo = room_repo

    def create_class_group(
        self,
        department_id: str,
        semester_id: str,
        name: str,
        student_count: int,
        home_room_id: Optional[str] = None,
    ) -> ClassGroup:
        dept = self.department_repo.get_by_id(str(department_id))
        if not dept:
            raise EntityNotFoundError(f"Department with id '{department_id}' not found.")

        name = validate_identifier(name, "Class name")
        student_count = validate_non_negative_int(student_count, "student_count", min_val=1)

        if home_room_id and self.room_repo:
            room = self.room_repo.get_by_id(str(home_room_id))
            if not room:
                raise EntityNotFoundError(f"Home room with id '{home_room_id}' not found.")

        # Check for duplicate class name within department and semester
        existing_classes = self.class_repo.list_all(
            {"department_id": department_id, "semester_id": semester_id}
        )
        for c in existing_classes:
            if c.name.lower() == name.lower():
                raise ValidationError(
                    f"Class '{name}' already exists in this department and semester."
                )

        class_group = ClassGroup(
            department_id=str(department_id),
            semester_id=str(semester_id),
            name=name,
            student_count=student_count,
            home_room_id=str(home_room_id) if home_room_id else None,
        )
        return self.class_repo.save(class_group)

    def update_class_group(
        self,
        class_group_id: str,
        name: str,
        student_count: int,
        home_room_id: Optional[str] = None,
    ) -> ClassGroup:
        class_group = self.class_repo.get_by_id(str(class_group_id))
        if not class_group:
            raise EntityNotFoundError(f"Class with id '{class_group_id}' not found.")

        name = validate_identifier(name, "Class name")
        student_count = validate_non_negative_int(student_count, "student_count", min_val=1)

        if home_room_id and self.room_repo:
            room = self.room_repo.get_by_id(str(home_room_id))
            if not room:
                raise EntityNotFoundError(f"Home room with id '{home_room_id}' not found.")

        # Check name uniqueness
        existing_classes = self.class_repo.list_all(
            {"department_id": class_group.department_id, "semester_id": class_group.semester_id}
        )
        for c in existing_classes:
            if str(c.id) != str(class_group.id) and c.name.lower() == name.lower():
                raise ValidationError(
                    f"Class '{name}' already exists in this department and semester."
                )

        class_group.name = name
        class_group.student_count = student_count
        class_group.home_room_id = str(home_room_id) if home_room_id else None

        return self.class_repo.save(class_group)

    def get_class_group(self, class_group_id: str) -> Optional[ClassGroup]:
        return self.class_repo.get_by_id(str(class_group_id))

    def list_class_groups(
        self,
        department_id: Optional[str] = None,
        semester_id: Optional[str] = None,
    ) -> List[ClassGroup]:
        filter_params = {}
        if department_id:
            filter_params["department_id"] = department_id
        if semester_id:
            filter_params["semester_id"] = semester_id
        return self.class_repo.list_all(filter_params if filter_params else None)

    def delete_class_group(self, class_group_id: str) -> bool:
        cls = self.class_repo.get_by_id(str(class_group_id))
        if not cls:
            raise EntityNotFoundError(f"Class with id '{class_group_id}' not found.")
        return self.class_repo.delete(str(class_group_id))

    # --- Student Group / Lab Batches ---

    def create_student_group(
        self, class_group_id: str, name: str, student_count: int
    ) -> StudentGroup:
        cls = self.class_repo.get_by_id(str(class_group_id))
        if not cls:
            raise EntityNotFoundError(f"Class with id '{class_group_id}' not found.")

        name = validate_identifier(name, "Student group name")
        student_count = validate_non_negative_int(student_count, "student_count", min_val=1)

        group = StudentGroup(
            class_group_id=str(class_group_id),
            name=name,
            student_count=student_count,
        )
        return self.class_repo.create_student_group(group)

    def list_student_groups(self, class_group_id: str) -> List[StudentGroup]:
        return self.class_repo.list_student_groups(str(class_group_id))

    def delete_student_group(self, student_group_id: str) -> bool:
        return self.class_repo.delete_student_group(str(student_group_id))
