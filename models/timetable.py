"""
Timetabling and scheduling domain models.

DOMAIN DISTINCTIONS:
1. Recurring Weekly Schedule vs Calendar Date: Time slots represent recurring weekly
   periods (day_of_week + period_index), not one-off calendar events.
2. Draft vs Published Timetables: Working timetables are drafts. Published timetables
   are preserved snapshots with immutable version identifiers.
3. Locked Sessions: Sessions pinned by users that cannot be moved by the solver.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TimetableStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class SchedulingConfig:
    """Configuration for institutional timetable grid."""
    id: Optional[int] = None
    institution_id: Optional[int] = None
    department_id: Optional[int] = None
    name: str = "Standard 5-Day Grid"
    days_per_week: int = 5
    periods_per_day: int = 6
    period_duration_minutes: int = 60
    start_time: str = "09:00"
    lunch_break_period: Optional[int] = 4
    break_duration_minutes: int = 45
    created_at: Optional[str] = None


@dataclass
class TimeSlot:
    """A recurring weekly period slot in the schedule grid."""
    id: Optional[int] = None
    config_id: int = 0
    day_of_week: int = 0     # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, etc.
    day_name: str = "Monday"
    period_index: int = 1    # 1-indexed (e.g. 1, 2, 3, 4, 5, 6)
    start_time: str = "09:00"
    end_time: str = "10:00"
    is_break: bool = False


@dataclass
class Timetable:
    """A timetable entity with versioning and status."""
    id: Optional[int] = None
    academic_year_id: int = 0
    semester_id: int = 0
    department_id: int = 0
    config_id: int = 0
    name: str = ""
    status: TimetableStatus = TimetableStatus.DRAFT
    version: int = 1
    description: str = ""
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class ScheduledSession:
    """An individual session placed on the weekly schedule."""
    id: Optional[int] = None
    timetable_id: int = 0
    offering_id: int = 0
    subject_id: int = 0
    class_group_id: int = 0
    teacher_id: int = 0
    room_id: int = 0
    time_slot_id: int = 0
    day_of_week: int = 0
    period_index: int = 1
    duration_periods: int = 1
    session_type: str = "theory"
    student_group_id: Optional[int] = None
    is_locked: bool = False
    lock_reason: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class LockedAssignment:
    """An immutable slot anchor requested by the user."""
    assignment_id: str
    day_of_week: int
    start_period: int
    room_id: Optional[str] = None

