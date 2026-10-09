"""
Comprehensive unit and integration tests for Academic Management Services (Agent 3).
Tests business rules, validations, error conditions, and database persistence using in-memory SQLite.
"""

import pytest
from core.exceptions import EntityNotFoundError, ValidationError
from core.models import RoomType, SessionType
from database.connection import DatabaseManager
from database.schema import initialize_database
from academic.academic_service import AcademicService


@pytest.fixture
def academic_service():
    """Initializes an AcademicService instance with an in-memory SQLite database."""
    db_manager = DatabaseManager(":memory:")
    initialize_database(db_manager)
    return AcademicService(db_manager)


# =============================================================================
# Institution and Department Tests
# =============================================================================


def test_institution_creation_and_update(academic_service):
    service = academic_service.institution_service
    inst = service.get_or_create_default_institution(name="Central University", code="CU")
    assert inst.name == "Central University"
    assert inst.code == "CU"
    assert inst.periods_per_day == 6

    # Update institution
    updated = service.update_institution(
        institution_id=str(inst.id),
        name="Central University of Technology",
        code="CUT",
        working_days=[0, 1, 2, 3, 4, 5],
        periods_per_day=7,
        period_duration_minutes=50,
    )
    assert updated.name == "Central University of Technology"
    assert updated.periods_per_day == 7
    assert len(updated.working_days) == 6


def test_department_crud_and_duplicate_code(academic_service):
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept_service = academic_service.institution_service

    # Create department
    dept = dept_service.create_department(str(inst.id), "Computer Science", "CSE")
    assert dept.name == "Computer Science"
    assert dept.code == "CSE"

    # Duplicate code rejection
    with pytest.raises(ValidationError, match="already exists"):
        dept_service.create_department(str(inst.id), "Comp Sci 2", "CSE")

    # Update department
    updated = dept_service.update_department(str(dept.id), "Computer Science & Eng", "CS")
    assert updated.code == "CS"
    assert updated.name == "Computer Science & Eng"

    # List departments
    all_depts = dept_service.list_departments(str(inst.id))
    assert len(all_depts) == 1
    assert all_depts[0].code == "CS"

    # Delete department
    assert dept_service.delete_department(str(dept.id)) is True
    assert dept_service.get_department(str(dept.id)) is None


def test_department_invalid_institution_reference(academic_service):
    with pytest.raises(EntityNotFoundError, match="Institution with id 'non-existent' not found"):
        academic_service.institution_service.create_department("non-existent", "Physics", "PHY")


# =============================================================================
# Academic Period (Year & Semester) Tests
# =============================================================================


def test_academic_year_and_semester_lifecycle(academic_service):
    period_service = academic_service.period_service

    # Create Academic Year with valid date range
    ay = period_service.create_academic_year("2026-2027", "2026-08-01", "2027-05-31", is_current=True)
    assert ay.name == "2026-2027"
    assert ay.is_current is True

    # Invalid date range: start_date > end_date
    with pytest.raises(ValidationError, match="cannot be after end date"):
        period_service.create_academic_year("2026-2027-Invalid", "2027-05-31", "2026-08-01")

    # Create Semester
    sem = period_service.create_semester(str(ay.id), number=1, term_name="Fall 2026")
    assert sem.number == 1
    assert sem.term_name == "Fall 2026"

    # Duplicate semester number within year rejected
    with pytest.raises(ValidationError, match="already exists"):
        period_service.create_semester(str(ay.id), number=1, term_name="Duplicate Sem 1")

    # List semesters
    sems = period_service.list_semesters(str(ay.id))
    assert len(sems) == 1
    assert sems[0].number == 1


# =============================================================================
# Class and Section Tests
# =============================================================================


def test_class_group_and_student_group_management(academic_service):
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept = academic_service.institution_service.create_department(str(inst.id), "AI & Data Science", "AIDS")
    ay = academic_service.period_service.create_academic_year("2026-2027", "2026-08-01", "2027-05-31")
    sem = academic_service.period_service.create_semester(str(ay.id), number=3, term_name="S3")

    class_service = academic_service.class_service

    # Create section S3AD-A
    cls_a = class_service.create_class_group(
        department_id=str(dept.id),
        semester_id=str(sem.id),
        name="S3AD-A",
        student_count=60,
    )
    assert cls_a.name == "S3AD-A"
    assert cls_a.student_count == 60

    # Create section S3AD-B
    cls_b = class_service.create_class_group(
        department_id=str(dept.id),
        semester_id=str(sem.id),
        name="S3AD-B",
        student_count=58,
    )
    assert cls_b.name == "S3AD-B"

    # Reject duplicate section name in same dept & semester
    with pytest.raises(ValidationError, match="already exists"):
        class_service.create_class_group(
            department_id=str(dept.id),
            semester_id=str(sem.id),
            name="S3AD-A",
            student_count=50,
        )

    # Subgroup / lab batch creation
    batch1 = class_service.create_student_group(str(cls_a.id), "Batch A1", student_count=30)
    batch2 = class_service.create_student_group(str(cls_a.id), "Batch A2", student_count=30)
    groups = class_service.list_student_groups(str(cls_a.id))
    assert len(groups) == 2
    assert {g.name for g in groups} == {"Batch A1", "Batch A2"}


