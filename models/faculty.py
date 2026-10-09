"""
Faculty and teacher domain models.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Teacher:
    """A faculty member / teacher profile."""
    id: Optional[int] = None
    department_id: int = 0
    employee_id: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    max_weekly_hours: int = 20
    min_weekly_hours: int = 0
    max_daily_hours: int = 4
    max_consecutive_hours: int = 2
    is_active: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class TeacherQualification:
    """
    Teacher qualification / eligibility for a subject.
    Indicates whether a teacher CAN teach a subject (competency/eligibility),
    distinct from whether they are currently assigned to teach it.
    """
    id: Optional[int] = None
    teacher_id: int = 0
    subject_id: int = 0
    competency_level: str = "primary"  # e.g., primary, secondary, qualified


@dataclass
class TeacherAvailability:
    """
    Availability of a teacher for a recurring weekly time slot.
    day_of_week: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday.
    period_index: 1-indexed period within the day.
    """
    id: Optional[int] = None
    teacher_id: int = 0
    day_of_week: int = 0
    period_index: int = 1
    is_available: bool = True


@dataclass
class TeacherPreference:
    """
    Teacher preference for scheduling.
    preference_type: 'time_slot', 'room', 'day_off', 'consecutive_limit'
    preference_score: integer scale (e.g. -2 = strongly avoid, 0 = neutral, +2 = strongly prefer)
    """
    id: Optional[int] = None
    teacher_id: int = 0
    preference_type: str = "time_slot"
    target_id: Optional[int] = None  # e.g. room_id or time_slot_id
    day_of_week: Optional[int] = None
    period_index: Optional[int] = None
    preference_score: int = 1
    notes: str = ""
