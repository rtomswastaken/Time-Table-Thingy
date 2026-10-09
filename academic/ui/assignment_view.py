"""
Subject Offering and Class Assignment Management Screen.
Allows administrators to configure curricular delivery requirements, session structures,
and assign qualified teachers to class cohorts.
"""

from typing import Any, Dict, List, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from core.models import RoomType, SessionType
from academic.class_service import ClassService
from academic.period_service import AcademicPeriodService
from academic.subject_service import SubjectService
from academic.teacher_service import TeacherService
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


class AssignmentView(ctk.CTkFrame):
    """View for managing Subject Offerings and Class-Subject-Teacher Assignments."""

    def __init__(
        self,
        master,
        subject_service: SubjectService,
        class_service: ClassService,
        teacher_service: TeacherService,
        period_service: AcademicPeriodService,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.subject_service = subject_service
        self.class_service = class_service
        self.teacher_service = teacher_service
        self.period_service = period_service

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Offerings & Teaching Assignments", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        add_assign_btn = ctk.CTkButton(
            title_box,
            text="+ Add Class Assignment",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_assignment_dialog,
            height=34,
        )
        add_assign_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Class Selector Bar
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8, height=48)
        bar.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        cls_lbl = ctk.CTkLabel(bar, text="Select Class Cohort:", font=FONT_BODY_BOLD)
        cls_lbl.pack(side="left", padx=(PADDING_MEDIUM, PADDING_SMALL))

        self.class_filter = ctk.CTkComboBox(bar, values=["All Classes"], command=lambda _: self.load_data(), width=220)
        self.class_filter.pack(side="left")

        # Table
        columns = [
            ("class_name", "Class Cohort", 140),
            ("subject_name", "Subject", 240),
            ("primary_teacher", "Primary Faculty", 180),
            ("secondary_teacher", "Co-Faculty", 140),
            ("batch_name", "Batch Scope", 120),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_delete=self._confirm_delete_assignment,
            empty_text="No subject assignments configured for this class cohort.",
        )
        self.table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_LARGE))

    def load_data(self) -> None:
        classes = self.class_service.list_class_groups()
        class_names = ["All Classes"] + [c.name for c in classes]
        self.class_filter.configure(values=class_names)

        chosen_cls = self.class_filter.get()
        class_id = None
        if chosen_cls and chosen_cls != "All Classes":
            matched = next((c for c in classes if c.name == chosen_cls), None)
            if matched:
                class_id = str(matched.id)

        assignments = self.subject_service.list_class_assignments(class_group_id=class_id)
        class_map = {str(c.id): c.name for c in classes}

        subjects = self.subject_service.list_subjects()
        subject_map = {str(s.id): f"{s.code} - {s.name}" for s in subjects}

        teachers = self.teacher_service.list_teachers()
        teacher_map = {str(t.id): t.name for t in teachers}

        rows = []
        for a in assignments:
            offering = self.subject_service.get_offering(str(a.offering_id))
            subj_title = "Unknown"
            if offering:
                subj_title = subject_map.get(str(offering.subject_id), "Unknown")

            rows.append({
                "id": str(a.id),
                "class_name": class_map.get(str(a.class_group_id), "Unknown"),
                "subject_name": subj_title,
                "primary_teacher": teacher_map.get(str(a.primary_teacher_id), "Unassigned"),
                "secondary_teacher": teacher_map.get(str(a.secondary_teacher_id), "-") if a.secondary_teacher_id else "-",
                "batch_name": a.student_group_id or "Entire Class",
            })
        self.table.set_data(rows)

    def _open_add_assignment_dialog(self) -> None:
        classes = self.class_service.list_class_groups()
        subjects = self.subject_service.list_subjects()
        teachers = self.teacher_service.list_teachers()
        sems = self.period_service.list_semesters()

        if not classes or not subjects or not teachers or not sems:
            self.banner.show_error("Please configure classes, subjects, faculty, and semesters first.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Add Class-Subject Teaching Assignment")
        dlg.geometry("450x480")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        class_names = [c.name for c in classes]
        cls_f = FormField(form, "Target Class Section", field_type="combobox", options=class_names, default_value=class_names[0], required=True)
        cls_f.pack(fill="x", pady=(0, PADDING_SMALL))

        subject_names = [f"{s.code} - {s.name}" for s in subjects]
        subj_f = FormField(form, "Subject", field_type="combobox", options=subject_names, default_value=subject_names[0], required=True)
        subj_f.pack(fill="x", pady=(0, PADDING_SMALL))

        teacher_names = [f"{t.name} ({t.employee_id})" for t in teachers]
        t1_f = FormField(form, "Primary Faculty", field_type="combobox", options=teacher_names, default_value=teacher_names[0], required=True)
        t1_f.pack(fill="x", pady=(0, PADDING_SMALL))

        t2_opts = ["None"] + teacher_names
        t2_f = FormField(form, "Co-Faculty (Optional / Co-Taught Labs)", field_type="combobox", options=t2_opts, default_value="None")
        t2_f.pack(fill="x", pady=(0, PADDING_SMALL))

        periods_f = FormField(form, "Weekly Teaching Periods (Periods/Week)", field_type="spinbox", default_value=4, required=True)
        periods_f.pack(fill="x", pady=(0, PADDING_SMALL))

        contact_hrs_f = FormField(form, "Weekly Contact Hours (Hours/Week)", field_type="spinbox", default_value="4.0", required=True)
        contact_hrs_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_assignment():
            chosen_cls = next((c for c in classes if c.name == cls_f.get_value()), classes[0])
            chosen_subj = subjects[subject_names.index(subj_f.get_value())]
            chosen_t1 = teachers[teacher_names.index(t1_f.get_value())]

            chosen_t2 = None
            if t2_f.get_value() != "None":
                chosen_t2 = teachers[teacher_names.index(t2_f.get_value())]

            periods = int(periods_f.get_value())
            contact_hrs = float(contact_hrs_f.get_value())

            try:
                # 1. Create or retrieve subject offering in class's semester
                offering = self.subject_service.create_offering(
                    subject_id=str(chosen_subj.id),
                    semester_id=str(chosen_cls.semester_id),
                    weekly_contact_hours=contact_hrs,
                    weekly_periods=periods,
                )

                # 2. Add default session requirement (1 period x periods times per week)
                self.subject_service.add_session_requirement(
                    offering_id=str(offering.id),
                    session_type=SessionType.THEORY,
                    consecutive_periods=1,
                    frequency_per_week=periods,
                )

                # 3. Assign offering to class group
                self.subject_service.assign_subject_to_class(
                    class_group_id=str(chosen_cls.id),
                    offering_id=str(offering.id),
                    primary_teacher_id=str(chosen_t1.id),
                    secondary_teacher_id=str(chosen_t2.id) if chosen_t2 else None,
                )

                self.banner.show_success(f"Assigned '{chosen_subj.code}' to class '{chosen_cls.name}'.")
                dlg.destroy()
                self.load_data()
            except Exception as ex:
                self.banner.show_error(str(ex))

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(btn_row, text="Cancel", fg_color="transparent", border_width=1, command=dlg.destroy, width=80)
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        save_btn = ctk.CTkButton(btn_row, text="Save Assignment", command=save_assignment, width=120)
        save_btn.pack(side="right")

    def _confirm_delete_assignment(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Delete Teaching Assignment",
            message=f"Are you sure you want to remove assignment for '{item.get('subject_name')}' from '{item.get('class_name')}'?",
            on_confirm=lambda: self._delete_assignment(item["id"]),
            is_destructive=True,
        )

    def _delete_assignment(self, assignment_id: str) -> None:
        try:
            self.subject_service.delete_class_assignment(assignment_id)
            self.banner.show_success("Teaching assignment removed.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot delete assignment: {e}")
