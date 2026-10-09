"""Core solver entry points for Timetable Thingy.

Provides the TimetableSolverEngine class and high-level helper functions.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Set, Tuple

from core.interfaces import ProgressCallback
from core.models import (
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
)
from solver.cp_sat_solver import CpSatTimetableSolver
from solver.results import AlternativeSolutionGenerator, PartialRegenerator
from solver.validator import DeterministicScheduleValidator

# Direct alias for the engine
TimetableSolverEngine = CpSatTimetableSolver


def solve(
    bundle: SchedulingInputBundle,
    config: Optional[SchedulingConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_token: Optional[threading.Event] = None,
) -> SchedulingResult:
    """Convenience functional interface to solve a scheduling problem."""
    engine = CpSatTimetableSolver()
    cfg = config or SchedulingConfig()
    return engine.solve(bundle, cfg, progress_callback, cancel_token)


def generate_alternatives(
    bundle: SchedulingInputBundle,
    config: Optional[SchedulingConfig] = None,
    count: int = 3,
) -> List[SchedulingResult]:
    """Generates distinct alternative valid timetables."""
    cfg = config or SchedulingConfig()
    return AlternativeSolutionGenerator.generate_alternatives(bundle, cfg, count)


def partial_regenerate(
    bundle: SchedulingInputBundle,
    existing_sessions: List[ScheduledSession],
    regenerate_class_ids: Optional[Set[str]] = None,
    regenerate_teacher_ids: Optional[Set[str]] = None,
    regenerate_days: Optional[Set[int]] = None,
    config: Optional[SchedulingConfig] = None,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_token: Optional[threading.Event] = None,
) -> SchedulingResult:
    """Regenerates a subset of the timetable while preserving unaffected sessions."""
    cfg = config or SchedulingConfig()
    partial_bundle, baseline_assignments = PartialRegenerator.prepare_partial_bundle(
        bundle=bundle,
        existing_sessions=existing_sessions,
        regenerate_class_ids=regenerate_class_ids,
        regenerate_teacher_ids=regenerate_teacher_ids,
        regenerate_days=regenerate_days,
    )
    engine = CpSatTimetableSolver()
    return engine.solve(
        bundle=partial_bundle,
        config=cfg,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
        baseline_assignments=baseline_assignments,
    )