# =============================================================================
# Teacher Management & Qualifications Tests
# =============================================================================


def test_teacher_profiles_and_qualifications(academic_service):
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept = academic_service.institution_service.create_department(str(inst.id), "Mechanical", "ME")
    teacher_service = academic_service.teacher_service
    subject_service = academic_service.subject_service

    # Create teachers
    t1 = teacher_service.create_teacher(str(dept.id), "Dr. Alan Turing", "EMP101", "alan@univ.edu", is_full_time=True)
    t2 = teacher_service.create_teacher(str(dept.id), "Grace Hopper", "EMP102", "grace@univ.edu", is_full_time=True)

    assert t1.name == "Dr. Alan Turing"
    assert t2.employee_id == "EMP102"

    # Duplicate employee_id rejected
    with pytest.raises(ValidationError, match="already exists"):
        teacher_service.create_teacher(str(dept.id), "Duplicate Emp", "EMP101")

    # Search and filter
    found = teacher_service.list_teachers(department_id=str(dept.id), search="Grace")
    assert len(found) == 1
    assert found[0].name == "Grace Hopper"

    # Create subjects
    s1 = subject_service.create_subject(str(dept.id), "ME201", "Thermodynamics", credits=4.0)
    s2 = subject_service.create_subject(str(dept.id), "ME202", "Fluid Mechanics", credits=3.0)

    # Add qualifications (can teach)
    q1 = teacher_service.add_qualification(str(t1.id), str(s1.id), competency_level=1, preference_score=5)
    q2 = teacher_service.add_qualification(str(t1.id), str(s2.id), competency_level=2, preference_score=4)
    q3 = teacher_service.add_qualification(str(t2.id), str(s1.id), competency_level=1, preference_score=5)

    assert q1.competency_level == 1

    # Check qualified teachers for subject s1
    qualified_for_s1 = teacher_service.get_teachers_qualified_for_subject(str(s1.id))
    assert len(qualified_for_s1) == 2

    # Check qualifications for teacher t1
    t1_quals = teacher_service.get_qualifications_for_teacher(str(t1.id))
    assert len(t1_quals) == 2

    # Remove qualification
    assert teacher_service.remove_qualification(str(t1.id), str(s2.id)) is True
    assert len(teacher_service.get_qualifications_for_teacher(str(t1.id))) == 1


# =============================================================================
# Subject Management, Offerings, and Session Requirements Tests
# =============================================================================


def test_subject_distinct_credits_and_contact_hours(academic_service):
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept = academic_service.institution_service.create_department(str(inst.id), "Electronics", "ECE")
    ay = academic_service.period_service.create_academic_year("2026-2027", "2026-08-01", "2027-05-31")
    sem = academic_service.period_service.create_semester(str(ay.id), number=4, term_name="S4")

    subject_service = academic_service.subject_service

    # Create subject: 4 credits, distinct from contact hours
    subject = subject_service.create_subject(str(dept.id), "EC401", "Signals and Systems", credits=4.0)
    assert subject.credits == 4.0

    # Negative credits rejected
    with pytest.raises(ValidationError, match="credits must be at least 0.0"):
        subject_service.create_subject(str(dept.id), "EC402", "Invalid Subject", credits=-1.0)

    # Create Subject Offering with 5 weekly contact hours across 5 periods
    offering = subject_service.create_offering(
        subject_id=str(subject.id),
        semester_id=str(sem.id),
        weekly_contact_hours=5.0,
        weekly_periods=5,
    )
    assert offering.weekly_contact_hours == 5.0
    assert offering.weekly_periods == 5

    # Configure session breakdown: 3 single theory lectures + 1 double lab session = 5 periods
    req1 = subject_service.add_session_requirement(
        offering_id=str(offering.id),
        session_type=SessionType.THEORY,
        consecutive_periods=1,
        frequency_per_week=3,
    )
    assert req1.total_periods == 3

    req2 = subject_service.add_session_requirement(
        offering_id=str(offering.id),
        session_type=SessionType.LABORATORY,
        consecutive_periods=2,
        frequency_per_week=1,
        requires_lab=True,
        preferred_room_type=RoomType.HARDWARE_LAB,
    )
    assert req2.total_periods == 2

    # Attempting to add more sessions that exceed weekly_periods must fail
    with pytest.raises(ValidationError, match="exceeds offering's weekly_periods"):
        subject_service.add_session_requirement(
            offering_id=str(offering.id),
            session_type=SessionType.THEORY,
            consecutive_periods=1,
            frequency_per_week=1,
        )


