"""Domain models and value objects for Timetable Thingy.

All entities are pure Python dataclasses with type hints and validation logic.
Supports both string UUIDs and SQLite integer IDs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.exceptions import ValidationError

EntityId = Union[str, int]


class SessionType(str, Enum):
    THEORY = "THEORY"
    LABORATORY = "LABORATORY"
    PRACTICAL = "PRACTICAL"
    TUTORIAL = "TUTORIAL"
    SEMINAR = "SEMINAR"
    PROJECT = "PROJECT"


class RoomType(str, Enum):
    LECTURE_HALL = "LECTURE_HALL"
    COMPUTER_LAB = "COMPUTER_LAB"
    HARDWARE_LAB = "HARDWARE_LAB"
    SEMINAR_ROOM = "SEMINAR_ROOM"
    WORKSHOP = "WORKSHOP"


class SchedulingStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NOT_STARTED = "NOT_STARTED"


class ConstraintType(str, Enum):
    TEACHER_DOUBLE_BOOKING = "TEACHER_DOUBLE_BOOKING"
    ROOM_DOUBLE_BOOKING = "ROOM_DOUBLE_BOOKING"
    CLASS_DOUBLE_BOOKING = "CLASS_DOUBLE_BOOKING"
    TEACHER_UNAVAILABLE = "TEACHER_UNAVAILABLE"
    ROOM_UNAVAILABLE = "ROOM_UNAVAILABLE"
    ROOM_CAPACITY_EXCEEDED = "ROOM_CAPACITY_EXCEEDED"
    ROOM_TYPE_MISMATCH = "ROOM_TYPE_MISMATCH"
    TEACHER_MAX_HOURS_EXCEEDED = "TEACHER_MAX_HOURS_EXCEEDED"
    TEACHER_CONSECUTIVE_LIMIT = "TEACHER_CONSECUTIVE_LIMIT"
    LOCKED_ASSIGNMENT_VIOLATION = "LOCKED_ASSIGNMENT_VIOLATION"
    LAB_CONTINUITY_BROKEN = "LAB_CONTINUITY_BROKEN"
    MISSING_SESSION_COUNT = "MISSING_SESSION_COUNT"


# ---------------------------------------------------------------------------
# Institution & Academic Structure
# ---------------------------------------------------------------------------


@dataclass
class Institution:
    name: str
    code: str
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    working_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # 0=Monday ... 4=Friday
    periods_per_day: int = 6
    period_duration_minutes: int = 60
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("Institution name cannot be empty.")
        if not str(self.code).strip():
            raise ValidationError("Institution code cannot be empty.")
        if not self.working_days:
            raise ValidationError("Institution must have at least one working day.")
        for d in self.working_days:
            if not 0 <= d <= 6:
                raise ValidationError(f"Invalid day index: {d}. Must be between 0 (Mon) and 6 (Sun).")
        if self.periods_per_day < 1:
            raise ValidationError("periods_per_day must be at least 1.")
        if self.period_duration_minutes < 15:
            raise ValidationError("period_duration_minutes must be at least 15 minutes.")


@dataclass
class Department:
    institution_id: EntityId
    name: str
    code: str
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("Department name cannot be empty.")
        if not str(self.code).strip():
            raise ValidationError("Department code cannot be empty.")


@dataclass
class AcademicYear:
    name: str
    start_date: str
    end_date: str
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    is_current: bool = True

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("Academic year name cannot be empty.")


@dataclass
class Semester:
    academic_year_id: EntityId
    number: int
    term_name: str
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValidationError("Semester number must be >= 1.")


@dataclass
class ClassGroup:
    department_id: EntityId
    semester_id: EntityId
    name: str
    student_count: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    home_room_id: Optional[EntityId] = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("ClassGroup name cannot be empty.")
        if self.student_count < 1:
            raise ValidationError("student_count must be at least 1.")


@dataclass
class StudentGroup:
    class_group_id: EntityId
    name: str
    student_count: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("StudentGroup name cannot be empty.")
        if self.student_count < 1:
            raise ValidationError("StudentGroup student_count must be at least 1.")


# ---------------------------------------------------------------------------
# Faculty & Preferences
# ---------------------------------------------------------------------------


@dataclass
class Teacher:
    department_id: EntityId
    name: str
    employee_id: str
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    email: Optional[str] = None
    is_full_time: bool = True

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("Teacher name cannot be empty.")
        if not str(self.employee_id).strip():
            raise ValidationError("Teacher employee_id cannot be empty.")


@dataclass
class TeacherQualification:
    teacher_id: EntityId
    subject_id: EntityId
    competency_level: int = 1  # 1 = primary, 2 = secondary
    preference_score: int = 5  # 1 (low) to 5 (high)
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TeacherAvailability:
    teacher_id: EntityId
    day_of_week: int
    period_index: int
    is_available: bool = True
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TeacherPreference:
    teacher_id: EntityId
    day_of_week: int
    period_index: int
    preference_weight: int = 0  # -10 (strongly avoid) to +10 (strongly prefer)
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TeacherWorkloadRule:
    teacher_id: EntityId
    max_periods_per_week: int = 20
    min_periods_per_week: int = 0
    max_periods_per_day: int = 5
    max_consecutive_periods: int = 3
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.max_periods_per_week < self.min_periods_per_week:
            raise ValidationError("max_periods_per_week cannot be less than min_periods_per_week.")
        if self.max_periods_per_day < 1:
            raise ValidationError("max_periods_per_day must be at least 1.")
        if self.max_consecutive_periods < 1:
            raise ValidationError("max_consecutive_periods must be at least 1.")


# ---------------------------------------------------------------------------
# Subjects & Curricular Offerings
# ---------------------------------------------------------------------------


@dataclass
class Subject:
    """Master course catalog definition."""
    department_id: EntityId
    code: str
    name: str
    credits: float
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    is_elective: bool = False

    def __post_init__(self) -> None:
        if not str(self.code).strip():
            raise ValidationError("Subject code cannot be empty.")
        if not str(self.name).strip():
            raise ValidationError("Subject name cannot be empty.")
        if self.credits < 0.0:
            raise ValidationError("Credits cannot be negative.")


@dataclass
class SubjectOffering:
    """Instantiation of a subject in a semester with weekly contact hours."""
    subject_id: EntityId
    semester_id: EntityId
    weekly_contact_hours: float
    weekly_periods: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.weekly_contact_hours <= 0.0:
            raise ValidationError("weekly_contact_hours must be positive.")
        if self.weekly_periods <= 0:
            raise ValidationError("weekly_periods must be positive.")


@dataclass
class SubjectSessionRequirement:
    """Specifies breakdown into discrete periods (e.g. 3 single lectures + 1 double lab)."""
    offering_id: EntityId
    session_type: SessionType
    consecutive_periods: int
    frequency_per_week: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    requires_lab: bool = False
    preferred_room_type: Optional[RoomType] = None

    def __post_init__(self) -> None:
        if self.consecutive_periods < 1:
            raise ValidationError("consecutive_periods must be at least 1.")
        if self.frequency_per_week < 1:
            raise ValidationError("frequency_per_week must be at least 1.")

    @property
    def total_periods(self) -> int:
        return self.consecutive_periods * self.frequency_per_week


@dataclass
class ClassSubjectAssignment:
    """Links a cohort to a subject offering and teacher."""
    class_group_id: EntityId
    offering_id: EntityId
    primary_teacher_id: EntityId
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    secondary_teacher_id: Optional[EntityId] = None
    student_group_id: Optional[EntityId] = None


# ---------------------------------------------------------------------------
# Physical Resources
# ---------------------------------------------------------------------------


@dataclass
class Room:
    name: str
    code: str
    room_type: RoomType
    capacity: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    building: Optional[str] = None
    floor: Optional[int] = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError("Room name cannot be empty.")
        if not str(self.code).strip():
            raise ValidationError("Room code cannot be empty.")
        if self.capacity < 1:
            raise ValidationError("Room capacity must be at least 1.")


@dataclass
class RoomAvailability:
    room_id: EntityId
    day_of_week: int
    period_index: int
    is_available: bool = True
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Timetabling & Placed Assignments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeSlot:
    day_of_week: int
    period_index: int
    start_time: str
    end_time: str
    is_break: bool = False


@dataclass(frozen=True)
class SchedulableUnit:
    """Discrete unit to be placed by the solver."""
    unit_id: EntityId
    assignment_id: EntityId
    class_group_id: EntityId
    subject_id: EntityId
    teacher_id: EntityId
    session_type: SessionType
    duration_periods: int
    secondary_teacher_id: Optional[EntityId] = None
    required_room_type: Optional[RoomType] = None
    student_group_id: Optional[EntityId] = None
    locked_day: Optional[int] = None
    locked_period: Optional[int] = None
    locked_room_id: Optional[EntityId] = None


@dataclass
class ScheduledSession:
    """Placed session in the recurring weekly schedule."""
    timetable_id: EntityId
    class_subject_assignment_id: EntityId
    day_of_week: int
    start_period: int
    duration_periods: int
    room_id: EntityId
    teacher_id: EntityId
    class_group_id: EntityId
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    secondary_teacher_id: Optional[EntityId] = None
    student_group_id: Optional[EntityId] = None
    is_locked: bool = False

    def __post_init__(self) -> None:
        if self.start_period < 0:
            raise ValidationError("start_period must be >= 0.")
        if self.duration_periods < 1:
            raise ValidationError("duration_periods must be >= 1.")

    @property
    def occupied_periods(self) -> List[int]:
        return list(range(self.start_period, self.start_period + self.duration_periods))


@dataclass
class Timetable:
    name: str
    academic_year_id: EntityId
    semester_id: EntityId
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    is_published: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TimetableVersion:
    timetable_id: EntityId
    version: int
    id: EntityId = field(default_factory=lambda: str(uuid.uuid4()))
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class LockedAssignment:
    assignment_id: EntityId
    day_of_week: int
    start_period: int
    room_id: Optional[EntityId] = None


# ---------------------------------------------------------------------------
# Validation & Metrics
# ---------------------------------------------------------------------------


@dataclass
class ConstraintViolation:
    violation_type: ConstraintType
    is_hard: bool
    severity: str
    message: str
    involved_sessions: List[EntityId] = field(default_factory=list)
    involved_teachers: List[EntityId] = field(default_factory=list)
    involved_rooms: List[EntityId] = field(default_factory=list)
    involved_classes: List[EntityId] = field(default_factory=list)


@dataclass
class OptimizationMetrics:
    total_hard_violations: int = 0
    soft_penalty_score: float = 0.0
    teacher_idle_gaps: int = 0
    student_idle_gaps: int = 0
    faculty_preference_satisfaction_rate: float = 1.0
    room_utilization_percentage: float = 0.0
    solver_runtime_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Solver Communication Bundles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulingConfig:
    time_limit_seconds: float = 60.0
    random_seed: int = 42
    allow_partial_solution: bool = False
    weight_teacher_preference: int = 10
    weight_minimize_teacher_gaps: int = 15
    weight_minimize_student_gaps: int = 20
    weight_preferred_room: int = 5
    weight_balanced_daily_load: int = 10


@dataclass(frozen=True)
class SchedulingInputBundle:
    institution_id: EntityId
    academic_year_id: EntityId
    semester_id: EntityId
    days: List[int]
    periods_per_day: int
    break_periods: Set[int]
    units: List[SchedulableUnit]
    teachers: List[Teacher]
    rooms: List[Room]
    class_groups: List[ClassGroup]
    teacher_availability: Dict[EntityId, Set[Tuple[int, int]]] = field(default_factory=dict)
    room_availability: Dict[EntityId, Set[Tuple[int, int]]] = field(default_factory=dict)
    teacher_workload_rules: Dict[EntityId, TeacherWorkloadRule] = field(default_factory=dict)
    teacher_preferences: Dict[EntityId, Dict[Tuple[int, int], int]] = field(default_factory=dict)


@dataclass(frozen=True)
class SolverProgress:
    phase: str
    elapsed_seconds: float
    best_objective_bound: Optional[float] = None
    is_feasible: bool = False
    message: str = ""


@dataclass(frozen=True)
class SchedulingResult:
    status: SchedulingStatus
    sessions: List[ScheduledSession] = field(default_factory=list)
    violations: List[ConstraintViolation] = field(default_factory=list)
    metrics: Optional[OptimizationMetrics] = None
    execution_time_seconds: float = 0.0
    message: str = ""
