"""
Schema management, initialization, and integrity validation.
"""

import logging
import sqlite3
from typing import List, Optional

from .connection import DatabaseManager, get_db_manager
from .migrations.runner import MigrationRunner

logger = logging.getLogger(__name__)


def initialize_database(db_manager: Optional[DatabaseManager] = None) -> List[int]:
    """
    Initializes the database schema using versioned migrations.
    Safe and idempotent: runs only unapplied migrations.
    Returns the list of migration versions applied during this call.
    """
    mgr = db_manager or get_db_manager()
    runner = MigrationRunner(mgr)
    applied = runner.run_migrations()
    logger.info("Database initialized. Applied %d migrations.", len(applied))
    return applied


def check_integrity(db_manager: Optional[DatabaseManager] = None) -> bool:
    """
    Executes PRAGMA integrity_check to verify SQLite database file integrity.
    Returns True if database is healthy ('ok'), False otherwise.
    """
    mgr = db_manager or get_db_manager()
    conn = mgr.get_connection()
    cursor = conn.execute("PRAGMA integrity_check;")
    result = cursor.fetchall()
    if len(result) == 1 and result[0][0] == "ok":
        return True
    logger.error("Integrity check failed: %s", result)
    return False


def check_foreign_keys(db_manager: Optional[DatabaseManager] = None) -> List[dict]:
    """
    Executes PRAGMA foreign_key_check to verify that all foreign key constraints
    are satisfied across the database.
    Returns a list of violation dictionaries if any exist.
    """
    mgr = db_manager or get_db_manager()
    conn = mgr.get_connection()
    cursor = conn.execute("PRAGMA foreign_key_check;")
    rows = cursor.fetchall()
    violations = []
    for row in rows:
        violations.append({
            "table": row[0],
            "rowid": row[1],
            "parent_table": row[2],
            "fkid": row[3],
        })
    return violations
