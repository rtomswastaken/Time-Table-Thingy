"""
Tests for timetable scheduling persistence, versioning, draft/publish workflows,
and locked session pinning.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.interfaces import TimetableRepository as ITimetableRepository
from core.models import (
    AcademicYear,
    ClassGroup,
    ClassSubjectAssignment,
    Department,
    Institution,
    Room,
    RoomType,
    ScheduledSession,
    Semester,
    Subject,
    SubjectOffering,
    Teacher,
    Timetable,
)
from database.connection import DatabaseManager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    RoomRepository,
    ScheduledSessionRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from database.schema import initialize_database


class TestTimetablePersistence(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tt.db"
        self.db_manager = DatabaseManager(self.db_path)
        initialize_database(self.db_manager)

        self.inst_repo = InstitutionRepository(self.db_manager)
        self.dept_repo = DepartmentRepository(self.db_manager)
        self.class_repo = ClassGroupRepository(self.db_manager)
        self.teacher_repo = TeacherRepository(self.db_manager)
        self.subject_repo = SubjectRepository(self.db_manager)
        self.room_repo = RoomRepository(self.db_manager)
        self.tt_repo = TimetableRepository(self.db_manager)
        self.session_repo = ScheduledSessionRepository(self.db_manager)

        # Baseline setup
        self.inst = self.inst_repo.save(Institution(id="inst-1", code="ENG_COLL", name="Engineering College"))
        self.dept = self.dept_repo.save(Department(id="dept-1", institution_id=self.inst.id, code="CS", name="Computer Science"))
        self.ay = self.inst_repo.save_academic_year(AcademicYear(id="ay-1", name="2026-2027", start_date="2026-01-01", end_date="2026-12-31"))
        self.sem = self.inst_repo.save_semester(Semester(id="sem-1", academic_year_id=self.ay.id, number=3, term_name="Semester 3"))
        self.class_group = self.class_repo.save(ClassGroup(id="cg-1", department_id=self.dept.id, semester_id=self.sem.id, name="S3AD", student_count=40))
        self.teacher1 = self.teacher_repo.save(Teacher(id="t-1", department_id=self.dept.id, employee_id="T1", name="Teacher 1"))
        self.teacher2 = self.teacher_repo.save(Teacher(id="t-2", department_id=self.dept.id, employee_id="T2", name="Teacher 2"))
        self.subject = self.subject_repo.save(Subject(id="sub-1", department_id=self.dept.id, code="CS301", name="Data Structures", credits=4.0))
        self.offering = self.subject_repo.save_offering(SubjectOffering(id="off-1", subject_id=self.subject.id, semester_id=self.sem.id, weekly_contact_hours=4.0, weekly_periods=4))
        self.csa = self.subject_repo.assign_subject_to_class(ClassSubjectAssignment(id="csa-1", class_group_id=self.class_group.id, offering_id=self.offering.id, primary_teacher_id=self.teacher1.id))
        self.room = self.room_repo.save(Room(id="room-1", code="101", name="Hall 101", room_type=RoomType.LECTURE_HALL, capacity=50))

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_timetable_repository_protocol_conformance(self):
        self.assertTrue(isinstance(self.tt_repo, ITimetableRepository))

    def test_save_and_retrieve_timetable_with_sessions(self):
        tt = Timetable(
            id="tt-1",
            name="Fall Schedule",
            academic_year_id=self.ay.id,
            semester_id=self.sem.id,
            version=1,
            is_published=False,
        )
        session = ScheduledSession(
            id="sess-1",
            timetable_id=tt.id,
            class_subject_assignment_id=self.csa.id,
            day_of_week=0,
            start_period=1,
            duration_periods=1,
            room_id=self.room.id,
            teacher_id=self.teacher1.id,
            class_group_id=self.class_group.id,
            is_locked=False,
        )

        self.tt_repo.save_timetable(tt, [session])

        fetched_tt = self.tt_repo.get_by_id("tt-1")
        self.assertIsNotNone(fetched_tt)
        self.assertEqual(fetched_tt.name, "Fall Schedule")

        sessions = self.tt_repo.get_sessions("tt-1")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].day_of_week, 0)
        self.assertEqual(sessions[0].start_period, 1)

    def test_pinned_locked_session_preservation(self):
        tt = Timetable(
            id="tt-locked-test",
            name="Locking Schedule",
            academic_year_id=self.ay.id,
            semester_id=self.sem.id,
        )
        # Session 1 is locked
        sess1 = ScheduledSession(
            id="sess-locked",
            timetable_id=tt.id,
            class_subject_assignment_id=self.csa.id,
            day_of_week=0,
            start_period=1,
            duration_periods=1,
            room_id=self.room.id,
            teacher_id=self.teacher1.id,
            class_group_id=self.class_group.id,
            is_locked=True,
        )
        # Session 2 is unlocked
        sess2 = ScheduledSession(
            id="sess-unlocked",
            timetable_id=tt.id,
            class_subject_assignment_id=self.csa.id,
            day_of_week=0,
            start_period=2,
            duration_periods=1,
            room_id=self.room.id,
            teacher_id=self.teacher1.id,
            class_group_id=self.class_group.id,
            is_locked=False,
        )
        self.tt_repo.save_timetable(tt, [sess1, sess2])

        # Solver outputs replacement sessions (without sess2, with new sess3)
        sess3 = ScheduledSession(
            id="sess-new-3",
            timetable_id=tt.id,
            class_subject_assignment_id=self.csa.id,
            day_of_week=1,
            start_period=3,
            duration_periods=1,
            room_id=self.room.id,
            teacher_id=self.teacher1.id,
            class_group_id=self.class_group.id,
            is_locked=False,
        )
        # Save solver update
        self.tt_repo.save_timetable(tt, [sess3])

        sessions_after = self.tt_repo.get_sessions(str(tt.id))
        session_ids = {s.id for s in sessions_after}
        self.assertIn("sess-locked", session_ids, "Locked session must be preserved across save_timetable calls.")
        self.assertIn("sess-new-3", session_ids, "New solver session must be present.")
        self.assertNotIn("sess-unlocked", session_ids, "Unlocked prior session must be replaced.")

    def test_publishing_draft_preserves_published_history(self):
        tt_v1 = Timetable(
            id="tt-v1",
            name="Fall Schedule",
            academic_year_id=self.ay.id,
            semester_id=self.sem.id,
            version=1,
            is_published=False,
        )
        self.tt_repo.save_timetable(tt_v1, [])

        # Publish v1
        pub_v1 = self.tt_repo.publish("tt-v1")
        self.assertTrue(pub_v1.is_published)
        self.assertEqual(pub_v1.version, 1)

        # Clone into v2 draft
        tt_v2 = self.tt_repo.clone_as_new_version("tt-v1", new_name="Fall Schedule v2")
        self.assertEqual(tt_v2.version, 2)
        self.assertFalse(tt_v2.is_published)

        # Publish v2
        pub_v2 = self.tt_repo.publish(str(tt_v2.id))
        self.assertTrue(pub_v2.is_published)
        self.assertEqual(pub_v2.version, 2)

        # Verify original published v1 is still published and unchanged
        orig_v1 = self.tt_repo.get_by_id("tt-v1")
        self.assertEqual(orig_v1.version, 1)
        self.assertTrue(orig_v1.is_published)


if __name__ == "__main__":
    unittest.main()
