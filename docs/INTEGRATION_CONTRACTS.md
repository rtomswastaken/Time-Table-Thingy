# Timetable Thingy - Integration Contracts & Interfaces

This document defines the Python interface contracts, expected inputs, outputs, error behaviors, and data bundles that **Agents 2 through 8** must implement or consume.

All interfaces use Python 3.11 `typing.Protocol` or abstract base classes with strict type annotations.

---

## 1. Domain Types & Enums (`core.models`)

The shared foundation provides these canonical types:

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Any

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
```

---

## 2. Solver & Scheduling Contracts (Agent 5 Contract)

### 2.1 Scheduling Configuration
```python
@dataclass(frozen=True)
class SchedulingConfig:
    """Configures the behavior and optimization weights of the CP-SAT solver."""
    time_limit_seconds: float = 60.0
    random_seed: int = 42
    allow_partial_solution: bool = False
    
    # Soft preference weights (1..100)
    weight_teacher_preference: int = 10
    weight_minimize_teacher_gaps: int = 15
    weight_minimize_student_gaps: int = 20
    weight_preferred_room: int = 5
    weight_balanced_daily_load: int = 10
```

### 2.2 Input Bundle
The solver is a pure function: `solve(bundle: SchedulingInputBundle, config: SchedulingConfig) -> SchedulingResult`. It receives everything it needs in a single immutable bundle:

```python
@dataclass(frozen=True)
class SchedulableUnit:
    """A single discrete session requirement that must be scheduled in the timetable."""
    unit_id: str                          # Unique identifier for this session instance
    assignment_id: str                    # FK to ClassSubjectAssignment
    class_group_id: str                   # Class cohort
    subject_id: str                       # Subject being taught
    teacher_id: str                       # Primary teacher
    secondary_teacher_id: Optional[str]   # Co-teacher (if any)
    session_type: SessionType             # THEORY, LABORATORY, etc.
    duration_periods: int                 # 1 for single period, 2 for double lab, etc.
    required_room_type: Optional[RoomType]# Specialized facility requirement
    student_group_id: Optional[str]       # Specific batch, if practical/tutorial
    locked_day: Optional[int] = None      # If locked, fixed day (0..N)
    locked_period: Optional[int] = None   # If locked, fixed start period
    locked_room_id: Optional[str] = None  # If locked, fixed room

@dataclass(frozen=True)
class SchedulingInputBundle:
    """Complete, self-contained problem snapshot passed to Agent 5's solver."""
    institution_id: str
    academic_year_id: str
    semester_id: str
    
    days: List[int]                       # e.g., [0, 1, 2, 3, 4] for Mon-Fri
    periods_per_day: int                  # e.g., 6 or 7
    break_periods: Set[int]               # e.g., {3} for lunch recess
    
    units: List[SchedulableUnit]
    teachers: List[Teacher]
    rooms: List[Room]
    class_groups: List[ClassGroup]
    
    teacher_availability: Dict[str, Set[tuple[int, int]]] # teacher_id -> {(day, period)} of unavailable slots
    room_availability: Dict[str, Set[tuple[int, int]]]    # room_id -> {(day, period)} of unavailable slots
    teacher_workload_rules: Dict[str, TeacherWorkloadRule]# teacher_id -> rule
    teacher_preferences: Dict[str, Dict[tuple[int, int], int]] # teacher_id -> (day, period) -> weight (-10..+10)
```

### 2.3 Progress Callback & Output Result
```python
@dataclass(frozen=True)
class SolverProgress:
    phase: str                            # e.g. "BUILDING_MODEL", "SEARCHING", "POST_PROCESSING"
    elapsed_seconds: float
    best_objective_bound: Optional[float] = None
    is_feasible: bool = False
    message: str = ""

ProgressCallback = Callable[[SolverProgress], None]

@dataclass(frozen=True)
class SchedulingResult:
    status: SchedulingStatus
    sessions: List[ScheduledSession] = field(default_factory=list)
    violations: List[ConstraintViolation] = field(default_factory=list)
    metrics: Optional[OptimizationMetrics] = None
    execution_time_seconds: float = 0.0
    message: str = ""

class TimetableSolver(Protocol):
    """Implemented by Agent 5 (solver/cp_sat_solver.py)."""
    def solve(
        self,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_token: Optional[threading.Event] = None
    ) -> SchedulingResult:
        ...
```

---

## 3. Schedule Validation Contract (Agents 5 & 6)

Every schedule—whether generated by CP-SAT or modified manually in CustomTkinter—must be verifiable using the deterministic validator:

```python
class ScheduleValidator(Protocol):
    """Implemented by Agent 5 (solver/validator.py). Used by Agent 6 for live validation."""
    def validate(
        self,
        sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle
    ) -> List[ConstraintViolation]:
        """Returns empty list if 100% valid. Returns all hard & soft violations otherwise."""
        ...
        
    def validate_move(
        self,
        session_id: str,
        target_day: int,
        target_period: int,
        target_room_id: str,
        current_sessions: List[ScheduledSession],
        bundle: SchedulingInputBundle
    ) -> List[ConstraintViolation]:
        """Real-time validation check before committing a drag-and-drop or swap in the GUI."""
        ...
