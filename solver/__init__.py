"""Scheduling and optimization engine package for Timetable Thingy.

Powered by Google OR-Tools CP-SAT.
"""

from solver.cp_sat_solver import CpSatTimetableSolver
from solver.solver import TimetableSolverEngine, solve, generate_alternatives, partial_regenerate
from solver.session_builder import SessionBuilder, PreflightValidator, PreflightIssue
from solver.constraints import ConstraintModelBuilder, ModelVariables
from solver.optimizer import ObjectiveOptimizer
from solver.validator import DeterministicScheduleValidator
from solver.explanations import InfeasibilityExplainer, DiagnosticRecord, DiagnosticSeverity
from solver.results import ResultBuilder, AlternativeSolutionGenerator, PartialRegenerator

__all__ = [
    "CpSatTimetableSolver",
    "TimetableSolverEngine",
    "solve",
    "generate_alternatives",
    "partial_regenerate",
    "SessionBuilder",
    "PreflightValidator",
    "PreflightIssue",
    "ConstraintModelBuilder",
    "ModelVariables",
    "ObjectiveOptimizer",
    "DeterministicScheduleValidator",
    "InfeasibilityExplainer",
    "DiagnosticRecord",
    "DiagnosticSeverity",
    "ResultBuilder",
    "AlternativeSolutionGenerator",
    "PartialRegenerator",
]
