"""
Subject and subject offering domain models.

DOMAIN DISTINCTIONS:
1. Credits vs Contact Hours: Academic credits and weekly contact hours are stored
   separately. Academic credits represent degree weighting; weekly contact hours
   represent physical classroom hours needed in the timetable.
2. Subject vs Subject Offering: A Subject is the catalog definition. A Subject Offering
   represents that subject being taught to a specific class group during a semester.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Subject:
    """
    Catalog definition of a course / subject.
    """
    id: Optional[int] = None
    department_id: int = 0
    code: str = ""
    name: str = ""
    credits: float = 3.0                    # Academic credits (degree weighting)
    weekly_contact_hours: int = 3           # Timetable hours per week (PHYSICAL HOURS)
    subject_type: str = "theory"            # theory, practical, lab, tutorial
    requires_lab: bool = False
    default_session_duration: int = 1       # Default slot length in periods (e.g. 1 for theory, 2 for lab)
    is_active: bool = True


@dataclass
class SubjectOffering:
    """
    Delivery of a Subject to a ClassGroup (or subgroup) during a Semester.
    """
    id: Optional[int] = None
    subject_id: int = 0
    class_group_id: int = 0
    semester_id: int = 0
    primary_teacher_id: Optional[int] = None    # Assigned teacher for this delivery
    student_group_id: Optional[int] = None      # Optional lab batch / subgroup
    weekly_sessions_required: int = 3           # Number of weekly meetings needed
    session_duration: int = 1                   # Duration per meeting in periods
    preferred_room_id: Optional[int] = None
