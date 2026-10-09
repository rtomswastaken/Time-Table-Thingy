"""
Tests for development seed data generation and referential integrity.
"""

import tempfile
import unittest
from pathlib import Path

from database.connection import DatabaseManager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    RoomRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from database.schema import check_foreign_keys, check_integrity
from database.seed import seed_development_data


class TestSeedData(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_seed.db"
        self.db_manager = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_seed_development_data_populates_entities(self):
        result = seed_development_data(self.db_manager)
        self.assertIn("institution_id", result)
        self.assertIn("department_id", result)
        self.assertEqual(result["teachers_count"], 9)

        # Integrity and foreign key verification
        self.assertTrue(check_integrity(self.db_manager), "Seeded database must pass integrity check.")
        violations = check_foreign_keys(self.db_manager)
        self.assertEqual(len(violations), 0, f"Seeded database must have 0 foreign key violations: {violations}")

        # Verify specific entities
        inst_repo = InstitutionRepository(self.db_manager)
        inst = inst_repo.get_by_id(result["institution_id"])
        self.assertIsNotNone(inst)
        self.assertEqual(inst.code, "SIT")

        teacher_repo = TeacherRepository(self.db_manager)
        t1 = teacher_repo.get_by_employee_id("T1")
        self.assertIsNotNone(t1)

        # Verify teacher availability
        # T1 is unavailable Friday (day 4) period 5
        self.assertFalse(teacher_repo.is_teacher_available(str(t1.id), 4, 5))
        self.assertTrue(teacher_repo.is_teacher_available(str(t1.id), 0, 1))

        # Verify subjects have credits and weekly contact hours distinct
        sub_repo = SubjectRepository(self.db_manager)
        sub_dslab = sub_repo.get_by_code(str(result["department_id"]), "CS331")
        self.assertIsNotNone(sub_dslab)
        self.assertEqual(sub_dslab.credits, 2.0)

        # Check offerings for CS331
        offerings = sub_repo.list_offerings(str(result["semester_3_id"]))
        dslab_offering = next((o for o in offerings if o.subject_id == sub_dslab.id), None)
        self.assertIsNotNone(dslab_offering)
        self.assertEqual(dslab_offering.weekly_contact_hours, 3.0)


if __name__ == "__main__":
    unittest.main()
