"""Workload Configuration CustomTkinter View.

Allows configuring weekly limits, daily limits, consecutive-period limits,
contact hours, per-class limits, or applying reusable institutional profiles.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from core.exceptions import ValidationError
from core.models import Teacher
from workload.models import TeacherWorkloadRuleExtended, WorkloadProfile
from workload.service import WorkloadServiceImpl

logger = logging.getLogger(__name__)


class WorkloadConfigView:
    """CustomTkinter frame for configuring teacher workload limits and profiles."""

    def __init__(
        self,
        parent: any,
        service: WorkloadServiceImpl,
        teachers: Optional[List[Teacher]] = None,
        on_save_callback: Optional[callable] = None,
    ) -> None:
        self.parent = parent
        self.service = service
        self.teachers = teachers or list(service._teachers.values())
        self.on_save_callback = on_save_callback

        self.selected_teacher_id: Optional[str] = (
            self.teachers[0].id if self.teachers else None
        )

        self.entries: Dict[str, any] = {}
        self.profile_dropdown: Optional[any] = None
        self.frame: Optional[any] = None

        if ctk is not None and parent is not None:
            self._build_ui()

    def _build_ui(self) -> None:
        self.frame = ctk.CTkFrame(self.parent)
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Header: Teacher selector & Profile Applicator
        header_frame = ctk.CTkFrame(self.frame)
        header_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            header_frame,
            text="Teacher Workload Limits & Rules",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=10, pady=5)

        teacher_names = [t.name for t in self.teachers] or ["No Teachers"]
        self.teacher_dropdown = ctk.CTkOptionMenu(
            header_frame,
            values=teacher_names,
            command=self._on_teacher_changed,
        )
        self.teacher_dropdown.pack(side="right", padx=10, pady=5)

        # Quick Profile Selection Bar
        profile_frame = ctk.CTkFrame(self.frame)
        profile_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(profile_frame, text="Apply Standard Profile:").pack(side="left", padx=10)

        profiles = self.service.list_profiles()
        profile_names = [p.name for p in profiles]
        self.profile_map = {p.name: p.id for p in profiles}

        self.profile_dropdown = ctk.CTkOptionMenu(
            profile_frame,
            values=profile_names or ["Standard"],
            command=self._on_profile_selected,
        )
        self.profile_dropdown.pack(side="left", padx=5)

        # Main Limits Form Grid
        form_frame = ctk.CTkFrame(self.frame)
        form_frame.pack(fill="both", expand=True, padx=10, pady=10)

        fields = [
            ("min_periods_per_week", "Minimum Weekly Teaching Periods:", "12"),
            ("max_periods_per_week", "Maximum Weekly Teaching Periods:", "20"),
            ("max_periods_per_day", "Maximum Daily Teaching Periods:", "5"),
            ("min_periods_per_day", "Minimum Daily Teaching Periods (if teaching):", "1"),
            ("max_consecutive_periods", "Maximum Consecutive Periods without Break:", "3"),
            ("max_contact_minutes_per_week", "Max Weekly Contact Minutes (e.g. 1200 = 20h):", "1200"),
            ("max_periods_per_class_per_week", "Max Periods per Single Class Weekly:", "6"),
            ("max_periods_per_class_per_day", "Max Periods per Single Class Daily:", "2"),
            ("max_working_days", "Maximum Active Working Days Weekly:", "5"),
        ]

        for idx, (field_id, label_text, default_val) in enumerate(fields):
            row = idx
            ctk.CTkLabel(
                form_frame,
                text=label_text,
                font=ctk.CTkFont(size=13),
            ).grid(row=row, column=0, sticky="w", padx=15, pady=8)

            entry = ctk.CTkEntry(form_frame, width=120)
            entry.insert(0, default_val)
            entry.grid(row=row, column=1, sticky="e", padx=15, pady=8)
            self.entries[field_id] = entry

        # Footer Actions
        footer_frame = ctk.CTkFrame(self.frame)
        footer_frame.pack(fill="x", padx=10, pady=10)

        self.status_label = ctk.CTkLabel(footer_frame, text="")
        self.status_label.pack(side="left", padx=10)

        save_btn = ctk.CTkButton(
            footer_frame,
            text="Save Workload Limits",
            command=self.save_workload_rule,
            fg_color="#2b7a4b",
            hover_color="#1e5836",
        )
        save_btn.pack(side="right", padx=10, pady=5)

        self._load_teacher_rule()

    def _on_teacher_changed(self, selected_name: str) -> None:
        for t in self.teachers:
            if t.name == selected_name:
                self.selected_teacher_id = t.id
                break
        self._load_teacher_rule()

    def _on_profile_selected(self, profile_name: str) -> None:
        pid = self.profile_map.get(profile_name)
        if not pid or not self.selected_teacher_id:
            return
        profile = self.service.get_profile(pid)
        self._populate_fields_from_profile(profile)
        if hasattr(self, "status_label"):
            self.status_label.configure(
                text=f"Loaded values from '{profile.name}' (Click Save to apply).",
                text_color="orange",
            )

    def _populate_fields_from_profile(self, profile: WorkloadProfile) -> None:
        self._set_val("min_periods_per_week", str(profile.min_periods_per_week))
        self._set_val("max_periods_per_week", str(profile.max_periods_per_week))
        self._set_val("max_periods_per_day", str(profile.max_periods_per_day))
        self._set_val("min_periods_per_day", str(profile.min_periods_per_day))
        self._set_val("max_consecutive_periods", str(profile.max_consecutive_periods))
        self._set_val(
            "max_contact_minutes_per_week",
            str(profile.max_contact_minutes_per_week) if profile.max_contact_minutes_per_week else "",
        )
        self._set_val(
            "max_periods_per_class_per_week",
            str(profile.max_periods_per_class_per_week) if profile.max_periods_per_class_per_week else "",
        )
        self._set_val(
            "max_periods_per_class_per_day",
            str(profile.max_periods_per_class_per_day) if profile.max_periods_per_class_per_day else "",
        )
        self._set_val(
            "max_working_days",
            str(profile.max_working_days) if profile.max_working_days else "",
        )

    def _set_val(self, field_id: str, val: str) -> None:
        if field_id in self.entries:
            entry = self.entries[field_id]
            entry.delete(0, "end")
            entry.insert(0, val)

    def _get_int(self, field_id: str, default: int = 0) -> int:
        val = self.entries[field_id].get().strip()
        return int(val) if val.isdigit() else default

    def _get_opt_int(self, field_id: str) -> Optional[int]:
        val = self.entries[field_id].get().strip()
        return int(val) if val.isdigit() else None

    def _load_teacher_rule(self) -> None:
        if not self.selected_teacher_id:
            return
        rule = self.service.get_workload_rule(self.selected_teacher_id)
        self._set_val("min_periods_per_week", str(rule.min_periods_per_week))
        self._set_val("max_periods_per_week", str(rule.max_periods_per_week))
        self._set_val("max_periods_per_day", str(rule.max_periods_per_day))
        self._set_val("min_periods_per_day", str(rule.min_periods_per_day))
        self._set_val("max_consecutive_periods", str(rule.max_consecutive_periods))
        self._set_val(
            "max_contact_minutes_per_week",
            str(rule.max_contact_minutes_per_week) if rule.max_contact_minutes_per_week else "",
        )
        self._set_val(
            "max_periods_per_class_per_week",
            str(rule.max_periods_per_class_per_week) if rule.max_periods_per_class_per_week else "",
        )
        self._set_val(
            "max_periods_per_class_per_day",
            str(rule.max_periods_per_class_per_day) if rule.max_periods_per_class_per_day else "",
        )
        self._set_val(
            "max_working_days",
            str(rule.max_working_days) if rule.max_working_days else "",
        )
        if hasattr(self, "status_label"):
            self.status_label.configure(text="")

    def save_workload_rule(self) -> None:
        if not self.selected_teacher_id:
            return

        try:
            rule = TeacherWorkloadRuleExtended(
                teacher_id=self.selected_teacher_id,
                min_periods_per_week=self._get_int("min_periods_per_week", 0),
                max_periods_per_week=self._get_int("max_periods_per_week", 20),
                max_periods_per_day=self._get_int("max_periods_per_day", 5),
                min_periods_per_day=self._get_int("min_periods_per_day", 0),
                max_consecutive_periods=self._get_int("max_consecutive_periods", 3),
                max_contact_minutes_per_week=self._get_opt_int("max_contact_minutes_per_week"),
                max_periods_per_class_per_week=self._get_opt_int("max_periods_per_class_per_week"),
                max_periods_per_class_per_day=self._get_opt_int("max_periods_per_class_per_day"),
                max_working_days=self._get_opt_int("max_working_days"),
            )
            self.service.set_workload_rule(rule)

            if hasattr(self, "status_label"):
                self.status_label.configure(
                    text="Workload configuration saved successfully!",
                    text_color="green",
                )

            if self.on_save_callback:
                self.on_save_callback(rule)

        except ValidationError as exc:
            if hasattr(self, "status_label"):
                self.status_label.configure(text=f"Error: {exc.message}", text_color="red")
