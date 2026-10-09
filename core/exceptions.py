"""Domain exception hierarchy for Timetable Thingy."""

from typing import Optional, Any


class TimetableAppError(Exception):
    """Base exception for all application-specific errors."""

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(TimetableAppError):
    """Raised when an entity fails validation or constraints are violated."""
    pass


class RepositoryError(TimetableAppError):
    """Raised when an operation in the database repository fails."""
    pass


class EntityNotFoundError(RepositoryError):
    """Raised when a requested domain entity is not found in storage."""
    pass


class ConcurrencyError(RepositoryError):
    """Raised when a concurrent modification violates version integrity."""
    pass


class SchedulingError(TimetableAppError):
    """Base exception for scheduling engine errors."""
    pass


class InfeasibleScheduleError(SchedulingError):
    """Raised when the specified constraints have no mathematically possible solution."""
    pass


class SolverTimeoutError(SchedulingError):
    """Raised when the solver times out before finding a feasible solution."""
    pass


class InvalidConfigurationError(SchedulingError):
    """Raised when problem formulation or configuration contains contradictory or invalid inputs."""
    pass


class ImportExportError(TimetableAppError):
    """Raised when reading or writing external formats (CSV, Excel, PDF) fails."""
    pass
