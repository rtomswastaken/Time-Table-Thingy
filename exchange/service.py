"""ImportExportService implementation.

Satisfies core.interfaces.ImportExportService protocol and provides
end-to-end orchestration for preview, validation, execution, and exports.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.exceptions import EntityNotFoundError, ImportExportError, ValidationError
from core.interfaces import ImportExportService as IImportExportService
from core.models import (
    ClassGroup,
    ConstraintViolation,
    Department,
    Institution,
    Room,
    ScheduledSession,
    Subject,
    Teacher,
    Timetable,
)
from exchange.exporters.csv_exporter import CSVExporter
from exchange.exporters.excel_exporter import ExcelExporter
from exchange.exporters.pdf_exporter import PDFTimetableExporter
from exchange.importers.base import BaseDatasetImporter
from exchange.importers.csv_parser import parse_csv_file
from exchange.importers.entity_importers import (
    AcademicPeriodsImporter,
    ClassAssignmentsImporter,
    ClassesImporter,
    DepartmentsImporter,
    RoomsImporter,
    SubjectOfferingsImporter,
    SubjectsImporter,
    TeacherAvailabilityImporter,
    TeacherQualificationsImporter,
    TeachersImporter,
)
from exchange.importers.excel_parser import parse_excel_file
from exchange.models import (
    DatasetType,
    ExportFormat,
    ExportResult,
    ImportMode,
    ImportPreview,
    ImportResult,
    ImportValidationSummary,
    TimetableLayout,
)
from exchange.templates.template_generator import TemplateGenerator


class ImportExportServiceImpl:
    """Core implementation of ImportExportService."""

    def __init__(
        self,
        db_manager: Optional[Any] = None,
        repositories: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.db_manager = db_manager
        self.repositories = repositories or {}
        self.context = context or {}

        # Register specialized importers
        self._importers: Dict[DatasetType, BaseDatasetImporter] = {
            DatasetType.DEPARTMENTS: DepartmentsImporter(),
            DatasetType.ACADEMIC_PERIODS: AcademicPeriodsImporter(),
            DatasetType.CLASSES: ClassesImporter(),
            DatasetType.TEACHERS: TeachersImporter(),
            DatasetType.TEACHER_QUALIFICATIONS: TeacherQualificationsImporter(),
            DatasetType.SUBJECTS: SubjectsImporter(),
            DatasetType.SUBJECT_OFFERINGS: SubjectOfferingsImporter(),
            DatasetType.CLASS_ASSIGNMENTS: ClassAssignmentsImporter(),
            DatasetType.ROOMS: RoomsImporter(),
            DatasetType.TEACHER_AVAILABILITY: TeacherAvailabilityImporter(),
        }

    def get_importer(self, dataset_type: DatasetType) -> BaseDatasetImporter:
        importer = self._importers.get(dataset_type)
        if not importer:
            raise ImportExportError(f"No importer registered for dataset: {dataset_type}")
        return importer

    def parse_file(self, file_path: str | Path) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Reads file based on extension (.csv or .xlsx)."""
        p = Path(file_path)
        ext = p.suffix.lower()
        if ext == ".csv":
            return parse_csv_file(p)
        elif ext in (".xlsx", ".xls"):
            return parse_excel_file(p)
        else:
            raise ImportExportError(f"Unsupported file format '{ext}'. Must be .csv or .xlsx.")

    def preview_import(
        self,
        file_path: str | Path,
        dataset_type: DatasetType,
    ) -> ImportPreview:
        """Step 2 of import workflow: parses file and generates a structured preview."""
        headers, rows = self.parse_file(file_path)
        importer = self.get_importer(dataset_type)
        return importer.generate_preview(Path(file_path).name, headers, rows)

    def validate_import(
        self,
        file_path: str | Path,
        dataset_type: DatasetType,
        column_mapping: Optional[Dict[str, str]] = None,
        mode: ImportMode = ImportMode.CREATE,
    ) -> Tuple[List[Dict[str, Any]], ImportValidationSummary]:
        """Step 4 of import workflow: validates rows against schema and existing data context."""
        headers, rows = self.parse_file(file_path)
        importer = self.get_importer(dataset_type)

        # Use provided mapping or auto-mapping
        if not column_mapping:
            mapping, missing = importer.get_mapper().auto_map(headers)
            if missing:
                raise ValidationError(f"Missing required columns for {dataset_type.value}: {', '.join(missing)}")
        else:
            mapping = column_mapping

        # Build context from repositories if available
        active_context = self._build_validation_context(dataset_type)
        return importer.validate_rows(rows, mapping, mode, active_context)

    def execute_import(
        self,
        file_path: str | Path,
        dataset_type: DatasetType,
        column_mapping: Optional[Dict[str, str]] = None,
        mode: ImportMode = ImportMode.CREATE,
    ) -> ImportResult:
        """Step 6 of import workflow: validates and persists records with rollback support."""
        canonical_rows, summary = self.validate_import(file_path, dataset_type, column_mapping, mode)

        if not summary.can_proceed and mode != ImportMode.VALIDATE_ONLY:
            return ImportResult(
                success=False,
                mode=mode,
                dataset_type=dataset_type,
                total_processed=summary.total_rows,
                created_count=0,
                updated_count=0,
                skipped_count=summary.invalid_rows,
                errors=summary.errors,
                warnings=summary.warnings,
                message=f"Import failed with {len(summary.errors)} validation errors. No records were committed.",
            )

        importer = self.get_importer(dataset_type)
        active_context = self._build_validation_context(dataset_type)

        # Atomic transaction execution if db_manager is available
        if self.db_manager and hasattr(self.db_manager, "transaction"):
            with self.db_manager.transaction():
                return importer.persist_records(canonical_rows, mode, active_context)
        else:
            return importer.persist_records(canonical_rows, mode, active_context)

    def _build_validation_context(self, dataset_type: DatasetType) -> Dict[str, Any]:
        """Populates lookup caches and repositories for referential validation."""
        ctx = dict(self.context)

        # Merge repositories into context
        for k, v in self.repositories.items():
            ctx[k] = v

        dept_repo = self.repositories.get("department_repo")
        if dept_repo and hasattr(dept_repo, "list_all"):
            try:
                depts = dept_repo.list_all()
                ctx["existing_department_codes"] = {d.code.upper() for d in depts}
                ctx["valid_department_codes"] = {d.code.upper() for d in depts}
                ctx["dept_id_map"] = {d.code.upper(): d.id for d in depts}
            except Exception:
                pass

        teacher_repo = self.repositories.get("teacher_repo")
        if teacher_repo and hasattr(teacher_repo, "list_all"):
            try:
                teachers = teacher_repo.list_all()
                ctx["existing_teacher_emp_ids"] = {t.employee_id.upper() for t in teachers}
                ctx["valid_teacher_emp_ids"] = {t.employee_id.upper() for t in teachers}
                ctx["teacher_id_map"] = {t.employee_id.upper(): t.id for t in teachers}
            except Exception:
                pass

        subject_repo = self.repositories.get("subject_repo")
        if subject_repo and hasattr(subject_repo, "list_all"):
            try:
                subs = subject_repo.list_all()
                ctx["existing_subject_codes"] = {s.code.upper() for s in subs}
                ctx["valid_subject_codes"] = {s.code.upper() for s in subs}
                ctx["subject_id_map"] = {s.code.upper(): s.id for s in subs}
            except Exception:
                pass

        room_repo = self.repositories.get("room_repo")
        if room_repo and hasattr(room_repo, "list_all"):
            try:
                rooms = room_repo.list_all()
                ctx["existing_room_codes"] = {r.code.upper() for r in rooms}
                ctx["valid_room_codes"] = {r.code.upper() for r in rooms}
            except Exception:
                pass

        class_repo = self.repositories.get("class_repo")
        if class_repo and hasattr(class_repo, "list_all"):
            try:
                classes = class_repo.list_all()
                ctx["existing_class_names"] = {c.name for c in classes}
                ctx["valid_class_names"] = {c.name for c in classes}
                ctx["class_id_map"] = {c.name: c.id for c in classes}
            except Exception:
                pass

        return ctx

    # -----------------------------------------------------------------------
    # Protocol Methods (core.interfaces.ImportExportService)
    # -----------------------------------------------------------------------

    def import_curriculum_from_csv(self, file_path: str) -> Dict[str, int]:
        """Imports subjects/curriculum from a CSV file.

        Returns a dictionary of counts: {'created': N, 'updated': M, 'errors': E}.
        """
        result = self.execute_import(file_path, DatasetType.SUBJECTS, mode=ImportMode.UPSERT)
        return {
            "created": result.created_count,
            "updated": result.updated_count,
            "errors": len(result.errors),
        }

    def import_faculty_from_excel(self, file_path: str) -> Dict[str, int]:
        """Imports teacher profiles from an Excel (.xlsx) file.

        Returns a dictionary of counts: {'created': N, 'updated': M, 'errors': E}.
        """
        result = self.execute_import(file_path, DatasetType.TEACHERS, mode=ImportMode.UPSERT)
        return {
            "created": result.created_count,
            "updated": result.updated_count,
            "errors": len(result.errors),
        }

    def export_timetable_to_pdf(
        self,
        timetable_id: str,
        output_path: str,
        layout: str = "CLASS_GRID",
    ) -> str:
        """Exports timetable to a printable PDF document."""
        sessions, metadata, violations = self._load_timetable_data(timetable_id)
        layout_enum = TimetableLayout(layout) if layout in TimetableLayout.__members__ else TimetableLayout.CLASS_GRID
        res = PDFTimetableExporter.export_timetable(
            output_path=output_path,
            sessions=sessions,
            layout=layout_enum,
            metadata=metadata,
            conflicts=violations,
        )
        return res.file_path

    def export_timetable_to_excel(self, timetable_id: str, output_path: str) -> str:
        """Exports timetable to an Excel (.xlsx) workbook."""
        sessions, metadata, _ = self._load_timetable_data(timetable_id)
        res = ExcelExporter.export_full_workbook(
            output_path=output_path,
            sessions=sessions,
            metadata=metadata,
        )
        return res.file_path

    def export_timetable_to_csv(self, timetable_id: str, output_path: str) -> str:
        """Exports timetable sessions to a CSV file."""
        sessions, metadata, _ = self._load_timetable_data(timetable_id)
        res = CSVExporter.export_sessions(sessions, output_path, metadata)
        return res.file_path

    def _load_timetable_data(
        self,
        timetable_id: str,
    ) -> Tuple[List[ScheduledSession], Dict[str, Any], List[Any]]:
        """Retrieves sessions and metadata from repositories or context."""
        tt_repo = self.repositories.get("tt_repo") or self.repositories.get("timetable_repo")
        sessions: List[ScheduledSession] = []
        tt: Optional[Timetable] = None

        if tt_repo:
            sessions = tt_repo.get_sessions(timetable_id)
            if hasattr(tt_repo, "get_by_id"):
                tt = tt_repo.get_by_id(timetable_id)
        else:
            sessions = self.context.get("sessions", [])

        meta: Dict[str, Any] = dict(self.context.get("metadata", {}))

        if tt:
            meta["timetable_name"] = tt.name
            meta["version"] = tt.version
            meta["is_published"] = tt.is_published

        # Map display lookups from repositories if available
        teacher_repo = self.repositories.get("teacher_repo")
        if teacher_repo and hasattr(teacher_repo, "list_all"):
            try:
                ts = teacher_repo.list_all()
                meta["teacher_emp_map"] = {t.id: t.employee_id for t in ts}
                meta["teacher_name_map"] = {t.id: t.name for t in ts}
            except Exception:
                pass

        class_repo = self.repositories.get("class_repo")
        if class_repo and hasattr(class_repo, "list_all"):
            try:
                cs = class_repo.list_all()
                meta["class_name_map"] = {c.id: c.name for c in cs}
            except Exception:
                pass

        subject_repo = self.repositories.get("subject_repo")
        if subject_repo and hasattr(subject_repo, "list_all"):
            try:
                subs = subject_repo.list_all()
                meta["sub_code_map"] = {s.id: s.code for s in subs}
                meta["sub_name_map"] = {s.id: s.name for s in subs}
            except Exception:
                pass

        room_repo = self.repositories.get("room_repo")
        if room_repo and hasattr(room_repo, "list_all"):
            try:
                rooms = room_repo.list_all()
                meta["room_code_map"] = {r.id: r.code for r in rooms}
                meta["room_name_map"] = {r.id: r.name for r in rooms}
            except Exception:
                pass

        violations = self.context.get("violations", [])
        return sessions, meta, violations


# Compatibility alias
ImportExportService = ImportExportServiceImpl
