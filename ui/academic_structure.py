"""Academic Structure views forwarding to academic.ui."""

from academic.ui.department_view import DepartmentView
from academic.ui.period_view import AcademicPeriodView
from academic.ui.class_view import ClassView

__all__ = ["DepartmentView", "AcademicPeriodView", "ClassView"]
