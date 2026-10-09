"""
Base repository providing common persistence primitives.
"""

import sqlite3
from typing import Any, Dict, List, Optional
from ..connection import DatabaseManager


class BaseRepository:
    """Base class for all SQLite domain repositories."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    @property
    def connection(self) -> sqlite3.Connection:
        """Returns the thread-local SQLite connection."""
        return self.db_manager.get_connection()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Executes a parameterized SQL statement."""
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_seq: List[tuple]) -> sqlite3.Cursor:
        """Executes a parameterized SQL statement across a sequence of parameters."""
        return self.connection.executemany(sql, params_seq)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetches a single row or None."""
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetches all rows."""
        cursor = self.execute(sql, params)
        return cursor.fetchall()
