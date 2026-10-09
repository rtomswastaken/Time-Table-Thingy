"""
Database connection management for SQLite.

Features:
- Enforces foreign key constraints on every connection (PRAGMA foreign_keys = ON).
- Enables Write-Ahead Logging (WAL) for concurrency where appropriate.
- Sets busy_timeout to prevent instant failures under concurrency.
- Uses isolation_level=None for predictable explicit transaction control.
- Thread-safe connection handling using thread-local storage.
- Context managers for explicit transaction demarcation with automatic rollback on error.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

DEFAULT_DB_FILENAME = "timetable_thingy.db"


def get_default_db_path() -> Path:
    """Returns the default SQLite database path in user application data or local directory."""
    app_dir = Path.home() / ".timetable_thingy"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / DEFAULT_DB_FILENAME


class DatabaseManager:
    """
    Manages SQLite connections, transactions, and pragmas.
    Supports in-memory testing databases and persistent on-disk databases.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None, timeout: float = 10.0):
        if db_path is None:
            self.db_path = str(get_default_db_path())
            self.is_memory = False
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
            self.is_memory = True
        else:
            self.db_path = str(db_path)
            self.is_memory = False
            parent = Path(self.db_path).parent
            if parent:
                parent.mkdir(parents=True, exist_ok=True)

        self.timeout = timeout
        self._local = threading.local()
        self._shared_memory_conn: Optional[sqlite3.Connection] = None
        if self.is_memory:
            self._shared_memory_conn = self._create_raw_connection()

    def _create_raw_connection(self) -> sqlite3.Connection:
        """Creates a new raw SQLite connection with standard configuration."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            isolation_level=None,  # Autocommit mode: explicit transactions via BEGIN/COMMIT
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False if self.is_memory else True,
        )
        conn.row_factory = sqlite3.Row

        # Mandatory PRAGMAs
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)};")

        if not self.is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")

        return conn

    def get_connection(self) -> sqlite3.Connection:
        """
        Retrieves a thread-specific connection.
        If using in-memory mode, returns the shared in-memory connection.
        """
        if self.is_memory and self._shared_memory_conn is not None:
            return self._shared_memory_conn

        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = self._create_raw_connection()
            self._local.connection = conn
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for an atomic database transaction.
        Executes BEGIN IMMEDIATE, commits on successful block execution, rolls back on exception.
        """
        conn = self.get_connection()
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise

    def close(self) -> None:
        """Closes thread-local connection and shared in-memory connection if any."""
        if hasattr(self._local, "connection") and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None

        if self._shared_memory_conn is not None:
            try:
                self._shared_memory_conn.close()
            except Exception:
                pass
            self._shared_memory_conn = None


# Global singleton instance for default application runtime
_default_manager: Optional[DatabaseManager] = None


def get_db_manager(db_path: Optional[Union[str, Path]] = None) -> DatabaseManager:
    """Returns singleton default DatabaseManager or a new instance if custom path is provided."""
    global _default_manager
    if db_path is not None:
        return DatabaseManager(db_path=db_path)
    if _default_manager is None:
        _default_manager = DatabaseManager()
    return _default_manager


# Convenience aliases for callers
DatabaseConnection = DatabaseManager
get_db = get_db_manager
