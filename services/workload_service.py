"""Workload service forwarder to workload package."""

from workload.service import WorkloadServiceImpl
from core.interfaces import WorkloadService, FacultyWorkloadSummary

__all__ = ["WorkloadServiceImpl", "WorkloadService", "FacultyWorkloadSummary"]
