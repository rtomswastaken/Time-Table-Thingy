"""Reusable CustomTkinter Export Dialog component for Agent 8 shell integration.

Allows users to configure timetable schedule and report exports:
- Destination format (PDF, Excel, CSV)
- Layout perspective (Class Grid, Teacher Grid, Room Grid, Master Tabular)
- File destination path selection
- Background generation to keep UI responsive
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from exchange.models import ExportFormat, ExportResult, TimetableLayout
from exchange.service import ImportExportServiceImpl


class ExportDialogController:
    """Headless controller for managing timetable export settings and dispatching workers."""

    def __init__(self, service: ImportExportServiceImpl):
        self.service = service
        self.selected_format = ExportFormat.EXCEL
        self.selected_layout = TimetableLayout.CLASS_GRID
        self.destination_path: Optional[str] = None
        self.timetable_id: str = "DEFAULT"

    def execute_export(
        self,
        timetable_id: str,
        output_path: str,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def _worker():
            try:
                if self.selected_format == ExportFormat.PDF:
                    out = self.service.export_timetable_to_pdf(
                        timetable_id, output_path, layout=self.selected_layout.value
                    )
                elif self.selected_format == ExportFormat.EXCEL:
                    out = self.service.export_timetable_to_excel(timetable_id, output_path)
                else:  # CSV
                    out = self.service.export_timetable_to_csv(timetable_id, output_path)
                on_success(out)
            except Exception as exc:
                on_error(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


class ExportDialogFrame:
    """CustomTkinter export configuration panel."""

    def __init__(
        self,
        parent: Any,
        service: ImportExportServiceImpl,
        timetable_id: str = "DEFAULT",
        on_export_finished: Optional[Callable[[str], None]] = None,
    ):
        self.parent = parent
        self.controller = ExportDialogController(service)
        self.controller.timetable_id = timetable_id
        self.on_export_finished = on_export_finished

        if ctk is not None and hasattr(parent, "winfo_exists"):
            self.frame = ctk.CTkFrame(parent, corner_radius=10)
            self._build_ui()
        else:
            self.frame = None

    def _build_ui(self) -> None:
        if not self.frame or ctk is None:
            return

        self.title_label = ctk.CTkLabel(
            self.frame,
            text="Export Timetable & Reports",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.title_label.pack(pady=(15, 10), padx=20, anchor="w")

        # Format selector
        row1 = ctk.CTkFrame(self.frame, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(row1, text="Export Format:").pack(side="left", padx=(0, 10))
        self.format_dropdown = ctk.CTkOptionMenu(
            row1,
            values=[f.value for f in ExportFormat],
            command=self._on_format_changed,
        )
        self.format_dropdown.set(self.controller.selected_format.value)
        self.format_dropdown.pack(side="left")

        # Layout selector
        row2 = ctk.CTkFrame(self.frame, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(row2, text="Grid Layout (PDF):").pack(side="left", padx=(0, 10))
        self.layout_dropdown = ctk.CTkOptionMenu(
            row2,
            values=[l.value for l in TimetableLayout],
            command=self._on_layout_changed,
        )
        self.layout_dropdown.set(self.controller.selected_layout.value)
        self.layout_dropdown.pack(side="left")

        # Destination path bar
        row3 = ctk.CTkFrame(self.frame, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=10)
        self.path_entry = ctk.CTkEntry(row3, placeholder_text="Select destination file path...")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.browse_btn = ctk.CTkButton(row3, text="Browse...", width=90, command=self._browse_dest)
        self.browse_btn.pack(side="right")

        # Action bar
        actions = ctk.CTkFrame(self.frame, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(10, 15))
        self.status_label = ctk.CTkLabel(actions, text="", text_color="gray")
        self.status_label.pack(side="left")

        self.export_btn = ctk.CTkButton(
            actions,
            text="Export Now",
            command=self._execute_export,
            fg_color="#1F4E79",
        )
        self.export_btn.pack(side="right")

    def _on_format_changed(self, value: str) -> None:
        self.controller.selected_format = ExportFormat(value)

    def _on_layout_changed(self, value: str) -> None:
        self.controller.selected_layout = TimetableLayout(value)

    def _browse_dest(self) -> None:
        from tkinter import filedialog
        fmt = self.controller.selected_format
        if fmt == ExportFormat.PDF:
            def_ext = ".pdf"
            filetypes = [("PDF Document", "*.pdf")]
        elif fmt == ExportFormat.EXCEL:
            def_ext = ".xlsx"
            filetypes = [("Excel Workbook", "*.xlsx")]
        else:
            def_ext = ".csv"
            filetypes = [("CSV File", "*.csv")]

        path = filedialog.asksaveasfilename(defaultextension=def_ext, filetypes=filetypes)
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _execute_export(self) -> None:
        dest = self.path_entry.get().strip()
        if not dest:
            self.status_label.configure(text="Please choose a destination file path.")
            return

        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="Exporting document in background...")

        def on_success(out_file: str):
            def _update():
                self.status_label.configure(text=f"Exported: {Path(out_file).name}")
                self.export_btn.configure(state="normal")
                if self.on_export_finished:
                    self.on_export_finished(out_file)
            if self.frame:
                self.frame.after(0, _update)

        def on_error(exc: Exception):
            def _update():
                self.status_label.configure(text=f"Export failed: {exc}")
                self.export_btn.configure(state="normal")
            if self.frame:
                self.frame.after(0, _update)

        self.controller.execute_export(
            self.controller.timetable_id,
            dest,
            on_success=on_success,
            on_error=on_error,
        )
