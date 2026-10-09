"""
Unit and integration tests for Academic Management UI screens (Agent 3).
Verifies component instantiation, data loading, and screen registration.
"""

import pytest
import customtkinter as ctk

from database.connection import DatabaseManager
from database.schema import initialize_database
from academic.academic_service import AcademicService
from academic.ui import (
    AcademicManagerView,
    create_academic_manager_view,
    DepartmentView,
    AcademicPeriodView,
    ClassView,
    TeacherView,
    SubjectView,
    AssignmentView,
    RoomView,
)
from academic.ui.components import DataTable, FormField, NotificationBanner
from ui.academic_structure import DepartmentView as AliasedDeptView
from ui.teachers import TeacherView as AliasedTeacherView
from ui.subjects import SubjectView as AliasedSubjectView
from ui.classrooms import RoomView as AliasedRoomView


@pytest.fixture(scope="module")
def root_window():
    """Provides a hidden root CTk window for headless widget testing."""
    root = ctk.CTk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def service():
    db_manager = DatabaseManager(":memory:")
    initialize_database(db_manager)
    return AcademicService(db_manager)


def test_ui_components(root_window):
    """Verify reusable UI components can be constructed and updated."""
    banner = NotificationBanner(root_window)
    banner.show_success("Test success message", timeout_ms=0)
    assert banner.label.cget("text") == "Test success message"

    field = FormField(root_window, "Test Field", default_value="Hello", required=True)
    assert field.get_value() == "Hello"
    field.set_value("World")
    assert field.get_value() == "World"

    table = DataTable(root_window, columns=[("id", "ID", 100), ("name", "Name", 200)])
    table.set_data([{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}])
    assert len(table.items) == 2


def test_individual_views_instantiation(root_window, service):
    """Verify each of the 7 academic management screens can be instantiated and load data."""
    dept_view = DepartmentView(root_window, institution_service=service.institution_service)
    assert dept_view is not None

    period_view = AcademicPeriodView(root_window, period_service=service.period_service)
    assert period_view is not None

    class_view = ClassView(
        root_window,
        class_service=service.class_service,
        institution_service=service.institution_service,
        period_service=service.period_service,
        room_service=service.room_service,
    )
    assert class_view is not None

    teacher_view = TeacherView(
        root_window,
        teacher_service=service.teacher_service,
        institution_service=service.institution_service,
        subject_service=service.subject_service,
    )
    assert teacher_view is not None

    subject_view = SubjectView(
        root_window,
        subject_service=service.subject_service,
        institution_service=service.institution_service,
    )
    assert subject_view is not None

    assign_view = AssignmentView(
        root_window,
        subject_service=service.subject_service,
        class_service=service.class_service,
        teacher_service=service.teacher_service,
        period_service=service.period_service,
    )
    assert assign_view is not None

    room_view = RoomView(root_window, room_service=service.room_service)
    assert room_view is not None


def test_academic_manager_container_view(root_window, service):
    """Verify master container view and Agent 8 factory method."""
    manager_view = create_academic_manager_view(root_window, service)
    assert isinstance(manager_view, AcademicManagerView)

    # Trigger full refresh
    manager_view.refresh_all()


def test_top_level_ui_aliases(root_window, service):
    """Verify top-level ui/ module aliases match underlying views."""
    v1 = AliasedDeptView(root_window, institution_service=service.institution_service)
    assert isinstance(v1, DepartmentView)

    v2 = AliasedTeacherView(
        root_window,
        teacher_service=service.teacher_service,
        institution_service=service.institution_service,
        subject_service=service.subject_service,
    )
    assert isinstance(v2, TeacherView)

    v3 = AliasedSubjectView(
        root_window,
        subject_service=service.subject_service,
        institution_service=service.institution_service,
    )
    assert isinstance(v3, SubjectView)

    v4 = AliasedRoomView(root_window, room_service=service.room_service)
    assert isinstance(v4, RoomView)
