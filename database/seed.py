"""
Development-only seed data generator.

WARNING: This module is intended solely for local development and integration testing.
It must never be executed automatically against production databases.
"""

import logging
import uuid
from typing import Any, Dict

from core.models import (
    AcademicYear,
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomType,
    Semester,
    SessionType,
    StudentGroup,
    Subject,
    SubjectOffering,
    SubjectSessionRequirement,
    Teacher,
    TeacherAvailability,
    TeacherPreference,
    TeacherQualification,
    TeacherWorkloadRule,
    Timetable,
)
from .connection import DatabaseManager
from .repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    PreferenceRepository,
    RoomRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from .schema import initialize_database

logger = logging.getLogger(__name__)


def seed_development_data(db_manager: DatabaseManager) -> Dict[str, Any]:
    """
    Populates an empty or development database with realistic academic data.
    Demonstrates institutions, departments, classes, teachers, subjects, rooms,
    qualifications, availabilities, preferences, and a draft timetable.
    """
    initialize_database(db_manager)

    inst_repo = InstitutionRepository(db_manager)
    dept_repo = DepartmentRepository(db_manager)
    teacher_repo = TeacherRepository(db_manager)
    subject_repo = SubjectRepository(db_manager)
    class_repo = ClassGroupRepository(db_manager)
    room_repo = RoomRepository(db_manager)
    tt_repo = TimetableRepository(db_manager)
    pref_repo = PreferenceRepository(db_manager)

    # 1. Institution
    institution = inst_repo.get_by_code("SIT")
    if not institution:
        institution = inst_repo.save(
            Institution(
                id="inst-sit",
                code="SIT",
                name="State Institute of Technology",
                working_days=[0, 1, 2, 3, 4],  # Mon-Fri
                periods_per_day=6,
                period_duration_minutes=60,
            )
        )

    # 2. Academic Year & Semesters
    years = inst_repo.list_academic_years()
    if not years:
        acad_year = inst_repo.save_academic_year(
            AcademicYear(
                id="ay-2026-2027",
                name="2026-2027",
                start_date="2026-08-01",
                end_date="2027-05-31",
                is_current=True,
            )
        )
    else:
        acad_year = years[0]

    semesters = inst_repo.list_semesters(str(acad_year.id))
    if not semesters:
        sem3 = inst_repo.save_semester(
            Semester(
                id="sem-3",
                academic_year_id=acad_year.id,
                number=3,
                term_name="Odd Semester (Fall 2026)",
            )
        )
        sem5 = inst_repo.save_semester(
            Semester(
                id="sem-5",
                academic_year_id=acad_year.id,
                number=5,
                term_name="Odd Semester (Fall 2026)",
            )
        )
    else:
        sem3 = semesters[0]
        sem5 = semesters[1] if len(semesters) > 1 else sem3

    # 3. Department
    dept = dept_repo.get_by_code(str(institution.id), "CSE")
    if not dept:
        dept = dept_repo.save(
            Department(
                id="dept-cse",
                institution_id=institution.id,
                code="CSE",
                name="Computer Science & Engineering",
            )
        )

    # 4. Classes (aligned with prototype data: S3AD, S5AD, S7AD)
    existing_classes = class_repo.list_by_department(str(dept.id))
    if not existing_classes:
        class_s3 = class_repo.save(
            ClassGroup(
                id="class-s3ad",
                department_id=dept.id,
                semester_id=sem3.id,
                name="S3AD",
                student_count=45,
            )
        )
        class_s5 = class_repo.save(
            ClassGroup(
                id="class-s5ad",
                department_id=dept.id,
                semester_id=sem5.id,
                name="S5AD",
                student_count=42,
            )
        )
        # Subgroups for S3AD lab sessions
        batch_a = class_repo.create_student_group(
            StudentGroup(id="batch-s3ad-1", class_group_id=class_s3.id, name="Batch 1", student_count=23)
        )
        batch_b = class_repo.create_student_group(
            StudentGroup(id="batch-s3ad-2", class_group_id=class_s3.id, name="Batch 2", student_count=22)
        )
    else:
        class_s3 = existing_classes[0]
        class_s5 = existing_classes[1] if len(existing_classes) > 1 else class_s3

    # 5. Rooms (Theory halls and laboratory)
    existing_rooms = room_repo.list_all()
    if not existing_rooms:
        room_lh1 = room_repo.save(
            Room(
                id="room-lh101",
                name="Lecture Hall 101",
                code="LH101",
                room_type=RoomType.LECTURE_HALL,
                capacity=60,
                building="CS Block",
                floor=1,
            )
        )
        room_cr2 = room_repo.save(
            Room(
                id="room-cr102",
                name="Classroom 102",
                code="CR102",
                room_type=RoomType.SEMINAR_ROOM,
                capacity=50,
                building="CS Block",
                floor=1,
            )
        )
        room_lab = room_repo.save(
            Room(
                id="room-lab01",
                name="Computing Lab 1",
                code="LAB01",
                room_type=RoomType.COMPUTER_LAB,
                capacity=40,
                building="CS Block",
                floor=2,
            )
        )
    else:
        room_lh1 = existing_rooms[0]
        room_cr2 = existing_rooms[1] if len(existing_rooms) > 1 else room_lh1
        room_lab = existing_rooms[2] if len(existing_rooms) > 2 else room_lh1

    # 6. Teachers (T1 through T9 matching data.py)
    teachers = []
    for i in range(1, 10):
        emp_id = f"T{i}"
        teacher = teacher_repo.get_by_employee_id(emp_id)
        if not teacher:
            teacher = teacher_repo.save(
                Teacher(
                    id=f"teacher-t{i}",
                    department_id=dept.id,
                    name=f"Faculty Member {i}",
                    employee_id=emp_id,
                    email=f"t{i}@sit.edu",
                    is_full_time=True,
                )
            )
            # Default workload rule
            teacher_repo.save_workload_rule(
                TeacherWorkloadRule(
                    id=f"rule-t{i}",
                    teacher_id=teacher.id,
                    max_periods_per_week=18,
                    min_periods_per_week=6,
                    max_periods_per_day=4,
                    max_consecutive_periods=2,
                )
            )
        teachers.append(teacher)

    # 7. Teacher Availability and Preferences
    # T1 is unavailable Friday (day 4) period 5
    teacher_repo.set_availability(
        TeacherAvailability(
            id="avail-t1-fri-p5",
            teacher_id=teachers[0].id,
            day_of_week=4,
            period_index=5,
            is_available=False,
        )
    )
    # T2 prefers morning periods
    pref_repo.save_preference(
        TeacherPreference(
            id="pref-t2-mon-p0",
            teacher_id=teachers[1].id,
            day_of_week=0,
            period_index=0,
            preference_weight=5,
        )
    )

    # 8. Subjects (Separated credits and weekly contact hours!)
    sub_ds = subject_repo.get_by_code(str(dept.id), "CS301")
    if not sub_ds:
        sub_ds = subject_repo.save(
            Subject(
                id="sub-cs301",
                department_id=dept.id,
                code="CS301",
                name="Data Structures & Algorithms",
                credits=4.0,  # 4 credits
            )
        )

    sub_dslab = subject_repo.get_by_code(str(dept.id), "CS331")
    if not sub_dslab:
        sub_dslab = subject_repo.save(
            Subject(
                id="sub-cs331",
                department_id=dept.id,
                code="CS331",
                name="Data Structures Lab",
                credits=2.0,  # 2 credits
            )
        )

    sub_ml = subject_repo.get_by_code(str(dept.id), "CS501")
    if not sub_ml:
        sub_ml = subject_repo.save(
            Subject(
                id="sub-cs501",
                department_id=dept.id,
                code="CS501",
                name="Machine Learning",
                credits=3.0,
            )
        )

    # 9. Teacher Qualifications (Eligibility)
    teacher_repo.add_qualification(
        TeacherQualification(
            id="qual-t1-cs301",
            teacher_id=teachers[0].id,
            subject_id=sub_ds.id,
            competency_level=1,
            preference_score=5,
        )
    )
    teacher_repo.add_qualification(
        TeacherQualification(
            id="qual-t2-cs331",
            teacher_id=teachers[1].id,
            subject_id=sub_dslab.id,
            competency_level=1,
            preference_score=5,
        )
    )

    # 10. Subject Offerings & Session Requirements
    offerings = subject_repo.list_offerings(str(sem3.id))
    if not offerings:
        offering_ds = subject_repo.save_offering(
            SubjectOffering(
                id="off-cs301-sem3",
                subject_id=sub_ds.id,
                semester_id=sem3.id,
                weekly_contact_hours=4.0,  # 4 contact hours
                weekly_periods=4,
            )
        )
        subject_repo.save_session_requirement(
            SubjectSessionRequirement(
                id="req-cs301",
                offering_id=offering_ds.id,
                session_type=SessionType.THEORY,
                consecutive_periods=1,
                frequency_per_week=4,
                requires_lab=False,
            )
        )

        offering_dslab = subject_repo.save_offering(
            SubjectOffering(
                id="off-cs331-sem3",
                subject_id=sub_dslab.id,
                semester_id=sem3.id,
                weekly_contact_hours=3.0,  # 3 contact hours
                weekly_periods=3,
            )
        )
        subject_repo.save_session_requirement(
            SubjectSessionRequirement(
                id="req-cs331",
                offering_id=offering_dslab.id,
                session_type=SessionType.LABORATORY,
                consecutive_periods=2,
                frequency_per_week=1,
                requires_lab=True,
                preferred_room_type=RoomType.COMPUTER_LAB,
            )
        )

        # Class Subject Assignments
        csa_ds = subject_repo.assign_subject_to_class(
            ClassSubjectAssignment(
                id="csa-s3ad-cs301",
                class_group_id=class_s3.id,
                offering_id=offering_ds.id,
                primary_teacher_id=teachers[0].id,
            )
        )
        csa_dslab = subject_repo.assign_subject_to_class(
            ClassSubjectAssignment(
                id="csa-s3ad-cs331",
                class_group_id=class_s3.id,
                offering_id=offering_dslab.id,
                primary_teacher_id=teachers[1].id,
            )
        )

    # 11. Initial Draft Timetable
    draft_tt = tt_repo.get_by_id("tt-draft-sem3")
    if not draft_tt:
        draft_tt = Timetable(
            id="tt-draft-sem3",
            name="CSE Semester 3 Draft",
            academic_year_id=acad_year.id,
            semester_id=sem3.id,
            version=1,
            is_published=False,
        )
        tt_repo.save_timetable(draft_tt, [])

    logger.info("Development data seeded successfully.")
    return {
        "institution_id": institution.id,
        "department_id": dept.id,
        "academic_year_id": acad_year.id,
        "semester_3_id": sem3.id,
        "class_s3_id": class_s3.id,
        "class_s5_id": class_s5.id,
        "teachers_count": len(teachers),
        "timetable_id": draft_tt.id,
    }
