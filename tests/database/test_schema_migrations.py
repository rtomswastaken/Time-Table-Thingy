"""
Tests for schema initialization, migration tracking, and constraint enforcement.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.connection import DatabaseManager
from database.migrations.runner import MigrationRunner
from database.schema import check_foreign_keys, check_integrity, initialize_database


class TestSchemaMigrations(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_schema.db"
        self.db_manager = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_initialize_database_applies_migrations(self):
        applied = initialize_database(self.db_manager)
        self.assertGreater(len(applied), 0)
        self.assertTrue(check_integrity(self.db_manager))

        runner = MigrationRunner(self.db_manager)
        conn = self.db_manager.get_connection()
        versions = runner.get_applied_versions(conn)
        self.assertIn(1, versions)

    def test_repeated_initialization_is_idempotent(self):
        first_run = initialize_database(self.db_manager)
        self.assertGreater(len(first_run), 0)

        # Second run should apply 0 new migrations
        second_run = initialize_database(self.db_manager)
        self.assertEqual(len(second_run), 0)

    def test_foreign_key_enforcement(self):
        initialize_database(self.db_manager)
        conn = self.db_manager.get_connection()

        # Attempt to insert department referencing nonexistent institution (ID 'missing-inst')
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO departments (id, institution_id, name, code) VALUES ('d1', 'missing-inst', 'CS', 'CSE');"
            )

    def test_unique_constraints_enforced(self):
        initialize_database(self.db_manager)
        conn = self.db_manager.get_connection()

        # Insert institution
        conn.execute("INSERT INTO institutions (id, name, code) VALUES ('inst-1', 'Institute 1', 'INST1');")

        # Duplicate institution code
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO institutions (id, name, code) VALUES ('inst-2', 'Duplicate Institute', 'INST1');")

        # Insert department
        conn.execute("INSERT INTO departments (id, institution_id, name, code) VALUES ('dept-1', 'inst-1', 'Dept 1', 'CS');")
        # Duplicate department code in same institution
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO departments (id, institution_id, name, code) VALUES ('dept-2', 'inst-1', 'Dept 2', 'CS');")

    def test_credits_vs_contact_hours_distinct_columns(self):
        initialize_database(self.db_manager)
        conn = self.db_manager.get_connection()

        # Add institution & department
        conn.execute("INSERT INTO institutions (id, name, code) VALUES ('i1', 'Inst 1', 'I1');")
        conn.execute("INSERT INTO departments (id, institution_id, name, code) VALUES ('d1', 'i1', 'Dept', 'CS');")
        conn.execute("INSERT INTO academic_years (id, name, start_date, end_date) VALUES ('ay1', '2026', '2026-01-01', '2026-12-31');")
        conn.execute("INSERT INTO semesters (id, academic_year_id, number, term_name) VALUES ('sem1', 'ay1', 1, 'Fall');")

        # Insert subject with credits = 2.0
        conn.execute(
            """
            INSERT INTO subjects (id, department_id, code, name, credits)
            VALUES ('sub1', 'd1', 'CS101L', 'Computing Lab', 2.0);
            """
        )
        # Insert offering with weekly_contact_hours = 4.0
        conn.execute(
            """
            INSERT INTO subject_offerings (id, subject_id, semester_id, weekly_contact_hours, weekly_periods)
            VALUES ('off1', 'sub1', 'sem1', 4.0, 4);
            """
        )

        sub_row = conn.execute("SELECT credits FROM subjects WHERE id = 'sub1';").fetchone()
        off_row = conn.execute("SELECT weekly_contact_hours FROM subject_offerings WHERE id = 'off1';").fetchone()
        self.assertEqual(sub_row["credits"], 2.0)
        self.assertEqual(off_row["weekly_contact_hours"], 4.0)
        self.assertNotEqual(sub_row["credits"], off_row["weekly_contact_hours"])


if __name__ == "__main__":
    unittest.main()
