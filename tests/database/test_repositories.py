"""
Comprehensive unit tests for repository CRUD, filtering, relationships, and protocols.
"""

import tempfile
import unittest
from pathlib import Path

from core.interfaces import Repository
from core.models import (
    AcademicYear,
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomType,
    Semester,
    Subject,
    SubjectOffering,
    Teacher,
    TeacherAvailability,
    TeacherPreference,
    TeacherQualification,
)
from database.connection import DatabaseManager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    PreferenceRepository,
    RoomRepository,
    SubjectRepository,
    TeacherRepository,
)
from database.schema import initialize_database


class TestRepositories(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_repos.db"
        self.db_manager = DatabaseManager(self.db_path)
        initialize_database(self.db_manager)

        self.inst_repo = InstitutionRepository(self.db_manager)
        self.dept_repo = DepartmentRepository(self.db_manager)
        self.teacher_repo = TeacherRepository(self.db_manager)
        self.subject_repo = SubjectRepository(self.db_manager)
        self.class_repo = ClassGroupRepository(self.db_manager)
        self.room_repo = RoomRepository(self.db_manager)
        self.pref_repo = PreferenceRepository(self.db_manager)

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_repository_protocol_conformance(self):
        self.assertTrue(isinstance(self.inst_repo, Repository))
        self.assertTrue(isinstance(self.dept_repo, Repository))
        self.assertTrue(isinstance(self.teacher_repo, Repository))
        self.assertTrue(isinstance(self.subject_repo, Repository))
        self.assertTrue(isinstance(self.class_repo, Repository))
        self.assertTrue(isinstance(self.room_repo, Repository))

    def test_institution_and_department_lifecycle(self):
        # Create institution
        inst = self.inst_repo.save(Institution(id="inst-1", code="MIT", name="Mass Tech"))
        self.assertEqual(inst.id, "inst-1")

        # Retrieve
        fetched = self.inst_repo.get_by_id("inst-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Mass Tech")

        # Academic year
        ay = self.inst_repo.save_academic_year(
            AcademicYear(id="ay-1", name="2026-2027", start_date="2026-08-01", end_date="2027-05-31")
        )
        self.assertIsNotNone(ay.id)

        # Semester
        sem = self.inst_repo.save_semester(
            Semester(id="sem-1", academic_year_id=ay.id, number=1, term_name="Semester 1")
        )
        self.assertIsNotNone(sem.id)

        # Create department
        dept = self.dept_repo.save(Department(id="dept-1", institution_id=inst.id, code="CS", name="Computer Science"))
        self.assertIsNotNone(dept.id)

        # List departments
        depts = self.dept_repo.list_by_institution(str(inst.id))
        self.assertEqual(len(depts), 1)
        self.assertEqual(depts[0].code, "CS")

    def test_teacher_qualifications_and_availability(self):
        inst = self.inst_repo.save(Institution(id="i-1", code="I", name="Institute"))
        dept = self.dept_repo.save(Department(id="d-1", institution_id=inst.id, code="D", name="Dept"))

        teacher = self.teacher_repo.save(
            Teacher(
                id="t-1",
                department_id=dept.id,
                employee_id="EMP01",
                name="Alan Turing",
                email="alan@cam.ac.uk",
            )
        )

        subject = self.subject_repo.save(
            Subject(
                id="sub-1",
                department_id=dept.id,
                code="CS101",
                name="Intro to CS",
                credits=3.0,
            )
        )

        # Add qualification (eligibility)
        qual = self.teacher_repo.add_qualification(
            TeacherQualification(id="q-1", teacher_id=teacher.id, subject_id=subject.id, competency_level=1)
        )
        self.assertIsNotNone(qual.id)

        quals = self.teacher_repo.list_qualifications_for_teacher(str(teacher.id))
        self.assertEqual(len(quals), 1)
        self.assertEqual(quals[0].subject_id, subject.id)

        # Availability
        self.teacher_repo.set_availability(
            TeacherAvailability(id="av-1", teacher_id=teacher.id, day_of_week=0, period_index=1, is_available=False)
        )
        self.assertFalse(self.teacher_repo.is_teacher_available(str(teacher.id), 0, 1))
        # Defaults to True for unconfigured slot
        self.assertTrue(self.teacher_repo.is_teacher_available(str(teacher.id), 0, 2))

    def test_subject_offering_and_assignment(self):
        inst = self.inst_repo.save(Institution(id="i-2", code="I2", name="Institute 2"))
        dept = self.dept_repo.save(Department(id="d-2", institution_id=inst.id, code="MATH", name="Mathematics"))
        ay = self.inst_repo.save_academic_year(
            AcademicYear(id="ay-2", name="2026-2027", start_date="2026-08-01", end_date="2027-05-31")
        )
        sem = self.inst_repo.save_semester(Semester(id="sem-2", academic_year_id=ay.id, number=1, term_name="Sem 1"))

        cg = self.class_repo.save(
            ClassGroup(id="cg-1", department_id=dept.id, semester_id=sem.id, name="M101", student_count=30)
        )
        teacher = self.teacher_repo.save(
            Teacher(id="t-2", department_id=dept.id, employee_id="T_MATH", name="Leonhard Euler")
        )
        sub = self.subject_repo.save(
            Subject(
                id="sub-2",
                department_id=dept.id,
                code="CALC1",
                name="Calculus I",
                credits=4.0,  # 4 credits
            )
        )

        offering = self.subject_repo.save_offering(
            SubjectOffering(
                id="off-2",
                subject_id=sub.id,
                semester_id=sem.id,
                weekly_contact_hours=5.0,  # 5 contact hours (distinct from 4 credits)
                weekly_periods=5,
            )
        )
        self.assertIsNotNone(offering.id)

        csa = self.subject_repo.assign_subject_to_class(
            ClassSubjectAssignment(
                id="csa-1",
                class_group_id=cg.id,
                offering_id=offering.id,
                primary_teacher_id=teacher.id,
            )
        )
        self.assertIsNotNone(csa.id)

        assignments = self.subject_repo.list_assignments(class_group_id=str(cg.id))
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].primary_teacher_id, teacher.id)

    def test_room_lifecycle(self):
        room = self.room_repo.save(
            Room(id="r-1", building="Science Hall", code="301", name="Physics Lab", room_type=RoomType.COMPUTER_LAB, capacity=30)
        )
        self.assertIsNotNone(room.id)

        fetched = self.room_repo.get_by_id("r-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.room_type, RoomType.COMPUTER_LAB)


if __name__ == "__main__":
    unittest.main()
