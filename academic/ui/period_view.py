"""
Academic Year and Semester Management Screen.
Allows administrators to manage academic periods, terms, and session cycles.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from academic.period_service import AcademicPeriodService
from academic.ui.components import DataTable, FormField, NotificationBanner
from academic.ui.theme import (
    COLOR_BG_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SECTION,
    FONT_SUBTITLE,
    FONT_TITLE,
    PADDING_LARGE,
    PADDING_MEDIUM,
    PADDING_SMALL,
)


class AcademicPeriodView(ctk.CTkFrame):
    """View for managing Academic Years and Semesters."""

    def __init__(self, master, period_service: AcademicPeriodService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.service = period_service
        self.selected_year_id: Optional[str] = None

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Academic Years & Semesters", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        actions_box = ctk.CTkFrame(title_box, fg_color="transparent")
        actions_box.pack(side="right")

        add_sem_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Semester",
            font=FONT_BODY_BOLD,
            command=self._open_add_semester_dialog,
            height=34,
        )
        add_sem_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        add_year_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Academic Year",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_year_dialog,
            height=34,
        )
        add_year_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Academic Years Section
        year_header = ctk.CTkLabel(self, text="Academic Years", font=FONT_SECTION, anchor="w")
        year_header.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        year_cols = [
            ("name", "Academic Year", 180),
            ("start_date", "Start Date", 140),
            ("end_date", "End Date", 140),
            ("is_current", "Current Status", 140),
        ]
        self.year_table = DataTable(
            self,
            columns=year_cols,
            on_edit=self._open_edit_year_dialog,
            empty_text="No academic years defined yet. Click '+ Add Academic Year' to create one.",
        )
        self.year_table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        # Semesters Section
        sem_header = ctk.CTkLabel(self, text="Semesters & Terms", font=FONT_SECTION, anchor="w")
        sem_header.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        sem_cols = [
            ("number", "Sem #", 80),
            ("term_name", "Term / Semester Name", 300),
            ("year_name", "Academic Year", 200),
        ]
        self.sem_table = DataTable(
            self,
            columns=sem_cols,
            on_edit=self._open_edit_semester_dialog,
            empty_text="No semesters defined yet for the active academic year.",
        )
        self.sem_table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_LARGE))

    def load_data(self) -> None:
        years = self.service.list_academic_years()
        year_rows = []
        for y in years:
            year_rows.append({
                "id": str(y.id),
                "name": y.name,
                "start_date": y.start_date or "N/A",
                "end_date": y.end_date or "N/A",
                "is_current": "Active (Current)" if y.is_current else "Inactive",
            })
        self.year_table.set_data(year_rows)

        if years and not self.selected_year_id:
            # Default to first current year or first year
            current_y = next((y for y in years if y.is_current), years[0])
            self.selected_year_id = str(current_y.id)

        all_sems = self.service.list_semesters(self.selected_year_id)
        year_map = {str(y.id): y.name for y in years}
        sem_rows = []
        for s in all_sems:
            sem_rows.append({
                "id": str(s.id),
                "academic_year_id": str(s.academic_year_id),
                "number": s.number,
                "term_name": s.term_name,
                "year_name": year_map.get(str(s.academic_year_id), "Unknown"),
            })
        self.sem_table.set_data(sem_rows)

    def _open_add_year_dialog(self) -> None:
        self._show_year_dialog("Add Academic Year", None)

    def _open_edit_year_dialog(self, item: Dict[str, Any]) -> None:
        self._show_year_dialog("Edit Academic Year", item)

    def _show_year_dialog(self, title: str, year_data: Optional[Dict[str, Any]]) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("400x320")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        name_f = FormField(form, "Academic Year (e.g. 2026-2027)", default_value=year_data.get("name", "") if year_data else "", required=True)
        name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        s_date_f = FormField(form, "Start Date (YYYY-MM-DD)", default_value=year_data.get("start_date", "") if year_data else "2026-08-01")
        s_date_f.pack(fill="x", pady=(0, PADDING_SMALL))

        e_date_f = FormField(form, "End Date (YYYY-MM-DD)", default_value=year_data.get("end_date", "") if year_data else "2027-05-31")
        e_date_f.pack(fill="x", pady=(0, PADDING_SMALL))

        curr_f = FormField(form, "Set as Current Academic Year", field_type="checkbox", default_value=bool(year_data and "Active" in year_data.get("is_current", "")))
        curr_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_year():
            name = name_f.get_value()
            s_date = s_date_f.get_value()
            e_date = e_date_f.get_value()
            is_curr = bool(curr_f.get_value())
            try:
                if year_data:
                    self.service.update_academic_year(year_data["id"], name=name, start_date=s_date, end_date=e_date, is_current=is_curr)
                    self.banner.show_success(f"Academic year '{name}' updated.")
                else:
                    self.service.create_academic_year(name=name, start_date=s_date, end_date=e_date, is_current=is_curr)
                    self.banner.show_success(f"Academic year '{name}' created.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                s_date_f.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_year, width=80)
        save_btn.pack(side="right")

    def _open_add_semester_dialog(self) -> None:
        self._show_semester_dialog("Add Semester", None)

    def _open_edit_semester_dialog(self, item: Dict[str, Any]) -> None:
        self._show_semester_dialog("Edit Semester", item)

    def _show_semester_dialog(self, title: str, sem_data: Optional[Dict[str, Any]]) -> None:
        years = self.service.list_academic_years()
        if not years:
            self.banner.show_error("Please create an academic year first.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("400x290")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        year_names = [y.name for y in years]
        default_y_name = year_names[0]
        if sem_data:
            default_y_name = sem_data.get("year_name", default_y_name)

        year_f = FormField(form, "Academic Year", field_type="combobox", options=year_names, default_value=default_y_name, required=True)
        year_f.pack(fill="x", pady=(0, PADDING_SMALL))

        num_f = FormField(form, "Semester Number", field_type="spinbox", default_value=sem_data.get("number", 1) if sem_data else 1, required=True)
        num_f.pack(fill="x", pady=(0, PADDING_SMALL))

        term_f = FormField(form, "Term / Semester Name", default_value=sem_data.get("term_name", "") if sem_data else "", required=True)
        term_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_sem():
            chosen_y_name = year_f.get_value()
            matched_year = next((y for y in years if y.name == chosen_y_name), years[0])
            num = int(num_f.get_value())
            term_name = term_f.get_value()
            try:
                if sem_data:
                    self.service.update_semester(sem_data["id"], number=num, term_name=term_name)
                    self.banner.show_success(f"Semester '{term_name}' updated.")
                else:
                    self.service.create_semester(str(matched_year.id), number=num, term_name=term_name)
                    self.banner.show_success(f"Semester '{term_name}' created.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                num_f.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_sem, width=80)
        save_btn.pack(side="right")
