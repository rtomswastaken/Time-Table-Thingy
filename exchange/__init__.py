"""Exchange package for academic data import, timetable export, and reporting."""

from exchange.models import (
    ColumnMapping,
    ConflictReportRow,
    DatasetType,
    ExportFormat,
    ExportResult,
    ImportMode,
    ImportPreview,
    ImportResult,
    ImportRowError,
    ImportRowWarning,
    ImportValidationSummary,
    RoomUtilizationRow,
    TimetableLayout,
    TimetableSummary,
    UnscheduledSessionRow,
    WorkloadReportRow,
)
from exchange.security import (
    sanitize_spreadsheet_value,
    desanitize_spreadsheet_value,
    sanitize_filename,
    validate_import_file_path,
    validate_export_file_path,
)
from exchange.importers import (
    AcademicPeriodsImporter,
    BaseDatasetImporter,
    ClassAssignmentsImporter,
    ClassesImporter,
    ColumnMapper,
    DepartmentsImporter,
    RoomsImporter,
    SubjectOfferingsImporter,
    SubjectsImporter,
    TeacherAvailabilityImporter,
    TeacherQualificationsImporter,
    TeachersImporter,
    normalize_column_name,
    parse_csv_file,
    parse_excel_file,
)
from exchange.exporters import (
    CSVExporter,
    ExcelExporter,
    PDFTimetableExporter,
)
from exchange.reports import (
    ConflictReportGenerator,
    RoomUtilizationReportGenerator,
    TimetableSummaryReportGenerator,
    WorkloadReportGenerator,
)
from exchange.templates import (
    TEMPLATE_CATALOG,
    TemplateGenerator,
)
from exchange.service import ImportExportService, ImportExportServiceImpl
from exchange.report_service import ReportService, ReportServiceImpl

__all__ = [
    # Models
    "ColumnMapping",
    "ConflictReportRow",
    "DatasetType",
    "ExportFormat",
    "ExportResult",
    "ImportMode",
    "ImportPreview",
    "ImportResult",
    "ImportRowError",
    "ImportRowWarning",
    "ImportValidationSummary",
    "RoomUtilizationRow",
    "TimetableLayout",
    "TimetableSummary",
    "UnscheduledSessionRow",
    "WorkloadReportRow",
    # Security
    "sanitize_spreadsheet_value",
    "desanitize_spreadsheet_value",
    "sanitize_filename",
    "validate_import_file_path",
    "validate_export_file_path",
    # Importers
    "AcademicPeriodsImporter",
    "BaseDatasetImporter",
    "ClassAssignmentsImporter",
    "ClassesImporter",
    "ColumnMapper",
    "DepartmentsImporter",
    "RoomsImporter",
    "SubjectOfferingsImporter",
    "SubjectsImporter",
    "TeacherAvailabilityImporter",
    "TeacherQualificationsImporter",
    "TeachersImporter",
    "normalize_column_name",
    "parse_csv_file",
    "parse_excel_file",
    # Exporters
    "CSVExporter",
    "ExcelExporter",
    "PDFTimetableExporter",
    # Reports
    "ConflictReportGenerator",
    "RoomUtilizationReportGenerator",
    "TimetableSummaryReportGenerator",
    "WorkloadReportGenerator",
    # Templates
    "TEMPLATE_CATALOG",
    "TemplateGenerator",
    # Services
    "ImportExportService",
    "ImportExportServiceImpl",
    "ReportService",
    "ReportServiceImpl",
]
