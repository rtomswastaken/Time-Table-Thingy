"""
Academic business rule validation for Timetable Thingy.

Enforces institutional constraints, identifier formatting, non-negative quantities,
date ranges, foreign key integrity, and curricular consistency.
"""

from datetime import datetime
from typing import Any, List, Optional
from core.exceptions import ValidationError


def validate_identifier(value: str, field_name: str) -> str:
    """Validates that an identifier or code is non-empty and well-formed."""
    if not value or not str(value).strip():
        raise ValidationError(f"{field_name} cannot be empty.")
    cleaned = str(value).strip()
    if len(cleaned) < 1:
        raise ValidationError(f"{field_name} must contain at least 1 character.")
    return cleaned


def validate_non_negative_int(value: int, field_name: str, min_val: int = 0) -> int:
    """Validates that a numeric integer value is at least min_val."""
    try:
        val = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid integer, got {value}.")
    if val < min_val:
        raise ValidationError(f"{field_name} must be at least {min_val}, got {val}.")
    return val


def validate_non_negative_float(value: float, field_name: str, min_val: float = 0.0) -> float:
    """Validates that a floating point value is at least min_val."""
    try:
        val = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid number, got {value}.")
    if val < min_val:
        raise ValidationError(f"{field_name} must be at least {min_val}, got {val}.")
    return val


def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> None:
    """
    Validates that if start and end dates are provided, they follow YYYY-MM-DD
    format and start_date <= end_date.
    """
    if not start_date or not end_date:
        return

    try:
        s_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"Invalid start date format '{start_date}'. Expected YYYY-MM-DD.")

    try:
        e_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"Invalid end date format '{end_date}'. Expected YYYY-MM-DD.")

    if s_dt > e_dt:
        raise ValidationError(
            f"Start date ({start_date}) cannot be after end date ({end_date})."
        )


def validate_session_requirements_consistency(
    weekly_periods: int, session_requirements: List[Any]
) -> None:
    """
    Validates that declared session requirements sum up to the required weekly periods.
    """
    if not session_requirements:
        return

    total_periods = 0
    for req in session_requirements:
        consec = getattr(req, "consecutive_periods", None) or req.get("consecutive_periods", 1)
        freq = getattr(req, "frequency_per_week", None) or req.get("frequency_per_week", 1)
        if consec < 1:
            raise ValidationError(f"Consecutive periods must be >= 1, got {consec}.")
        if freq < 1:
            raise ValidationError(f"Frequency per week must be >= 1, got {freq}.")
        total_periods += consec * freq

    if total_periods != weekly_periods:
        raise ValidationError(
            f"Session requirements total {total_periods} periods, which conflicts with "
            f"declared weekly_periods ({weekly_periods})."
        )
