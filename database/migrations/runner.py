"""
Database migration runner.

Tracks applied migrations in a `schema_migrations` table.
Ensures atomic execution of each migration step.
Provides idempotent initialization and forward migrations.
"""

import datetime
import importlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import List, Tuple, Union

from ..connection import DatabaseManager

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


class MigrationRunner:
    """Manages schema migrations for SQLite."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def ensure_migration_table(self, conn: sqlite3.Connection) -> None:
        """Creates the schema_migrations table if it does not already exist."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )

    def get_applied_versions(self, conn: sqlite3.Connection) -> List[int]:
        """Returns list of migration version integers already applied, sorted."""
        self.ensure_migration_table(conn)
        cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        return [row[0] for row in cursor.fetchall()]

    def get_available_migrations(self) -> List[Tuple[int, str, Path]]:
        """
        Scans migrations directory for SQL files matching pattern:
        {version:03d}_{name}.sql, e.g. 001_initial_schema.sql
        """
        migrations = []
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            parts = file.name.split("_", 1)
            if len(parts) == 2 and parts[0].isdigit():
                version = int(parts[0])
                name = parts[1].replace(".sql", "")
                migrations.append((version, name, file))
        return sorted(migrations, key=lambda m: m[0])

    def run_migrations(self) -> List[int]:
        """
        Executes all unapplied migrations in ascending version order.
        Each migration runs within an atomic transaction.
        Returns the list of newly applied version numbers.
        """
        applied_now: List[int] = []
        available = self.get_available_migrations()

        conn = self.db_manager.get_connection()
        self.ensure_migration_table(conn)
        applied_versions = set(self.get_applied_versions(conn))

        for version, name, filepath in available:
            if version in applied_versions:
                continue

            logger.info("Applying migration %03d: %s", version, name)
            with self.db_manager.transaction() as tx_conn:
                sql_content = filepath.read_text(encoding="utf-8")
                tx_conn.executescript(sql_content)
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                tx_conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                    (version, name, now_str),
                )
                applied_now.append(version)

        return applied_now

    def get_current_version(self) -> int:
        """Returns the highest applied schema version or 0 if none."""
        conn = self.db_manager.get_connection()
        self.ensure_migration_table(conn)
        cursor = conn.execute("SELECT MAX(version) FROM schema_migrations;")
        val = cursor.fetchone()[0]
        return val if val is not None else 0
