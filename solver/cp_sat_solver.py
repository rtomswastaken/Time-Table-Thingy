"""OR-Tools CP-SAT Timetable Solver implementation for Timetable Thingy.

Implements the TimetableSolver protocol using Google OR-Tools CP-SAT.
Operates completely detached from the GUI, uses pure domain bundles,
supports thread-safe cancellation, and streams search progress.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from core.interfaces import ProgressCallback
from core.models import (
    ConstraintViolation,
    OptimizationMetrics,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SchedulingStatus,
    SolverProgress,
)
from solver.constraints import ConstraintModelBuilder, ModelVariables
from solver.explanations import InfeasibilityExplainer
from solver.optimizer import ObjectiveOptimizer
from solver.results import ResultBuilder
from solver.session_builder import PreflightValidator
from solver.validator import DeterministicScheduleValidator


class _SolverProgressSolutionCallback(cp_model.CpSolverSolutionCallback):
    """Bridge for streaming solution events to the application progress callback."""

    def __init__(
        self,
        progress_callback: Optional[ProgressCallback],
        cancel_token: Optional[threading.Event],
        start_time: float,
    ) -> None:
        super().__init__()
        self.progress_callback = progress_callback
        self.cancel_token = cancel_token
        self.start_time = start_time
        self.solution_count = 0

    def on_solution_callback(self) -> None:
        self.solution_count += 1
        elapsed = time.perf_counter() - self.start_time

        # Check for cancellation request
        if self.cancel_token and self.cancel_token.is_set():
            self.StopSearch()
            return

        if self.progress_callback:
            obj_val = self.ObjectiveValue()
            progress = SolverProgress(
                phase="SEARCHING",
                elapsed_seconds=round(elapsed, 2),
                best_objective_bound=round(obj_val, 2),
                is_feasible=True,
                message=f"Found feasible solution #{self.solution_count} (cost: {int(obj_val)})",
            )
            try:
                self.progress_callback(progress)
            except Exception:
                pass


class CpSatTimetableSolver:
    """Core CP-SAT solver implementing the TimetableSolver interface protocol."""

    def solve(
        self,
        bundle: SchedulingInputBundle,
        config: SchedulingConfig,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_token: Optional[threading.Event] = None,
        baseline_assignments: Optional[Dict[str, Tuple[int, int, str]]] = None,
    ) -> SchedulingResult:
        """Solves the timetable model deterministically within the configured time limit."""
        start_time = time.perf_counter()

        def _notify(phase: str, msg: str, is_feas: bool = False, bound: Optional[float] = None) -> None:
            if progress_callback:
                elapsed = time.perf_counter() - start_time
                try:
                    progress_callback(
                        SolverProgress(
                            phase=phase,
                            elapsed_seconds=round(elapsed, 2),
                            best_objective_bound=bound,
                            is_feasible=is_feas,
                            message=msg,
                        )
                    )
                except Exception:
                    pass

        # 1. Preflight Validation
        _notify("VALIDATING", "Running pre-flight consistency checks...")
        if cancel_token and cancel_token.is_set():
            return ResultBuilder.build_result(
                status=SchedulingStatus.ERROR,
                sessions=[],
                bundle=bundle,
                config=config,
                runtime_seconds=time.perf_counter() - start_time,
                message="Operation cancelled by user before solving.",
            )

        preflight_issues = PreflightValidator.validate_bundle(bundle)
        fatal_issues = [issue for issue in preflight_issues if issue.is_fatal]
        if fatal_issues:
            violations = [issue.to_constraint_violation() for issue in fatal_issues]
            return ResultBuilder.build_result(
                status=SchedulingStatus.INFEASIBLE,
                sessions=[],
                bundle=bundle,
                config=config,
                violations=violations,
                runtime_seconds=time.perf_counter() - start_time,
                message=f"Preflight validation identified {len(fatal_issues)} fatal constraint conflict(s).",
            )

        # 2. Build Mathematical Formulation
        _notify("BUILDING_MODEL", "Building CP-SAT decision variables and constraints...")
        if cancel_token and cancel_token.is_set():
            return ResultBuilder.build_result(
                status=SchedulingStatus.ERROR,
                sessions=[],
                bundle=bundle,
                config=config,
                runtime_seconds=time.perf_counter() - start_time,
                message="Operation cancelled by user during model compilation.",
            )

        builder = ConstraintModelBuilder(bundle, config)
        model, variables = builder.build()

        # 3. Apply Multi-Objective Penalties
        ObjectiveOptimizer.apply_objective(model, bundle, config, variables, baseline_assignments)

        # 4. Configure CP-SAT Engine
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.1, config.time_limit_seconds)
        solver.parameters.random_seed = config.random_seed
        solver.parameters.num_workers = 1  # Deterministic execution
        solver.parameters.log_search_progress = False

        callback = _SolverProgressSolutionCallback(progress_callback, cancel_token, start_time)

        # 5. Execute Optimization Search
        _notify("SEARCHING", f"Starting CP-SAT search with time limit {config.time_limit_seconds}s...")
        status_code = solver.Solve(model, callback)
        total_time = time.perf_counter() - start_time

        # Check if cancelled mid-search
        if cancel_token and cancel_token.is_set():
            # If search was cancelled but a feasible solution was already discovered:
            if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
                return ResultBuilder.build_result(
                    status=SchedulingStatus.FEASIBLE,
                    sessions=sessions,
                    bundle=bundle,
                    config=config,
                    runtime_seconds=total_time,
                    message="Search stopped by user; returning best feasible solution found before cancellation.",
                )
            return ResultBuilder.build_result(
                status=SchedulingStatus.ERROR,
                sessions=[],
                bundle=bundle,
                config=config,
                runtime_seconds=total_time,
                message="Search cancelled by user before any feasible solution was found.",
            )

        # 6. Map Outcomes
        if status_code == cp_model.OPTIMAL:
            _notify("OPTIMAL", "Optimal solution discovered and proven!", is_feas=True)
            sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
            return ResultBuilder.build_result(
                status=SchedulingStatus.OPTIMAL,
                sessions=sessions,
                bundle=bundle,
                config=config,
                runtime_seconds=total_time,
                message="Optimal schedule generated successfully.",
            )

        elif status_code == cp_model.FEASIBLE:
            _notify("FEASIBLE", "Feasible solution found within time limit.", is_feas=True)
            sessions = ResultBuilder.extract_sessions(solver, bundle, variables)
            return ResultBuilder.build_result(
                status=SchedulingStatus.FEASIBLE,
                sessions=sessions,
                bundle=bundle,
                config=config,
                runtime_seconds=total_time,
                message="Feasible schedule generated (time limit reached before optimality proof).",
            )

        elif status_code == cp_model.INFEASIBLE:
            _notify("INFEASIBLE", "Problem proven mathematically infeasible. Running root-cause diagnostics...")
            diagnostic_records = InfeasibilityExplainer.diagnose(bundle, config)
            violations = [d.to_constraint_violation() for d in diagnostic_records]
            remediation_summary = "; ".join(d.explanation for d in diagnostic_records[:3])
            return ResultBuilder.build_result(
                status=SchedulingStatus.INFEASIBLE,
                sessions=[],
                bundle=bundle,
                config=config,
                violations=violations,
                runtime_seconds=total_time,
                message=f"Timetable is infeasible. Root causes: {remediation_summary}",
            )

        else:
            # cp_model.UNKNOWN -> search limit reached without any solution
            _notify("TIMEOUT", f"Time limit of {config.time_limit_seconds}s reached without solution.")
            return ResultBuilder.build_result(
                status=SchedulingStatus.TIMEOUT,
                sessions=[],
                bundle=bundle,
                config=config,
                runtime_seconds=total_time,
                message=f"Solver reached time limit ({config.time_limit_seconds}s) without finding a feasible solution.",
            )
