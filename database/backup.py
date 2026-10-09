"""
Safe SQLite database backup and restoration utilities.

Uses SQLite's online backup API (Connection.backup) to guarantee
atomic, transactionally consistent snapshots even under active concurrency and WAL mode.
"""

import datetime
import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional, Union

from .connection import DatabaseManager

logger = logging.getLogger(__name__)

CORE_TABLES = {"schema_migrations", "institutions", "departments", "timetables", "scheduled_sessions"}


class BackupError(Exception):
    """Raised when a backup operation fails."""
    pass


class RestoreError(Exception):
    """Raised when a restore operation fails."""
    pass


def create_backup(
    db_manager: DatabaseManager,
    backup_path: Union[str, Path],
    pages_per_step: int = -1,
) -> Path:
    """
    Creates a transaction-consistent backup using SQLite's online backup API.
    
    Args:
        db_manager: The active DatabaseManager instance.
        backup_path: Target file path for the backup file.
        pages_per_step: Number of pages to copy per step (-1 copies all pages in one atomic step).
        
    Returns:
        Path to the newly created backup file.
    """
    dest_path = Path(backup_path).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    source_conn = db_manager.get_connection()

    try:
        dest_conn = sqlite3.connect(str(dest_path), isolation_level=None)
        try:
            source_conn.backup(dest_conn, pages=pages_per_step)
        finally:
            dest_conn.close()
    except Exception as e:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        logger.error("Failed to create database backup at %s: %s", dest_path, e)
        raise BackupError(f"Backup failed: {e}") from e

    logger.info("Successfully created database backup at %s", dest_path)
    return dest_path


def validate_backup(backup_path: Union[str, Path]) -> bool:
    """
    Validates that a backup file is a valid, uncorrupted SQLite database
    containing the expected core schema.
    """
    path = Path(backup_path)
    if not path.is_file() or path.stat().st_size == 0:
        logger.warning("Backup validation failed: file %s is missing or empty.", path)
        return False

    try:
        conn = sqlite3.connect(str(path), isolation_level=None)
        try:
            # Check PRAGMA integrity_check
            cursor = conn.execute("PRAGMA integrity_check;")
            rows = cursor.fetchall()
            if not rows or rows[0][0] != "ok":
                logger.warning("Integrity check failed for backup %s: %s", path, rows)
                return False

            # Check core tables presence
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            if not CORE_TABLES.issubset(tables):
                missing = CORE_TABLES - tables
                logger.warning("Backup %s is missing required tables: %s", path, missing)
                return False

            return True
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Validation exception for backup %s: %s", path, e)
        return False


def restore_backup(
    backup_path: Union[str, Path],
    target_db_manager: DatabaseManager,
    create_pre_restore_snapshot: bool = True,
) -> Optional[Path]:
    """
    Restores the database from a backup file after verifying backup integrity.
    Optionally creates a pre-restore snapshot of the target database so that
    user data is preserved if the restoration fails.

    Args:
        backup_path: Path to the backup file to restore.
        target_db_manager: DatabaseManager for the target database.
        create_pre_restore_snapshot: Whether to create a safety backup before restoring.

    Returns:
        Path to the pre-restore snapshot file if one was created, else None.
    """
    path = Path(backup_path).resolve()
    if not validate_backup(path):
        raise RestoreError(f"Cannot restore: Backup file {path} is invalid or corrupted.")

    pre_restore_path: Optional[Path] = None

    # Step 1: Create a safety backup of the existing live database if it's on disk
    if create_pre_restore_snapshot and not target_db_manager.is_memory:
        target_file = Path(target_db_manager.db_path)
        if target_file.is_file() and target_file.stat().st_size > 0:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_restore_path = target_file.parent / f"{target_file.stem}_pre_restore_{timestamp}.bak"
            try:
                create_backup(target_db_manager, pre_restore_path)
                logger.info("Created pre-restore safety snapshot at %s", pre_restore_path)
            except Exception as e:
                raise RestoreError(f"Failed to create pre-restore snapshot: {e}") from e

    # Step 2: Use SQLite backup API from the backup file into the target connection
    try:
        backup_conn = sqlite3.connect(str(path), isolation_level=None)
        target_conn = target_db_manager.get_connection()
        try:
            backup_conn.backup(target_conn)
        finally:
            backup_conn.close()

        # Step 3: Run post-restore integrity check on the target connection
        cursor = target_conn.execute("PRAGMA integrity_check;")
        res = cursor.fetchall()
        if not res or res[0][0] != "ok":
            raise RestoreError(f"Target database failed integrity check after restoration: {res}")

        logger.info("Successfully restored database from %s", path)
        return pre_restore_path
    except Exception as e:
        logger.error("Restore failed: %s", e)
        # If pre-restore snapshot exists and target is on disk, we can attempt rolling back to it
        if pre_restore_path and pre_restore_path.is_file():
            logger.warning("Attempting rollback to pre-restore snapshot %s", pre_restore_path)
            try:
                rollback_conn = sqlite3.connect(str(pre_restore_path), isolation_level=None)
                target_conn = target_db_manager.get_connection()
                rollback_conn.backup(target_conn)
                rollback_conn.close()
            except Exception as rb_err:
                logger.critical("Fatal: failed to rollback after restore failure: %s", rb_err)
        raise RestoreError(f"Restore operation failed: {e}") from e
