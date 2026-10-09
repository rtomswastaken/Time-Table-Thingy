"""
Validation, solver reporting, and audit log domain models.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SchedulingRun:
    """Execution summary and metrics for an optimization solver run."""
    id: Optional[int] = None
    timetable_id: int = 0
    solver_status: str = "OPTIMAL"  # OPTIMAL, FEASIBLE, INFEASIBLE, TIMEOUT, FAILED
    execution_time_seconds: float = 0.0
    objective_value: float = 0.0
    total_sessions_scheduled: int = 0
    total_sessions_unscheduled: int = 0
    run_timestamp: Optional[str] = None
    configuration_snapshot_json: Optional[str] = None


@dataclass
class ConflictRecord:
    """An identified timetable constraint violation or conflict."""
    id: Optional[int] = None
    timetable_id: int = 0
    run_id: Optional[int] = None
    conflict_type: str = "teacher_overlap"
    severity: str = "error"  # warning, error
    description: str = ""
    session_id_1: Optional[int] = None
    session_id_2: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class UnscheduledSession:
    """Explanation for a subject offering session that could not be placed."""
    id: Optional[int] = None
    timetable_id: int = 0
    run_id: Optional[int] = None
    offering_id: int = 0
    reason: str = ""
    created_at: Optional[str] = None


@dataclass
class TimetableChangeLog:
    """Audit log entry tracking modifications to a timetable."""
    id: Optional[int] = None
    timetable_id: int = 0
    action: str = "create"  # create, update, delete, lock, unlock, publish, clone
    entity_type: str = "session"
    entity_id: Optional[int] = None
    details_json: Optional[str] = None
    changed_at: Optional[str] = None


from core.models import ConstraintViolation, OptimizationMetrics


@dataclass
class ScheduleValidationResult:
    """Aggregated validation output for a timetable."""
    is_valid: bool = True
    violations: list = field(default_factory=list)
    hard_violations: list = field(default_factory=list)
    soft_violations: list = field(default_factory=list)

