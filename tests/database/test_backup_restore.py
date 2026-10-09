"""
Tests for safe SQLite online backup, validation, and restoration.
"""

import tempfile
import unittest
from pathlib import Path

from core.models import Institution
from database.backup import RestoreError, create_backup, restore_backup, validate_backup
from database.connection import DatabaseManager
from database.repositories import InstitutionRepository
from database.schema import initialize_database


class TestBackupRestore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = Path(self.temp_dir.name)
        self.source_db_path = self.db_dir / "source.db"
        self.target_db_path = self.db_dir / "target.db"
        self.backup_path = self.db_dir / "backup.db"

        self.source_manager = DatabaseManager(self.source_db_path)
        initialize_database(self.source_manager)

        # Seed initial record in source
        self.inst_repo = InstitutionRepository(self.source_manager)
        self.inst_repo.save(Institution(id="inst-backup", code="BACKUP_INST", name="Backup Institute"))

    def tearDown(self):
        self.source_manager.close()
        self.temp_dir.cleanup()

    def test_create_and_validate_backup(self):
        saved_path = create_backup(self.source_manager, self.backup_path)
        self.assertTrue(saved_path.is_file())
        self.assertGreater(saved_path.stat().st_size, 0)
        self.assertTrue(validate_backup(saved_path))

    def test_validate_corrupted_or_empty_backup(self):
        corrupt_path = self.db_dir / "corrupt.db"
        corrupt_path.write_text("NOT A REAL SQLITE FILE", encoding="utf-8")
        self.assertFalse(validate_backup(corrupt_path))

        empty_path = self.db_dir / "empty.db"
        empty_path.touch()
        self.assertFalse(validate_backup(empty_path))

    def test_restore_backup_success(self):
        # Create backup of source
        create_backup(self.source_manager, self.backup_path)

        # Create target database with empty/initialized schema
        target_manager = DatabaseManager(self.target_db_path)
        try:
            initialize_database(target_manager)
            target_repo = InstitutionRepository(target_manager)
            self.assertIsNone(target_repo.get_by_code("BACKUP_INST"))

            # Restore into target
            restore_backup(self.backup_path, target_manager, create_pre_restore_snapshot=True)

            # Target should now contain the restored institution
            restored_inst = target_repo.get_by_code("BACKUP_INST")
            self.assertIsNotNone(restored_inst)
            self.assertEqual(restored_inst.name, "Backup Institute")
        finally:
            target_manager.close()

    def test_restore_invalid_backup_raises_and_preserves_target(self):
        bad_backup = self.db_dir / "bad.db"
        bad_backup.write_bytes(b"corrupted binary data")

        target_manager = DatabaseManager(self.target_db_path)
        try:
            initialize_database(target_manager)
            target_repo = InstitutionRepository(target_manager)
            target_repo.save(Institution(id="inst-existing", code="EXISTING", name="Existing Target"))

            with self.assertRaises(RestoreError):
                restore_backup(bad_backup, target_manager)

            # Target must remain completely intact
            intact = target_repo.get_by_code("EXISTING")
            self.assertIsNotNone(intact)
            self.assertEqual(intact.name, "Existing Target")
        finally:
            target_manager.close()


if __name__ == "__main__":
    unittest.main()
