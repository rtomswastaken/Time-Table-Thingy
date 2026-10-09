"""
Tests for database connection management, PRAGMA enforcement, and transaction safety.
"""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from database.connection import DatabaseManager


class TestDatabaseConnection(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_conn.db"
        self.db_manager = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_foreign_keys_pragma_enabled(self):
        conn = self.db_manager.get_connection()
        cursor = conn.execute("PRAGMA foreign_keys;")
        val = cursor.fetchone()[0]
        self.assertEqual(val, 1, "Foreign keys must be enabled on every connection.")

    def test_busy_timeout_configured(self):
        conn = self.db_manager.get_connection()
        cursor = conn.execute("PRAGMA busy_timeout;")
        val = cursor.fetchone()[0]
        self.assertGreaterEqual(val, 5000, "busy_timeout should be at least 5000ms.")

    def test_transaction_commit_success(self):
        conn = self.db_manager.get_connection()
        conn.execute("CREATE TABLE test_tx (id INTEGER PRIMARY KEY, val TEXT);")

        with self.db_manager.transaction() as tx:
            tx.execute("INSERT INTO test_tx (val) VALUES ('saved');")

        row = self.db_manager.get_connection().execute("SELECT val FROM test_tx WHERE id = 1;").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["val"], "saved")

    def test_transaction_rollback_on_error(self):
        conn = self.db_manager.get_connection()
        conn.execute("CREATE TABLE test_rollback (id INTEGER PRIMARY KEY, val TEXT UNIQUE);")

        # First insert
        with self.db_manager.transaction() as tx:
            tx.execute("INSERT INTO test_rollback (val) VALUES ('first');")

        # Second transaction fails on unique violation
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db_manager.transaction() as tx:
                tx.execute("INSERT INTO test_rollback (val) VALUES ('second');")
                tx.execute("INSERT INTO test_rollback (val) VALUES ('first');")  # Violates unique constraint

        # Verify 'second' was rolled back
        cursor = self.db_manager.get_connection().execute("SELECT count(*) FROM test_rollback WHERE val = 'second';")
        self.assertEqual(cursor.fetchone()[0], 0, "Failed transaction must roll back all changes.")

    def test_thread_connections_isolated(self):
        conn1 = self.db_manager.get_connection()
        other_conn = []

        def worker():
            c = self.db_manager.get_connection()
            other_conn.append(c)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertEqual(len(other_conn), 1)
        self.assertIsNot(conn1, other_conn[0], "Different threads must obtain separate connections.")


if __name__ == "__main__":
    unittest.main()
