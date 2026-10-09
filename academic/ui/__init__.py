"""Academic Management UI Components and Screens."""

from academic.ui.academic_app import AcademicManagerView, create_academic_manager_view
from academic.ui.assignment_view import AssignmentView
from academic.ui.class_view import ClassView
from academic.ui.department_view import DepartmentView
from academic.ui.period_view import AcademicPeriodView
from academic.ui.room_view import RoomView
from academic.ui.subject_view import SubjectView
from academic.ui.teacher_view import TeacherView

__all__ = [
    "AcademicManagerView",
    "create_academic_manager_view",
    "DepartmentView",
    "AcademicPeriodView",
    "ClassView",
    "TeacherView",
    "SubjectView",
    "AssignmentView",
    "RoomView",
]
