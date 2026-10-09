"""
Classroom, Laboratory, and Resource Management Service.
Manages physical scheduling facilities, capacity, equipment, and room types.
"""

from typing import List, Optional
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import Room, RoomAvailability, RoomType
from database.repositories import RoomRepository
from academic.validation import validate_identifier, validate_non_negative_int


class RoomService:
    """Service handling classrooms, laboratories, and physical scheduling facilities."""

    def __init__(self, room_repo: RoomRepository) -> None:
        self.room_repo = room_repo

    def create_room(
        self,
        name: str,
        code: str,
        room_type: RoomType,
        capacity: int,
        building: Optional[str] = None,
        floor: Optional[int] = None,
    ) -> Room:
        name = validate_identifier(name, "Room name")
        code = validate_identifier(code, "Room code")
        capacity = validate_non_negative_int(capacity, "Room capacity", min_val=1)

        # Ensure unique code
        existing = self.room_repo.get_by_code(code)
        if existing:
            raise ValidationError(f"Room with code '{code}' already exists.")

        room = Room(
            name=name,
            code=code,
            room_type=room_type,
            capacity=capacity,
            building=building.strip() if building else None,
            floor=floor,
        )
        return self.room_repo.save(room)

    def update_room(
        self,
        room_id: str,
        name: str,
        code: str,
        room_type: RoomType,
        capacity: int,
        building: Optional[str] = None,
        floor: Optional[int] = None,
    ) -> Room:
        room = self.room_repo.get_by_id(str(room_id))
        if not room:
            raise EntityNotFoundError(f"Room with id '{room_id}' not found.")

        name = validate_identifier(name, "Room name")
        code = validate_identifier(code, "Room code")
        capacity = validate_non_negative_int(capacity, "Room capacity", min_val=1)

        existing = self.room_repo.get_by_code(code)
        if existing and str(existing.id) != str(room.id):
            raise ValidationError(f"Room with code '{code}' already exists.")

        room.name = name
        room.code = code
        room.room_type = room_type
        room.capacity = capacity
        room.building = building.strip() if building else None
        room.floor = floor

        return self.room_repo.save(room)

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.room_repo.get_by_id(str(room_id))

    def get_room_by_code(self, code: str) -> Optional[Room]:
        return self.room_repo.get_by_code(code.strip())

    def list_rooms(
        self,
        room_type: Optional[RoomType] = None,
        search: Optional[str] = None,
    ) -> List[Room]:
        filter_params = {}
        if room_type:
            filter_params["room_type"] = room_type

        rooms = self.room_repo.list_all(filter_params if filter_params else None)

        if search:
            query = search.strip().lower()
            rooms = [
                r
                for r in rooms
                if query in r.name.lower() or query in r.code.lower()
            ]

        return rooms

    def delete_room(self, room_id: str) -> bool:
        r = self.room_repo.get_by_id(str(room_id))
        if not r:
            raise EntityNotFoundError(f"Room with id '{room_id}' not found.")
        return self.room_repo.delete(str(room_id))

    # --- Room Availability Operations ---

    def set_room_availability(
        self,
        room_id: str,
        day_of_week: int,
        period_index: int,
        is_available: bool = True,
    ) -> RoomAvailability:
        room = self.room_repo.get_by_id(str(room_id))
        if not room:
            raise EntityNotFoundError(f"Room with id '{room_id}' not found.")

        if not 0 <= day_of_week <= 6:
            raise ValidationError(f"Invalid day_of_week: {day_of_week}. Must be 0 to 6.")
        if period_index < 0:
            raise ValidationError("period_index must be >= 0.")

        avail = RoomAvailability(
            room_id=str(room_id),
            day_of_week=day_of_week,
            period_index=period_index,
            is_available=is_available,
        )
        self.room_repo.set_availability(avail)
        return avail

    def is_room_available(self, room_id: str, day_of_week: int, period_index: int) -> bool:
        return self.room_repo.is_room_available(str(room_id), day_of_week, period_index)
