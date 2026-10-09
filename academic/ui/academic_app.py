"""
Integrated Academic Management Workspace Application.
Provides coordinated tabbed navigation across all academic management screens.
Ready for Agent 8 shell integration or standalone execution.
"""

from typing import Optional
import customtkinter as ctk

from academic.academic_service import AcademicService
from academic.ui.assignment_view import AssignmentView
from academic.ui.class_view import ClassView
from academic.ui.department_view import DepartmentView
from academic.ui.period_view import AcademicPeriodView
from academic.ui.room_view import RoomView
from academic.ui.subject_view import SubjectView
from academic.ui.teacher_view import TeacherView
from academic.ui.theme import (
    COLOR_BG_PRIMARY,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    FONT_BODY_BOLD,
    FONT_SECTION,
)


class AcademicManagerView(ctk.CTkFrame):
    """
    Main Academic Management Panel.
    Coordinates all 7 academic screens with seamless tabbed navigation.
    """

    def __init__(self, master, service: AcademicService, **kwargs):
        super().__init__(master, fg_color=COLOR_BG_PRIMARY, **kwargs)
        self.service = service

        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_selected_color=COLOR_PRIMARY,
            segmented_button_selected_hover_color=COLOR_PRIMARY_HOVER,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        # Create tabs
        self.tab_depts = self.tabview.add("Institution & Departments")
        self.tab_periods = self.tabview.add("Academic Periods")
        self.tab_classes = self.tabview.add("Classes & Sections")
        self.tab_teachers = self.tabview.add("Teachers & Faculty")
        self.tab_subjects = self.tabview.add("Subject Catalog")
        self.tab_assignments = self.tabview.add("Curricular Offerings")
        self.tab_rooms = self.tabview.add("Rooms & Laboratories")

        # Instantiate sub-views
        self.dept_view = DepartmentView(
            self.tab_depts, institution_service=service.institution_service
        )
        self.dept_view.pack(fill="both", expand=True)

        self.period_view = AcademicPeriodView(
            self.tab_periods, period_service=service.period_service
        )
        self.period_view.pack(fill="both", expand=True)

        self.class_view = ClassView(
            self.tab_classes,
            class_service=service.class_service,
            institution_service=service.institution_service,
            period_service=service.period_service,
            room_service=service.room_service,
        )
        self.class_view.pack(fill="both", expand=True)

        self.teacher_view = TeacherView(
            self.tab_teachers,
            teacher_service=service.teacher_service,
            institution_service=service.institution_service,
            subject_service=service.subject_service,
        )
        self.teacher_view.pack(fill="both", expand=True)

        self.subject_view = SubjectView(
            self.tab_subjects,
            subject_service=service.subject_service,
            institution_service=service.institution_service,
        )
        self.subject_view.pack(fill="both", expand=True)

        self.assignment_view = AssignmentView(
            self.tab_assignments,
            subject_service=service.subject_service,
            class_service=service.class_service,
            teacher_service=service.teacher_service,
            period_service=service.period_service,
        )
        self.assignment_view.pack(fill="both", expand=True)

        self.room_view = RoomView(
            self.tab_rooms, room_service=service.room_service
        )
        self.room_view.pack(fill="both", expand=True)

    def refresh_all(self) -> None:
        """Reloads data across all sub-views."""
        self.dept_view.load_data()
        self.period_view.load_data()
        self.class_view.load_data()
        self.teacher_view.load_data()
        self.subject_view.load_data()
        self.assignment_view.load_data()
        self.room_view.load_data()


def create_academic_manager_view(parent, academic_service: AcademicService) -> AcademicManagerView:
    """Factory function for Agent 8 shell integration."""
    return AcademicManagerView(parent, service=academic_service)


if __name__ == "__main__":
    from database.connection import get_db_manager
    from database.schema import initialize_database

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Timetable Thingy - Academic Management Module")
    root.geometry("1100x750")

    mgr = get_db_manager("timetable_thingy.db")
    initialize_database(mgr)
    svc = AcademicService(mgr)

    app_view = create_academic_manager_view(root, svc)
    app_view.pack(fill="both", expand=True)

    root.mainloop()