```

---

## 4. Timetable Workspace & Edit Operations (Agent 6 Contract)

Agent 6 manages the timetable grid. It interacts with the timetable coordinator service using these operations:

```python
class TimetableCoordinator(Protocol):
    """Implemented by Agent 8/6 (academic/coordinator.py)."""
    def create_draft_from_generation(self, result: SchedulingResult) -> Timetable:
        ...
        
    def move_session(
        self,
        timetable_id: str,
        session_id: str,
        day: int,
        start_period: int,
        room_id: str
    ) -> tuple[bool, List[ConstraintViolation]]:
        """Moves session. If invalid, does not commit unless force=True."""
        ...
        
    def swap_sessions(
        self,
        timetable_id: str,
        session_a_id: str,
        session_b_id: str
    ) -> tuple[bool, List[ConstraintViolation]]:
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
        progress_callback: Optional[ProgressCallback] = None
    ) -> SchedulingResult:
        """Keeps all locked sessions and regenerates only unlocked / selected classes."""
        ...
```

---

## 5. Workload & Preference Contracts (Agent 4 Contract)

Agent 4 calculates workload metrics and manages faculty preferences:

```python
@dataclass(frozen=True)
class FacultyWorkloadSummary:
    teacher_id: str
    teacher_name: str
    assigned_periods_per_week: int
    assigned_contact_hours_per_week: float
    max_periods_allowed: int
    min_periods_required: int
    daily_periods: Dict[int, int]          # day -> period count
    max_consecutive_observed: int
    is_overloaded: bool
    is_underloaded: bool

class WorkloadService(Protocol):
    """Implemented by Agent 4 (workload/workload_service.py)."""
    def calculate_faculty_workload(
        self,
        teacher_id: str,
        sessions: List[ScheduledSession],
        institution: Institution
    ) -> FacultyWorkloadSummary:
        ...

    def calculate_all_workloads(
        self,
        timetable_id: str
    ) -> List[FacultyWorkloadSummary]:
        ...

    def set_availability(
        self,
        teacher_id: str,
        unavailable_slots: Set[tuple[int, int]]
    ) -> None:
        ...

    def set_preferences(
        self,
        teacher_id: str,
        preferences: Dict[tuple[int, int], int]
    ) -> None:
        ...
```

---

## 6. Academic Management Service Contract (Agent 3 Contract)

Agent 3 provides CRUD services for institution, departments, subjects, faculty, and classes:

```python
class AcademicService(Protocol):
    """Implemented by Agent 3 (academic/academic_service.py)."""
    def create_department(self, institution_id: str, name: str, code: str) -> Department: ...
    def create_teacher(self, department_id: str, name: str, employee_id: str, is_full_time: bool = True) -> Teacher: ...
    def create_subject(self, department_id: str, name: str, code: str, credits: float) -> Subject: ...
    def create_class_group(self, department_id: str, semester_id: str, name: str, student_count: int) -> ClassGroup: ...
    def create_room(self, name: str, code: str, room_type: RoomType, capacity: int) -> Room: ...
    
    def assign_subject_to_class(
        self,
        class_group_id: str,
        offering_id: str,
        teacher_id: str,
        student_group_id: Optional[str] = None
    ) -> ClassSubjectAssignment: ...
```

---

## 7. Database Repositories Contract (Agent 2 Contract)

Agent 2 provides atomic SQLite repository implementations conforming to:

```python
class Repository(Protocol[T]):
    def get_by_id(self, entity_id: str) -> Optional[T]: ...
    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[T]: ...
    def save(self, entity: T) -> T: ...
    def delete(self, entity_id: str) -> bool: ...

class TimetableRepository(Protocol):
    def get_by_id(self, timetable_id: str) -> Optional[Timetable]: ...
    def get_sessions(self, timetable_id: str) -> List[ScheduledSession]: ...
    def save_timetable(self, timetable: Timetable, sessions: List[ScheduledSession]) -> None: ...
    def update_session(self, session: ScheduledSession) -> None: ...
    def delete_timetable(self, timetable_id: str) -> bool: ...
```

---

## 8. Import, Export & Reporting Contract (Agent 7 Contract)

Agent 7 provides file exchange and report generation:

```python
class ImportExportService(Protocol):
    """Implemented by Agent 7 (exchange/service.py)."""
    def import_curriculum_from_csv(self, file_path: str) -> Dict[str, int]: ...
    def import_faculty_from_excel(self, file_path: str) -> Dict[str, int]: ...
    def export_timetable_to_pdf(self, timetable_id: str, output_path: str, layout: str = "CLASS_GRID") -> str: ...
    def export_timetable_to_excel(self, timetable_id: str, output_path: str) -> str: ...
    def export_timetable_to_csv(self, timetable_id: str, output_path: str) -> str: ...

class ReportService(Protocol):
    """Implemented by Agent 7 (exchange/reports.py)."""
    def generate_workload_report(self, timetable_id: str) -> str: ...
    def generate_room_utilization_report(self, timetable_id: str) -> str: ...
```

---

## 9. GUI Progress & Event Bus Contract (Agent 8 Contract)

Agent 8 provides the event notification hub for threading communication:

```python
@dataclass(frozen=True)
class UIProgressEvent:
    event_type: str                       # "TASK_STARTED", "PROGRESS_UPDATE", "TASK_FINISHED", "TASK_FAILED"
    task_name: str
    progress_percentage: float            # 0.0 to 100.0
    status_text: str
    payload: Any = None

class EventBus(Protocol):
    def subscribe(self, event_type: str, handler: Callable[[UIProgressEvent], None]) -> None: ...
    def publish(self, event: UIProgressEvent) -> None: ...
```
