"""
Institution and Department Management Screen.
Allows administrators to configure institutional parameters and departmental units.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from academic.institution_service import InstitutionService
from academic.ui.components import ConfirmDialog, DataTable, FormField, NotificationBanner
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


class DepartmentView(ctk.CTkFrame):
    """View for managing Institution parameters and Departments."""

    def __init__(self, master, institution_service: InstitutionService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.service = institution_service
        self.current_inst = None

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        # Title bar
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Institution & Departments", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        add_dept_btn = ctk.CTkButton(
            title_box,
            text="+ Add Department",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_department_dialog,
            height=34,
        )
        add_dept_btn.pack(side="right")

        # Notification Banner
        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Institution Configuration Card
        inst_card = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8)
        inst_card.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        inst_header = ctk.CTkLabel(inst_card, text="Institution Settings", font=FONT_SUBTITLE, anchor="w")
        inst_header.pack(fill="x", padx=PADDING_MEDIUM, pady=(PADDING_MEDIUM, PADDING_SMALL))

        # Settings row
        settings_grid = ctk.CTkFrame(inst_card, fg_color="transparent")
        settings_grid.pack(fill="x", padx=PADDING_MEDIUM, pady=(0, PADDING_SMALL))

        self.inst_name_field = FormField(settings_grid, "Institution Name", required=True)
        self.inst_name_field.pack(side="left", fill="x", expand=True, padx=(0, PADDING_SMALL))

        self.inst_code_field = FormField(settings_grid, "Code", required=True)
        self.inst_code_field.pack(side="left", fill="x", expand=True, padx=(0, PADDING_SMALL))

        self.periods_field = FormField(settings_grid, "Periods / Day", field_type="spinbox")
        self.periods_field.pack(side="left", fill="x", expand=True, padx=(0, PADDING_SMALL))

        self.duration_field = FormField(settings_grid, "Duration (min)", field_type="spinbox")
        self.duration_field.pack(side="left", fill="x", expand=True)

        save_inst_btn = ctk.CTkButton(
            inst_card,
            text="Save Settings",
            font=FONT_BODY,
            command=self._save_institution_settings,
            height=30,
            width=120,
        )
        save_inst_btn.pack(anchor="e", padx=PADDING_MEDIUM, pady=(0, PADDING_MEDIUM))

        # Departments Section
        dept_header = ctk.CTkLabel(self, text="Department Roster", font=FONT_SECTION, anchor="w")
        dept_header.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Table
        columns = [
            ("code", "Code", 100),
            ("name", "Department Name", 320),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_edit=self._open_edit_department_dialog,
            on_delete=self._confirm_delete_department,
            empty_text="No departments configured yet. Click '+ Add Department' to begin.",
        )
        self.table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_LARGE))

    def load_data(self) -> None:
        self.current_inst = self.service.get_or_create_default_institution()
        self.inst_name_field.set_value(self.current_inst.name)
        self.inst_code_field.set_value(self.current_inst.code)
        self.periods_field.set_value(self.current_inst.periods_per_day)
        self.duration_field.set_value(self.current_inst.period_duration_minutes)

        depts = self.service.list_departments(str(self.current_inst.id))
        rows = [{"id": str(d.id), "code": d.code, "name": d.name} for d in depts]
        self.table.set_data(rows)

    def _save_institution_settings(self) -> None:
        try:
            self.service.update_institution(
                institution_id=str(self.current_inst.id),
                name=self.inst_name_field.get_value(),
                code=self.inst_code_field.get_value(),
                working_days=self.current_inst.working_days,
                periods_per_day=int(self.periods_field.get_value()),
                period_duration_minutes=int(self.duration_field.get_value()),
            )
            self.banner.show_success("Institution settings saved successfully.")
        except Exception as e:
            self.banner.show_error(f"Error saving settings: {e}")

    def _open_add_department_dialog(self) -> None:
        self._show_dept_dialog("Add Department", None)

    def _open_edit_department_dialog(self, item: Dict[str, Any]) -> None:
        self._show_dept_dialog("Edit Department", item)

    def _show_dept_dialog(self, title: str, dept_data: Optional[Dict[str, Any]]) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("400x260")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        code_field = FormField(form, "Department Code", default_value=dept_data.get("code", "") if dept_data else "", required=True)
        code_field.pack(fill="x", pady=(0, PADDING_SMALL))

        name_field = FormField(form, "Department Name", default_value=dept_data.get("name", "") if dept_data else "", required=True)
        name_field.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_dept():
            code = code_field.get_value()
            name = name_field.get_value()
            try:
                if dept_data:
                    self.service.update_department(dept_data["id"], name=name, code=code)
                    self.banner.show_success(f"Department '{code}' updated.")
                else:
                    self.service.create_department(str(self.current_inst.id), name=name, code=code)
                    self.banner.show_success(f"Department '{code}' created.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                code_field.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_dept, width=80)
        save_btn.pack(side="right")

    def _confirm_delete_department(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Delete Department",
            message=f"Are you sure you want to delete department '{item.get('name')}' ({item.get('code')})?",
            on_confirm=lambda: self._delete_department(item["id"]),
            is_destructive=True,
        )

    def _delete_department(self, dept_id: str) -> None:
        try:
            self.service.delete_department(dept_id)
            self.banner.show_success("Department deleted.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot delete department: {e}")
