"""Faculty workload report generator adapter."""

from exchange.reports.workload_report import WorkloadReportGenerator
from exchange.models import WorkloadReportRow

__all__ = ["WorkloadReportGenerator", "WorkloadReportRow"]
