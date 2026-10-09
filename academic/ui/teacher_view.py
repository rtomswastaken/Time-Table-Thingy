"""
Teacher and Faculty Management Screen.
Allows administrators to manage faculty profiles, departmental associations,
and subject qualifications / teaching eligibility.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from academic.institution_service import InstitutionService
from academic.subject_service import SubjectService
from academic.teacher_service import TeacherService
from academic.ui.components import ConfirmDialog, DataTable, FormField, NotificationBanner
from academic.ui.theme import (
    COLOR_BG_CARD,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_CAPTION,
    FONT_SECTION,
    FONT_SUBTITLE,
    FONT_TITLE,
    PADDING_LARGE,
    PADDING_MEDIUM,
    PADDING_SMALL,
)


class TeacherView(ctk.CTkFrame):
    """View for managing Faculty Profiles and Subject Qualifications."""

    def __init__(
        self,
        master,
        teacher_service: TeacherService,
        institution_service: InstitutionService,
        subject_service: Optional[SubjectService] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.teacher_service = teacher_service
        self.inst_service = institution_service
        self.subject_service = subject_service

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Teachers & Faculty", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        actions_box = ctk.CTkFrame(title_box, fg_color="transparent")
        actions_box.pack(side="right")

        qual_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Qualification",
            font=FONT_BODY_BOLD,
            command=self._open_add_qualification_dialog,
            height=34,
        )
        qual_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        add_teacher_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Teacher",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_teacher_dialog,
            height=34,
        )
        add_teacher_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Search and Filter Bar
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8, height=48)
        bar.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        search_lbl = ctk.CTkLabel(bar, text="Search:", font=FONT_BODY_BOLD)
        search_lbl.pack(side="left", padx=(PADDING_MEDIUM, PADDING_SMALL))

        self.search_entry = ctk.CTkEntry(bar, placeholder_text="Search by name or employee ID...", width=240)
        self.search_entry.pack(side="left", padx=(0, PADDING_MEDIUM))
        self.search_entry.bind("<KeyRelease>", lambda _: self.load_data())

        dept_lbl = ctk.CTkLabel(bar, text="Department:", font=FONT_BODY_BOLD)
        dept_lbl.pack(side="left", padx=(0, PADDING_SMALL))

        self.dept_filter = ctk.CTkComboBox(bar, values=["All Departments"], command=lambda _: self.load_data())
        self.dept_filter.pack(side="left")

        # Table
        columns = [
            ("employee_id", "Employee ID", 120),
            ("name", "Faculty Name", 220),
            ("dept_name", "Department", 160),
            ("email", "Email", 200),
            ("status", "Employment", 110),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_edit=self._open_edit_teacher_dialog,
            on_delete=self._confirm_delete_teacher,
            empty_text="No teachers registered yet. Click '+ Add Teacher' to add faculty.",
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
        teachers = self.teacher_service.list_teachers(department_id=dept_id, search=search_text)
        dept_map = {str(d.id): d.name for d in depts}

        rows = []
        for t in teachers:
            rows.append({
                "id": str(t.id),
                "employee_id": t.employee_id,
                "name": t.name,
                "dept_name": dept_map.get(str(t.department_id), "Unknown"),
                "email": t.email or "N/A",
                "status": "Full-Time" if t.is_full_time else "Part-Time",
            })
        self.table.set_data(rows)

    def _open_add_teacher_dialog(self) -> None:
        self._show_teacher_dialog("Add Teacher Profile", None)

    def _open_edit_teacher_dialog(self, item: Dict[str, Any]) -> None:
        self._show_teacher_dialog("Edit Teacher Profile", item)

    def _show_teacher_dialog(self, title: str, teacher_data: Optional[Dict[str, Any]]) -> None:
        depts = self.inst_service.list_departments()
        if not depts:
            self.banner.show_error("Please create at least one department first.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x360")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        name_f = FormField(form, "Full Name", default_value=teacher_data.get("name", "") if teacher_data else "", required=True)
        name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        emp_f = FormField(form, "Employee ID", default_value=teacher_data.get("employee_id", "") if teacher_data else "", required=True)
        emp_f.pack(fill="x", pady=(0, PADDING_SMALL))

        dept_names = [d.name for d in depts]
        dept_f = FormField(form, "Department", field_type="combobox", options=dept_names, default_value=teacher_data.get("dept_name", dept_names[0]) if teacher_data else dept_names[0], required=True)
        dept_f.pack(fill="x", pady=(0, PADDING_SMALL))

        email_f = FormField(form, "Email Address", default_value=teacher_data.get("email", "") if teacher_data and teacher_data.get("email") != "N/A" else "")
        email_f.pack(fill="x", pady=(0, PADDING_SMALL))

        ft_f = FormField(form, "Full-Time Employee", field_type="checkbox", default_value=bool(not teacher_data or teacher_data.get("status") == "Full-Time"))
        ft_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_teacher():
            name = name_f.get_value()
            emp_id = emp_f.get_value()
            chosen_dept = next((d for d in depts if d.name == dept_f.get_value()), depts[0])
            email = email_f.get_value()
            is_ft = bool(ft_f.get_value())

            try:
                if teacher_data:
                    self.teacher_service.update_teacher(
                        teacher_id=teacher_data["id"],
                        name=name,
                        employee_id=emp_id,
                        email=email,
                        is_full_time=is_ft,
                    )
                    self.banner.show_success(f"Teacher '{name}' updated.")
                else:
                    self.teacher_service.create_teacher(
                        department_id=str(chosen_dept.id),
                        name=name,
                        employee_id=emp_id,
                        email=email,
                        is_full_time=is_ft,
                    )
                    self.banner.show_success(f"Teacher '{name}' registered.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                emp_f.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_teacher, width=80)
        save_btn.pack(side="right")

    def _open_add_qualification_dialog(self) -> None:
        teachers = self.teacher_service.list_teachers()
        subjects = self.subject_service.list_subjects() if self.subject_service else []

        if not teachers or not subjects:
            self.banner.show_error("Please register at least one teacher and one subject first.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Add Teaching Qualification")
        dlg.geometry("420x320")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        t_names = [f"{t.name} ({t.employee_id})" for t in teachers]
        t_f = FormField(form, "Faculty Member", field_type="combobox", options=t_names, default_value=t_names[0], required=True)
        t_f.pack(fill="x", pady=(0, PADDING_SMALL))

        s_names = [f"{s.code} - {s.name}" for s in subjects]
        s_f = FormField(form, "Qualified Subject", field_type="combobox", options=s_names, default_value=s_names[0], required=True)
        s_f.pack(fill="x", pady=(0, PADDING_SMALL))

        comp_levels = ["1 - Primary Instructor", "2 - Secondary / Backup"]
        comp_f = FormField(form, "Competency Level", field_type="combobox", options=comp_levels, default_value=comp_levels[0])
        comp_f.pack(fill="x", pady=(0, PADDING_SMALL))

        score_f = FormField(form, "Preference Score (1=Low, 5=High)", field_type="spinbox", default_value=5)
        score_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_qual():
            chosen_t_idx = t_names.index(t_f.get_value())
            chosen_teacher = teachers[chosen_t_idx]

            chosen_s_idx = s_names.index(s_f.get_value())
            chosen_subject = subjects[chosen_s_idx]

            comp_level = 1 if "1" in comp_f.get_value() else 2
            pref_score = int(score_f.get_value())

            try:
                self.teacher_service.add_qualification(
                    teacher_id=str(chosen_teacher.id),
                    subject_id=str(chosen_subject.id),
                    competency_level=comp_level,
                    preference_score=pref_score,
                )
                self.banner.show_success(f"Qualification saved for {chosen_teacher.name} -> {chosen_subject.code}.")
                dlg.destroy()
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_qual, width=80)
        save_btn.pack(side="right")

    def _confirm_delete_teacher(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Deactivate / Delete Teacher",
            message=f"Are you sure you want to remove teacher '{item.get('name')}' ({item.get('employee_id')})?",
            on_confirm=lambda: self._delete_teacher(item["id"]),
            is_destructive=True,
        )

    def _delete_teacher(self, teacher_id: str) -> None:
        try:
            self.teacher_service.delete_teacher(teacher_id)
            self.banner.show_success("Teacher removed.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot remove teacher: {e}")
