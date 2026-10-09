"""
Class and Section Management Screen.
Allows administrators to manage cohorts, sections, student counts, fixed rooms, and lab batches.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from academic.class_service import ClassService
from academic.institution_service import InstitutionService
from academic.period_service import AcademicPeriodService
from academic.room_service import RoomService
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


class ClassView(ctk.CTkFrame):
    """View for managing Classes, Sections, and Lab Batches."""

    def __init__(
        self,
        master,
        class_service: ClassService,
        institution_service: InstitutionService,
        period_service: AcademicPeriodService,
        room_service: Optional[RoomService] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.class_service = class_service
        self.inst_service = institution_service
        self.period_service = period_service
        self.room_service = room_service

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Classes & Sections", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        actions_box = ctk.CTkFrame(title_box, fg_color="transparent")
        actions_box.pack(side="right")

        add_batch_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Lab Batch",
            font=FONT_BODY_BOLD,
            command=self._open_add_batch_dialog,
            height=34,
        )
        add_batch_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        add_class_btn = ctk.CTkButton(
            actions_box,
            text="+ Add Class Section",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_class_dialog,
            height=34,
        )
        add_class_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8, height=48)
        filter_bar.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        filter_lbl = ctk.CTkLabel(filter_bar, text="Filter Department:", font=FONT_BODY_BOLD)
        filter_lbl.pack(side="left", padx=(PADDING_MEDIUM, PADDING_SMALL))

        self.dept_filter = ctk.CTkComboBox(filter_bar, values=["All Departments"], command=lambda _: self.load_data())
        self.dept_filter.pack(side="left", padx=(0, PADDING_MEDIUM))

        # Table
        columns = [
            ("name", "Class Section", 140),
            ("dept_name", "Department", 180),
            ("sem_name", "Semester", 140),
            ("student_count", "Students", 90),
            ("room_name", "Fixed Room", 140),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_edit=self._open_edit_class_dialog,
            on_delete=self._confirm_delete_class,
            empty_text="No classes created yet. Click '+ Add Class Section' to create one.",
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

        classes = self.class_service.list_class_groups(department_id=dept_id)
        dept_map = {str(d.id): d.name for d in depts}

        sems = self.period_service.list_semesters()
        sem_map = {str(s.id): s.term_name for s in sems}

        rooms = self.room_service.list_rooms() if self.room_service else []
        room_map = {str(r.id): r.name for r in rooms}

        rows = []
        for c in classes:
            rows.append({
                "id": str(c.id),
                "name": c.name,
                "dept_name": dept_map.get(str(c.department_id), "Unknown"),
                "sem_name": sem_map.get(str(c.semester_id), "Unknown"),
                "student_count": c.student_count,
                "room_name": room_map.get(str(c.home_room_id), "None") if c.home_room_id else "None",
            })
        self.table.set_data(rows)

    def _open_add_class_dialog(self) -> None:
        self._show_class_dialog("Add Class Section", None)

    def _open_edit_class_dialog(self, item: Dict[str, Any]) -> None:
        self._show_class_dialog("Edit Class Section", item)

    def _show_class_dialog(self, title: str, class_data: Optional[Dict[str, Any]]) -> None:
        depts = self.inst_service.list_departments()
        sems = self.period_service.list_semesters()
        if not depts or not sems:
            self.banner.show_error("Please configure at least one department and semester first.")
            return

        rooms = self.room_service.list_rooms() if self.room_service else []

        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x400")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        name_f = FormField(form, "Class Name (e.g. S3AD-A)", default_value=class_data.get("name", "") if class_data else "", required=True)
        name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        dept_names = [d.name for d in depts]
        dept_f = FormField(form, "Department", field_type="combobox", options=dept_names, default_value=class_data.get("dept_name", dept_names[0]) if class_data else dept_names[0], required=True)
        dept_f.pack(fill="x", pady=(0, PADDING_SMALL))

        sem_names = [s.term_name for s in sems]
        sem_f = FormField(form, "Semester", field_type="combobox", options=sem_names, default_value=class_data.get("sem_name", sem_names[0]) if class_data else sem_names[0], required=True)
        sem_f.pack(fill="x", pady=(0, PADDING_SMALL))

        count_f = FormField(form, "Student Count", field_type="spinbox", default_value=class_data.get("student_count", 60) if class_data else 60, required=True)
        count_f.pack(fill="x", pady=(0, PADDING_SMALL))

        room_opts = ["None"] + [r.name for r in rooms]
        room_f = FormField(form, "Default Home Room", field_type="combobox", options=room_opts, default_value=class_data.get("room_name", "None") if class_data else "None")
        room_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_cls():
            name = name_f.get_value()
            chosen_dept = next((d for d in depts if d.name == dept_f.get_value()), depts[0])
            chosen_sem = next((s for s in sems if s.term_name == sem_f.get_value()), sems[0])
            count = int(count_f.get_value())
            chosen_room = None
            if room_f.get_value() != "None":
                chosen_room = next((r for r in rooms if r.name == room_f.get_value()), None)

            try:
                if class_data:
                    self.class_service.update_class_group(
                        class_group_id=class_data["id"],
                        name=name,
                        student_count=count,
                        home_room_id=str(chosen_room.id) if chosen_room else None,
                    )
                    self.banner.show_success(f"Class '{name}' updated.")
                else:
                    self.class_service.create_class_group(
                        department_id=str(chosen_dept.id),
                        semester_id=str(chosen_sem.id),
                        name=name,
                        student_count=count,
                        home_room_id=str(chosen_room.id) if chosen_room else None,
                    )
                    self.banner.show_success(f"Class '{name}' created.")
                dlg.destroy()
                self.load_data()
            except ValidationError as ve:
                name_f.show_error(str(ve))
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_cls, width=80)
        save_btn.pack(side="right")

    def _open_add_batch_dialog(self) -> None:
        classes = self.class_service.list_class_groups()
        if not classes:
            self.banner.show_error("Please create a class section first before creating lab batches.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Add Lab Batch")
        dlg.geometry("380x280")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        class_names = [c.name for c in classes]
        cls_f = FormField(form, "Parent Class Section", field_type="combobox", options=class_names, default_value=class_names[0], required=True)
        cls_f.pack(fill="x", pady=(0, PADDING_SMALL))

        batch_name_f = FormField(form, "Batch Name (e.g. Batch A1)", required=True)
        batch_name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        count_f = FormField(form, "Batch Student Count", field_type="spinbox", default_value=30, required=True)
        count_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_batch():
            chosen_cls = next((c for c in classes if c.name == cls_f.get_value()), classes[0])
            b_name = batch_name_f.get_value()
            b_count = int(count_f.get_value())
            try:
                self.class_service.create_student_group(str(chosen_cls.id), b_name, b_count)
                self.banner.show_success(f"Lab batch '{b_name}' created under {chosen_cls.name}.")
                dlg.destroy()
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_batch, width=80)
        save_btn.pack(side="right")

    def _confirm_delete_class(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Delete Class Section",
            message=f"Are you sure you want to delete class section '{item.get('name')}'?",
            on_confirm=lambda: self._delete_class(item["id"]),
            is_destructive=True,
        )

    def _delete_class(self, class_id: str) -> None:
        try:
            self.class_service.delete_class_group(class_id)
            self.banner.show_success("Class section deleted.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot delete class section: {e}")
