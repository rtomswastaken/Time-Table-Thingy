"""
Subject Management Screen.
Allows administrators to manage the academic course catalog, credits, and subject definitions.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from academic.institution_service import InstitutionService
from academic.subject_service import SubjectService
from academic.ui.components import ConfirmDialog, DataTable, FormField, NotificationBanner
from academic.ui.theme import (
    COLOR_BG_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SECTION,
    FONT_TITLE,
    PADDING_LARGE,
    PADDING_MEDIUM,
    PADDING_SMALL,
)


class SubjectView(ctk.CTkFrame):
    """View for managing Course Catalog and Subject Definitions."""

    def __init__(
        self,
        master,
        subject_service: SubjectService,
        institution_service: InstitutionService,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.subject_service = subject_service
        self.inst_service = institution_service

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Subject Catalog", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        add_subj_btn = ctk.CTkButton(
            title_box,
            text="+ Add Subject",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_subject_dialog,
            height=34,
        )
        add_subj_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Search & Filter
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8, height=48)
        bar.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        search_lbl = ctk.CTkLabel(bar, text="Search:", font=FONT_BODY_BOLD)
        search_lbl.pack(side="left", padx=(PADDING_MEDIUM, PADDING_SMALL))

        self.search_entry = ctk.CTkEntry(bar, placeholder_text="Search code or name...", width=240)
        self.search_entry.pack(side="left", padx=(0, PADDING_MEDIUM))
        self.search_entry.bind("<KeyRelease>", lambda _: self.load_data())

        dept_lbl = ctk.CTkLabel(bar, text="Department:", font=FONT_BODY_BOLD)
        dept_lbl.pack(side="left", padx=(0, PADDING_SMALL))

        self.dept_filter = ctk.CTkComboBox(bar, values=["All Departments"], command=lambda _: self.load_data())
        self.dept_filter.pack(side="left")

        # Table
        columns = [
            ("code", "Code", 120),
            ("name", "Subject Name", 300),
            ("dept_name", "Department", 180),
            ("credits", "Credits", 90),
            ("is_elective", "Type", 120),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_edit=self._open_edit_subject_dialog,
            on_delete=self._confirm_delete_subject,
            empty_text="No subjects found in the catalog. Click '+ Add Subject' to create one.",
        )
        self.table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_LARGE))

    def load_data(self) -> None:
        depts = self.inst_service.list_departments()
        dept_names = ["All Departments"] + [d.name for d in depts]
        self.dept_filter.configure(values=dept_names)

        chosen_dept = self.dept_filter.get()
        dept_id = None
        if chosen_dept and chosen_dept != "All Departments":
            matched = next((d for d in depts if d.name == chosen_dept), None)
            if matched:
                dept_id = str(matched.id)

        search_text = self.search_entry.get().strip()
        subjects = self.subject_service.list_subjects(department_id=dept_id, search=search_text)
        dept_map = {str(d.id): d.name for d in depts}

        rows = []
        for s in subjects:
            rows.append({
                "id": str(s.id),
                "code": s.code,
                "name": s.name,
                "dept_name": dept_map.get(str(s.department_id), "Unknown"),
                "credits": f"{s.credits:.1f}",
                "is_elective": "Elective" if s.is_elective else "Core",
            })
        self.table.set_data(rows)

    def _open_add_subject_dialog(self) -> None:
        self._show_subject_dialog("Add Subject to Catalog", None)

    def _open_edit_subject_dialog(self, item: Dict[str, Any]) -> None:
        self._show_subject_dialog("Edit Subject", item)

    def _show_subject_dialog(self, title: str, subject_data: Optional[Dict[str, Any]]) -> None:
        depts = self.inst_service.list_departments()
        if not depts:
            self.banner.show_error("Please create at least one department first.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x340")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        code_f = FormField(form, "Subject Code (e.g. CS301)", default_value=subject_data.get("code", "") if subject_data else "", required=True)
        code_f.pack(fill="x", pady=(0, PADDING_SMALL))

        name_f = FormField(form, "Subject Name", default_value=subject_data.get("name", "") if subject_data else "", required=True)
        name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        dept_names = [d.name for d in depts]
        dept_f = FormField(form, "Department", field_type="combobox", options=dept_names, default_value=subject_data.get("dept_name", dept_names[0]) if subject_data else dept_names[0], required=True)
        dept_f.pack(fill="x", pady=(0, PADDING_SMALL))

        credits_val = subject_data.get("credits", "3.0") if subject_data else "3.0"
        credits_f = FormField(form, "Academic Credits", field_type="spinbox", default_value=credits_val, required=True)
        credits_f.pack(fill="x", pady=(0, PADDING_SMALL))

        is_elec = bool(subject_data and subject_data.get("is_elective") == "Elective")
        elec_f = FormField(form, "Elective Course", field_type="checkbox", default_value=is_elec)
        elec_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_subject():
            code = code_f.get_value()
            name = name_f.get_value()
            chosen_dept = next((d for d in depts if d.name == dept_f.get_value()), depts[0])
            credits_num = float(credits_f.get_value())
            is_elective = bool(elec_f.get_value())

            try:
                if subject_data:
                    self.subject_service.update_subject(
                        subject_id=subject_data["id"],
                        code=code,
                        name=name,
                        credits=credits_num,
                        is_elective=is_elective,
                    )
                    self.banner.show_success(f"Subject '{code}' updated.")
                else:
                    self.subject_service.create_subject(
                        department_id=str(chosen_dept.id),
                        code=code,
                        name=name,
                        credits=credits_num,
                        is_elective=is_elective,
                    )
                    self.banner.show_success(f"Subject '{code}' added to catalog.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                code_f.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_subject, width=80)
        save_btn.pack(side="right")

    def _confirm_delete_subject(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Delete Subject",
            message=f"Are you sure you want to delete subject '{item.get('name')}' ({item.get('code')})?",
            on_confirm=lambda: self._delete_subject(item["id"]),
            is_destructive=True,
        )

    def _delete_subject(self, subject_id: str) -> None:
        try:
            self.subject_service.delete_subject(subject_id)
            self.banner.show_success("Subject deleted from catalog.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot delete subject: {e}")
