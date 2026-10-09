"""Core interface protocols for Timetable Thingy.

All agent contracts are defined here using typing.Protocol to ensure loose coupling
and clean integration between independent modules.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    runtime_checkable,
)

from core.models import (
    ClassGroup,
    ClassSubjectAssignment,
    ConstraintViolation,
    Department,
    Institution,
    OptimizationMetrics,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SolverProgress,
    StudentGroup,
    Subject,
    SubjectOffering,
    Teacher,
    TeacherWorkloadRule,
    Timetable,
)

T = TypeVar("T")
ProgressCallback = Callable[[SolverProgress], None]


# ---------------------------------------------------------------------------
# Generic and Concrete Repository Interfaces (Agent 2)
# ---------------------------------------------------------------------------


@runtime_checkable
class Repository(Protocol[T]):
    """Generic repository protocol for persistent entities."""

    def get_by_id(self, entity_id: str) -> Optional[T]:
        ...

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[T]:
        ...

    def save(self, entity: T) -> T:
        ...

    def delete(self, entity_id: str) -> bool:
        ...


@runtime_checkable
class TimetableRepository(Protocol):
    """Specialized repository for managing Timetable containers and their assigned sessions."""

    def get_by_id(self, timetable_id: str) -> Optional[Timetable]:
        ...

    def list_timetables(self, semester_id: Optional[str] = None) -> List[Timetable]:
        ...

    def get_sessions(self, timetable_id: str) -> List[ScheduledSession]:
        ...

    def save_timetable(self, timetable: Timetable, sessions: List[ScheduledSession]) -> None:
        ...

    def update_session(self, session: ScheduledSession) -> None:
        ...

    def delete_session(self, session_id: str) -> bool:
        ...

    def delete_timetable(self, timetable_id: str) -> bool:
        ...


# ---------------------------------------------------------------------------
# Academic Management Service (Agent 3)
# ---------------------------------------------------------------------------


@runtime_checkable
class AcademicService(Protocol):
    """Orchestrates institution, department, faculty, curriculum, and class definitions."""

    def create_department(self, institution_id: str, name: str, code: str) -> Department:
        ...

    def create_teacher(
        self,
        department_id: str,
        name: str,
        employee_id: str,
        email: Optional[str] = None,
        is_full_time: bool = True,
    ) -> Teacher:
        ...

    def create_subject(
        self,
        department_id: str,
        code: str,
        name: str,
        credits: float,
        is_elective: bool = False,
    ) -> Subject:
        ...

    def create_offering(
        self,
        subject_id: str,
        semester_id: str,
        weekly_contact_hours: float,
        weekly_periods: int,
    ) -> SubjectOffering:
        ...

    def create_class_group(
        self,
        department_id: str,
        semester_id: str,
        name: str,
        student_count: int,
        home_room_id: Optional[str] = None,
    ) -> ClassGroup:
        ...

    def create_room(
        self,
        name: str,
        code: str,
        room_type: RoomType,
        capacity: int,
        building: Optional[str] = None,
    ) -> Room:
        ...

    def assign_subject_to_class(
        self,
        class_group_id: str,
        offering_id: str,
        primary_teacher_id: str,
        secondary_teacher_id: Optional[str] = None,
        student_group_id: Optional[str] = None,
    ) -> ClassSubjectAssignment:
        ...


# ---------------------------------------------------------------------------
# Workload & Faculty Preference Services (Agent 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FacultyWorkloadSummary:
    teacher_id: str
    teacher_name: str
    assigned_periods_per_week: int
    assigned_contact_hours_per_week: float
    max_periods_allowed: int
    min_periods_required: int
    daily_periods: Dict[int, int]
    max_consecutive_observed: int
    is_overloaded: bool
    is_underloaded: bool


@runtime_checkable
class WorkloadService(Protocol):
    """Calculates workload metrics and manages availability and preferences."""

    def calculate_faculty_workload(
        self,
        teacher_id: str,
        sessions: List[ScheduledSession],
        institution: Institution,
    ) -> FacultyWorkloadSummary:
        ...

    def calculate_all_workloads(
        self,
        timetable_id: str,
    ) -> List[FacultyWorkloadSummary]:
        ...

    def set_availability(
        self,
        teacher_id: str,
        unavailable_slots: Set[Tuple[int, int]],
    ) -> None:
        ...

    def set_preferences(
        self,
        teacher_id: str,
        preferences: Dict[Tuple[int, int], int],
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# Solver Engine & Validator (Agent 5)
# ---------------------------------------------------------------------------


@runtime_checkable
class TimetableSolver(Protocol):
    """Independent mathematical scheduling engine using OR-Tools CP-SAT."""

    def solve(
        self,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_token: Optional[threading.Event] = None,
    ) -> SchedulingResult:
        ...


@runtime_checkable
class ScheduleValidator(Protocol):
    """Deterministic validator for detecting hard constraint collisions and soft penalties."""

    def validate(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
    ) -> List[ConstraintViolation]:
        ...

    def validate_move(
        self,
        session_id: str,
        target_day: int,
        target_period: int,
        target_room_id: str,
        current_sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle,
    ) -> List[ConstraintViolation]:
        ...


# ---------------------------------------------------------------------------
# Timetable Workspace & Edit Operations (Agent 6)
# ---------------------------------------------------------------------------


@runtime_checkable
class TimetableCoordinator(Protocol):
    """Mediates between the GUI, the solver, and persistent storage."""

    def create_draft_from_generation(self, result: SchedulingResult) -> Timetable:
        ...

    def move_session(
        self,
        timetable_id: str,
        session_id: str,
        day: int,
        start_period: int,
        room_id: str,
        force: bool = False,
    ) -> Tuple[bool, List[ConstraintViolation]]:
        ...

    def swap_sessions(
        self,
        timetable_id: str,
        session_a_id: str,
        session_b_id: str,
        force: bool = False,
    ) -> Tuple[bool, List[ConstraintViolation]]:
        ...

    def lock_session(self, timetable_id: str, session_id: str) -> None:
        ...

    def unlock_session(self, timetable_id: str, session_id: str) -> None:
        ...

    def partial_regenerate(
        self,
        timetable_id: str,
        regenerate_class_ids: Optional[List[str]] = None,
        config: Optional[SchedulingConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> SchedulingResult:
        ...


# ---------------------------------------------------------------------------
# Import, Export & Reporting (Agent 7)
# ---------------------------------------------------------------------------


@runtime_checkable
class ImportExportService(Protocol):
    """Handles tabular file import and publication formats."""

    def import_curriculum_from_csv(self, file_path: str) -> Dict[str, int]:
        ...

    def import_faculty_from_excel(self, file_path: str) -> Dict[str, int]:
        ...

    def export_timetable_to_pdf(
        self, timetable_id: str, output_path: str, layout: str = "CLASS_GRID"
    ) -> str:
        ...

    def export_timetable_to_excel(self, timetable_id: str, output_path: str) -> str:
        ...

    def export_timetable_to_csv(self, timetable_id: str, output_path: str) -> str:
        ...


@runtime_checkable
class ReportService(Protocol):
    """Compiles analytical reports for administration."""

    def generate_workload_report(self, timetable_id: str) -> str:
        ...

    def generate_room_utilization_report(self, timetable_id: str) -> str:
        ...


# ---------------------------------------------------------------------------
# GUI Progress & Event Bus (Agent 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UIProgressEvent:
    event_type: str
    task_name: str
    progress_percentage: float
    status_text: str
    payload: Any = None


@runtime_checkable
class EventBus(Protocol):
    """Thread-safe event publishing and subscription system."""

    def subscribe(self, event_type: str, handler: Callable[[UIProgressEvent], None]) -> None:
        ...

    def publish(self, event: UIProgressEvent) -> None:
        ...
