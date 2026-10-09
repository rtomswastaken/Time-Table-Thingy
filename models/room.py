"""
Room and resource domain models.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Room:
    """A room or physical space where sessions take place."""
    id: Optional[int] = None
    department_id: Optional[int] = None  # None if shared institutional room
    building: str = ""
    room_number: str = ""
    name: str = ""
    room_type: str = "classroom"         # classroom, lecture_hall, computer_lab, lab, seminar_hall
    capacity: int = 40
    is_active: bool = True

    @property
    def display_name(self) -> str:
        if self.building:
            return f"{self.building} - {self.room_number} ({self.name})"
        return f"{self.room_number} ({self.name})"


@dataclass
class RoomEquipment:
    """Equipment present in a room."""
    id: Optional[int] = None
    room_id: int = 0
    equipment_name: str = ""
    quantity: int = 1


@dataclass
class RoomAvailability:
    """Availability of a room for a recurring weekly time slot."""
    id: Optional[int] = None
    room_id: int = 0
    day_of_week: int = 0
    period_index: int = 1
    is_available: bool = True
