"""Teacher Preferences and Workload Engine.

Agent 4 module providing faculty availability management, workload calculations,
workload rules, soft scheduling preferences, solver integration, and analytics.
"""

from workload.models import (
    DetailedTeacherPreference,
    FairnessMetrics,
    PreferenceEvaluationItem,
    PreferenceEvaluationReport,
    SoftPreferenceType,
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
    WorkloadViolation,
    WorkloadViolationType,
)
from workload.rules import WorkloadRuleManager
from workload.availability import AvailabilityManager
from workload.preferences import PreferenceManager
from workload.calculator import WorkloadCalculator
from workload.analytics import WorkloadAnalytics
from workload.solver_adapter import SolverWorkloadAdapter
from workload.repository import WorkloadRepository, InMemoryWorkloadRepository
from workload.service import WorkloadServiceImpl
from workload.validation import WorkloadValidator

__all__ = [
    "AvailabilityManager",
    "DetailedTeacherPreference",
    "FairnessMetrics",
    "InMemoryWorkloadRepository",
    "PreferenceEvaluationItem",
    "PreferenceEvaluationReport",
    "PreferenceManager",
    "SoftPreferenceType",
    "SolverWorkloadAdapter",
    "TeacherWorkloadRuleExtended",
    "WorkloadAnalytics",
    "WorkloadCalculator",
    "WorkloadProfile",
    "WorkloadRepository",
    "WorkloadRuleManager",
    "WorkloadServiceImpl",
    "WorkloadValidator",
    "WorkloadViolation",
    "WorkloadViolationType",
]
