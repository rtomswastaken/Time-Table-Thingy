"""Tests for CustomTkinter UI view models and headless compatibility."""

import pytest
from core.models import Institution, Teacher
from workload.service import WorkloadServiceImpl
from workload.ui.preferences_view import TeacherPreferencesView
from workload.ui.workload_config_view import WorkloadConfigView
from workload.ui.workload_overview_view import WorkloadOverviewView


@pytest.fixture
def institution():
    return Institution(
        name="UI Test Inst",
        code="UI",
        working_days=[0, 1, 2, 3, 4],
        periods_per_day=6,
    )


@pytest.fixture
def service(institution):
    t1 = Teacher(department_id="d1", name="Dr. Grace Hopper", employee_id="GH01", id="t1")
    t2 = Teacher(department_id="d1", name="Dr. Donald Knuth", employee_id="DK02", id="t2")
    return WorkloadServiceImpl(institution=institution, teachers=[t1, t2])


def test_ui_views_instantiate_headless(service, institution):
    """UI view classes can be instantiated in headless test environment (parent=None) without error."""
    teachers = list(service._teachers.values())

    # 1. Preferences View
    pref_view = TeacherPreferencesView(parent=None, service=service, teachers=teachers, institution=institution)
    assert pref_view.selected_teacher_id == "t1"
    assert len(pref_view.teachers) == 2

    # 2. Config View
    config_view = WorkloadConfigView(parent=None, service=service, teachers=teachers)
    assert config_view.selected_teacher_id == "t1"

    # 3. Overview View
    overview_view = WorkloadOverviewView(parent=None, service=service, teachers=teachers)
    assert overview_view.dept_filter is None
    assert overview_view.timetable_id == "current_draft"