def test_class_subject_assignment(academic_service):
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept = academic_service.institution_service.create_department(str(inst.id), "Civil", "CE")
    ay = academic_service.period_service.create_academic_year("2026-2027", "2026-08-01", "2027-05-31")
    sem = academic_service.period_service.create_semester(str(ay.id), number=5, term_name="S5")
    cls = academic_service.class_service.create_class_group(str(dept.id), str(sem.id), "S5CE-A", 55)
    t1 = academic_service.teacher_service.create_teacher(str(dept.id), "Dr. Build", "EMP201")
    t2 = academic_service.teacher_service.create_teacher(str(dept.id), "Eng. Steel", "EMP202")
    subject = academic_service.subject_service.create_subject(str(dept.id), "CE501", "Structural Analysis", 3.0)
    offering = academic_service.subject_service.create_offering(str(subject.id), str(sem.id), 4.0, 4)

    # Assign offering to class group with primary & secondary teacher
    assignment = academic_service.subject_service.assign_subject_to_class(
        class_group_id=str(cls.id),
        offering_id=str(offering.id),
        primary_teacher_id=str(t1.id),
        secondary_teacher_id=str(t2.id),
    )
    assert assignment.class_group_id == str(cls.id)
    assert assignment.primary_teacher_id == str(t1.id)
    assert assignment.secondary_teacher_id == str(t2.id)

    # List assignments for class
    assignments = academic_service.subject_service.list_class_assignments(class_group_id=str(cls.id))
    assert len(assignments) == 1
    assert assignments[0].id == assignment.id


# =============================================================================
# Classroom, Lab, and Equipment Tests
# =============================================================================


def test_room_and_laboratory_management(academic_service):
    room_service = academic_service.room_service

    # Create classroom
    r1 = room_service.create_room(
        name="Lecture Hall 101",
        code="LH-101",
        room_type=RoomType.LECTURE_HALL,
        capacity=80,
        building="Academic Block A",
        floor=1,
    )
    assert r1.name == "Lecture Hall 101"
    assert r1.capacity == 80

    # Create computer lab
    lab1 = room_service.create_room(
        name="Advanced AI Computing Lab",
        code="LAB-AI",
        room_type=RoomType.COMPUTER_LAB,
        capacity=35,
        building="Computing Center",
        floor=2,
    )
    assert lab1.room_type == RoomType.COMPUTER_LAB

    # Duplicate room code rejected
    with pytest.raises(ValidationError, match="already exists"):
        room_service.create_room("Duplicate Hall", "LH-101", RoomType.LECTURE_HALL, 50)

    # Capacity must be at least 1
    with pytest.raises(ValidationError, match="Room capacity must be at least 1"):
        room_service.create_room("Invalid Room", "INV-1", RoomType.SEMINAR_ROOM, capacity=0)

    # List and filter rooms
    labs = room_service.list_rooms(room_type=RoomType.COMPUTER_LAB)
    assert len(labs) == 1
    assert labs[0].code == "LAB-AI"

    # Room availability
    avail = room_service.set_room_availability(str(r1.id), day_of_week=0, period_index=1, is_available=False)
    assert avail.is_available is False
    assert room_service.is_room_available(str(r1.id), day_of_week=0, period_index=1) is False
    assert room_service.is_room_available(str(r1.id), day_of_week=0, period_index=2) is True


# =============================================================================
# Unified AcademicService Protocol Facade Tests
# =============================================================================


def test_academic_service_facade_protocol(academic_service):
    """Verify that AcademicService satisfies core.interfaces.AcademicService protocol."""
    inst = academic_service.institution_service.get_or_create_default_institution()
    dept = academic_service.create_department(str(inst.id), "Biotech", "BT")
    teacher = academic_service.create_teacher(str(dept.id), "Dr. Watson", "EMP301")
    subject = academic_service.create_subject(str(dept.id), "BT101", "Biochemistry", credits=3.0)
    ay = academic_service.period_service.create_academic_year("2026-2027", "2026-08-01", "2027-05-31")
    sem = academic_service.period_service.create_semester(str(ay.id), 1, "S1")
    offering = academic_service.create_offering(str(subject.id), str(sem.id), 3.0, 3)
    room = academic_service.create_room("Bio Lab", "LAB-BIO", RoomType.WORKSHOP, 40)
    cls = academic_service.create_class_group(str(dept.id), str(sem.id), "S1BT-A", 40, home_room_id=str(room.id))

    assignment = academic_service.assign_subject_to_class(
        class_group_id=str(cls.id),
        offering_id=str(offering.id),
        primary_teacher_id=str(teacher.id),
    )
    assert assignment is not None
    assert assignment.class_group_id == str(cls.id)
    assert assignment.primary_teacher_id == str(teacher.id)
