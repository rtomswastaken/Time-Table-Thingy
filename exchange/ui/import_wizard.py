"""Reusable CustomTkinter Import Wizard component for Agent 8 shell integration.

Provides:
- Dataset selection (Departments, Faculty, Subjects, Classes, Rooms, etc.)
- Import mode selection (CREATE, UPDATE, UPSERT, VALIDATE_ONLY)
- File browsing (.csv, .xlsx)
- Live preview (column mapping, sample rows, empty field statistics)
- Pre-flight validation error summary
- Background worker execution to prevent GUI thread freezing
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from exchange.models import DatasetType, ImportMode, ImportPreview, ImportResult, ImportValidationSummary
from exchange.service import ImportExportServiceImpl


class ImportWizardController:
    """Headless controller for managing import workflow state independently of GUI."""

    def __init__(self, service: ImportExportServiceImpl):
        self.service = service
        self.selected_dataset = DatasetType.TEACHERS
        self.selected_mode = ImportMode.CREATE
        self.file_path: Optional[str] = None
        self.preview: Optional[ImportPreview] = None
        self.column_mapping: Dict[str, str] = {}
        self.validation_summary: Optional[ImportValidationSummary] = None
        self.last_result: Optional[ImportResult] = None

    def load_file(self, file_path: str, dataset_type: Optional[DatasetType] = None) -> ImportPreview:
        self.file_path = file_path
        if dataset_type:
            self.selected_dataset = dataset_type
        self.preview = self.service.preview_import(file_path, self.selected_dataset)
        self.column_mapping = dict(self.preview.detected_mapping)
        return self.preview

    def validate(self) -> ImportValidationSummary:
        if not self.file_path:
            raise ValueError("No file selected.")
        _, summary = self.service.validate_import(
            self.file_path,
            self.selected_dataset,
            column_mapping=self.column_mapping,
            mode=self.selected_mode,
        )
        self.validation_summary = summary
        return summary

    def execute_in_background(
        self,
        on_success: Callable[[ImportResult], None],
        on_error: Callable[[Exception], None],
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Executes validation and persistence on a background thread."""
        if not self.file_path:
            on_error(ValueError("No file loaded."))
            return

        def _worker():
            try:
                if on_progress:
                    on_progress("Validating records...")
                result = self.service.execute_import(
                    self.file_path,
                    self.selected_dataset,
                    column_mapping=self.column_mapping,
                    mode=self.selected_mode,
                )
                self.last_result = result
                on_success(result)
            except Exception as exc:
                on_error(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


class ImportWizardFrame:
    """CustomTkinter embeddable frame for the multi-step import wizard."""

    def __init__(
        self,
        parent: Any,
        service: ImportExportServiceImpl,
        on_import_completed: Optional[Callable[[ImportResult], None]] = None,
    ):
        self.parent = parent
        self.controller = ImportWizardController(service)
        self.on_import_completed = on_import_completed

        if ctk is not None and hasattr(parent, "winfo_exists"):
            self.frame = ctk.CTkFrame(parent, corner_radius=10)
            self._build_ui()
        else:
            self.frame = None

    def _build_ui(self) -> None:
        if not self.frame or ctk is None:
            return

        # Header Title
        self.title_label = ctk.CTkLabel(
            self.frame,
            text="Academic Data Import Wizard",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.title_label.pack(pady=(15, 5), padx=20, anchor="w")

        # Step 1: Dataset & Mode Configuration
        config_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        config_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(config_frame, text="Dataset Type:").pack(side="left", padx=(0, 5))
        self.dataset_dropdown = ctk.CTkOptionMenu(
            config_frame,
            values=[ds.value for ds in DatasetType],
            command=self._on_dataset_changed,
        )
        self.dataset_dropdown.set(self.controller.selected_dataset.value)
        self.dataset_dropdown.pack(side="left", padx=5)

        ctk.CTkLabel(config_frame, text="Import Mode:").pack(side="left", padx=(20, 5))
        self.mode_dropdown = ctk.CTkOptionMenu(
            config_frame,
            values=[m.value for m in ImportMode],
            command=self._on_mode_changed,
        )
        self.mode_dropdown.set(self.controller.selected_mode.value)
        self.mode_dropdown.pack(side="left", padx=5)

        # File Selection Bar
        file_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        file_frame.pack(fill="x", padx=20, pady=10)

        self.file_path_label = ctk.CTkLabel(
            file_frame,
            text="No file selected (.csv or .xlsx)",
            text_color="gray",
        )
        self.file_path_label.pack(side="left", fill="x", expand=True, padx=5)

        self.browse_button = ctk.CTkButton(
            file_frame,
            text="Browse File...",
            command=self._browse_file,
            width=120,
        )
        self.browse_button.pack(side="right", padx=5)

        # Preview / Summary Display Text Box
        self.summary_box = ctk.CTkTextbox(self.frame, height=180, font=ctk.CTkFont(size=11))
        self.summary_box.pack(fill="both", expand=True, padx=20, pady=10)
        self.summary_box.insert("1.0", "Select a file to inspect data preview and column mapping.")

        # Bottom Action Bar
        action_bar = ctk.CTkFrame(self.frame, fg_color="transparent")
        action_bar.pack(fill="x", padx=20, pady=(5, 15))

        self.status_label = ctk.CTkLabel(action_bar, text="", text_color="gray")
        self.status_label.pack(side="left")

        self.import_button = ctk.CTkButton(
            action_bar,
            text="Validate & Import",
            command=self._execute_import,
            state="disabled",
            fg_color="#1F4E79",
        )
        self.import_button.pack(side="right")

    def _on_dataset_changed(self, value: str) -> None:
        self.controller.selected_dataset = DatasetType(value)
        if self.controller.file_path:
            self._reload_preview()

    def _on_mode_changed(self, value: str) -> None:
        self.controller.selected_mode = ImportMode(value)

    def _browse_file(self) -> None:
        from tkinter import filedialog
        filetypes = [
            ("Supported Spreadsheets", "*.csv *.xlsx *.xls"),
            ("CSV Files", "*.csv"),
            ("Excel Workbooks", "*.xlsx *.xls"),
            ("All Files", "*.*"),
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.file_path_label.configure(text=Path(path).name, text_color="white")
            self.controller.file_path = path
            self._reload_preview()

    def _reload_preview(self) -> None:
        if not self.controller.file_path:
            return
        try:
            preview = self.controller.load_file(self.controller.file_path, self.controller.selected_dataset)
            self.summary_box.delete("1.0", "end")
            msg = [
                f"File: {preview.file_name} ({preview.total_rows} rows)",
                f"Detected Columns: {', '.join(preview.column_names)}",
                f"Active Field Mapping: {preview.detected_mapping}",
            ]
            if preview.missing_required_columns:
                msg.append(f"WARNING: Missing required fields: {', '.join(preview.missing_required_columns)}")
            if preview.duplicate_identifiers:
                msg.append(f"WARNING: Duplicate IDs in file: {', '.join(preview.duplicate_identifiers)}")

            msg.append("\nSample Record 1:")
            if preview.sample_rows:
                msg.append(str(preview.sample_rows[0]))

            self.summary_box.insert("1.0", "\n".join(msg))
            self.import_button.configure(state="normal")
        except Exception as exc:
            self.summary_box.delete("1.0", "end")
            self.summary_box.insert("1.0", f"Error reading file:\n{exc}")
            self.import_button.configure(state="disabled")

    def _execute_import(self) -> None:
        self.import_button.configure(state="disabled")
        self.status_label.configure(text="Processing import in background...")

        def on_success(result: ImportResult):
            def _update():
                self.status_label.configure(text=f"Completed: {result.message}")
                self.import_button.configure(state="normal")
                self.summary_box.delete("1.0", "end")
                report = [
                    f"Import Outcome: {'SUCCESS' if result.success else 'FAILED'}",
                    f"Created: {result.created_count}",
                    f"Updated: {result.updated_count}",
                    f"Errors: {len(result.errors)}",
                ]
                for err in result.errors[:10]:
                    report.append(f"Row {err.row_number} [{err.field}]: {err.message}")
                self.summary_box.insert("1.0", "\n".join(report))
                if self.on_import_completed:
                    self.on_import_completed(result)
            if self.frame:
                self.frame.after(0, _update)

        def on_error(exc: Exception):
            def _update():
                self.status_label.configure(text=f"Error: {exc}")
                self.import_button.configure(state="normal")
                self.summary_box.delete("1.0", "end")
                self.summary_box.insert("1.0", f"Import failed with error:\n{exc}")
            if self.frame:
                self.frame.after(0, _update)

        self.controller.execute_in_background(on_success=on_success, on_error=on_error)
