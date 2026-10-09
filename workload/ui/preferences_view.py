"""Teacher Preferences & Availability CustomTkinter View.

Allows administrators to select a teacher, view and toggle availability grid slots,
set priority-weighted soft preferences (morning, avoid final, minimize gaps),
and persist configurations through WorkloadService.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Tuple

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from core.models import Institution, Teacher
from workload.models import DetailedTeacherPreference, SoftPreferenceType
from workload.service import WorkloadServiceImpl

logger = logging.getLogger(__name__)

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class TeacherPreferencesView:
    """CustomTkinter frame for managing teacher availability and soft preferences."""

    def __init__(
        self,
        parent: any,
        service: WorkloadServiceImpl,
        teachers: Optional[List[Teacher]] = None,
        institution: Optional[Institution] = None,
        on_save_callback: Optional[callable] = None,
    ) -> None:
        self.parent = parent
        self.service = service
        self.teachers = teachers or list(service._teachers.values())
        self.institution = institution or service.institution
        self.on_save_callback = on_save_callback

        self.selected_teacher_id: Optional[str] = (
            self.teachers[0].id if self.teachers else None
        )

        # Slot states: 0 = Available, 1 = Unavailable (Hard), 2 = Preferred (+), 3 = Avoid (-)
        self.slot_states: Dict[Tuple[int, int], int] = {}
        self.slot_buttons: Dict[Tuple[int, int], any] = {}

        # Preference toggles and sliders
        self.pref_vars: Dict[SoftPreferenceType, any] = {}
        self.weight_sliders: Dict[SoftPreferenceType, any] = {}

        self.frame: Optional[any] = None
        if ctk is not None and parent is not None:
            self._build_ui()

    def _build_ui(self) -> None:
        """Constructs the CustomTkinter layout."""
        self.frame = ctk.CTkFrame(self.parent)
        self.frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Header: Teacher selector
        header_frame = ctk.CTkFrame(self.frame)
        header_frame.pack(fill="x", padx=10, pady=10)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="Faculty Availability & Preferences",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(side="left", padx=10, pady=5)

        teacher_names = [t.name for t in self.teachers] or ["No Teachers"]
        self.teacher_dropdown = ctk.CTkOptionMenu(
            header_frame,
            values=teacher_names,
            command=self._on_teacher_changed,
        )
        self.teacher_dropdown.pack(side="right", padx=10, pady=5)

        # Content split: Left is Availability Grid, Right is Soft Preferences
        content_frame = ctk.CTkFrame(self.frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Left Column: Availability Grid
        self.grid_frame = ctk.CTkFrame(content_frame)
        self.grid_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        grid_title = ctk.CTkLabel(
            self.grid_frame,
            text="Weekly Availability Grid (Click to toggle: Available -> Unavailable -> Preferred -> Avoid)",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        grid_title.pack(anchor="w", padx=10, pady=5)

        self.matrix_container = ctk.CTkFrame(self.grid_frame)
        self.matrix_container.pack(fill="both", expand=True, padx=10, pady=5)
        self._build_matrix_buttons()

        # Right Column: Soft Preferences
        self.pref_frame = ctk.CTkFrame(content_frame, width=320)
        self.pref_frame.pack(side="right", fill="y", padx=10, pady=10)

        pref_title = ctk.CTkLabel(
            self.pref_frame,
            text="Soft Optimization Preferences",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        pref_title.pack(anchor="w", padx=10, pady=5)

        self._build_soft_pref_controls()

        # Footer Buttons
        footer_frame = ctk.CTkFrame(self.frame)
        footer_frame.pack(fill="x", padx=10, pady=10)

        self.status_label = ctk.CTkLabel(footer_frame, text="", text_color="green")
        self.status_label.pack(side="left", padx=10)

        save_btn = ctk.CTkButton(
            footer_frame,
            text="Save Configuration",
            command=self.save_configuration,
            fg_color="#2b7a4b",
            hover_color="#1e5836",
        )
        save_btn.pack(side="right", padx=10, pady=5)

        reset_btn = ctk.CTkButton(
            footer_frame,
            text="Reset to Defaults",
            command=self.reset_to_defaults,
            fg_color="#555555",
            hover_color="#333333",
        )
        reset_btn.pack(side="right", padx=10, pady=5)

        self._load_teacher_data()

    def _build_matrix_buttons(self) -> None:
        """Constructs interactive grid buttons."""
        for widget in self.matrix_container.winfo_children():
            widget.destroy()

        self.slot_buttons.clear()

        # Header row: Periods
        ctk.CTkLabel(self.matrix_container, text="Day / Period", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=4, pady=4
        )
        for p in range(self.institution.periods_per_day):
            ctk.CTkLabel(self.matrix_container, text=f"P{p + 1}", font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=p + 1, padx=4, pady=4
            )

        # Rows for working days
        for r_idx, day in enumerate(self.institution.working_days):
            day_name = DAY_NAMES[day] if day < len(DAY_NAMES) else f"Day {day}"
            ctk.CTkLabel(self.matrix_container, text=day_name, font=ctk.CTkFont(weight="bold")).grid(
                row=r_idx + 1, column=0, padx=4, pady=4
            )

            for p in range(self.institution.periods_per_day):
                btn = ctk.CTkButton(
                    self.matrix_container,
                    text="Available",
                    width=70,
                    height=30,
                    fg_color="#2E7D32",  # Green
                    command=lambda d=day, per=p: self._toggle_slot(d, per),
                )
                btn.grid(row=r_idx + 1, column=p + 1, padx=3, pady=3)
                self.slot_buttons[(day, p)] = btn

    def _build_soft_pref_controls(self) -> None:
        """Builds controls for soft preferences."""
        pref_configs = [
            (SoftPreferenceType.PREFER_MORNING, "Prefer morning classes (AM slots)"),
            (SoftPreferenceType.AVOID_FINAL_PERIOD, "Avoid teaching final period of day"),
            (SoftPreferenceType.MINIMIZE_GAPS, "Minimize idle gaps between sessions"),
            (SoftPreferenceType.MINIMIZE_WORKING_DAYS, "Compact days (fewer working days)"),
            (SoftPreferenceType.AVOID_SINGLE_SESSIONS, "Avoid days with only 1 session"),
        ]

        for ptype, label_text in pref_configs:
            box_frame = ctk.CTkFrame(self.pref_frame)
            box_frame.pack(fill="x", padx=5, pady=6)

            cb_var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(box_frame, text=label_text, variable=cb_var)
            cb.pack(anchor="w", padx=5, pady=2)
            self.pref_vars[ptype] = cb_var

            slider_frame = ctk.CTkFrame(box_frame, fg_color="transparent")
            slider_frame.pack(fill="x", padx=5, pady=2)
            ctk.CTkLabel(slider_frame, text="Weight (1-10):", font=ctk.CTkFont(size=11)).pack(
                side="left", padx=2
            )

            slider = ctk.CTkSlider(slider_frame, from_=1, to=10, number_of_steps=9)
            slider.set(5)
            slider.pack(side="right", fill="x", expand=True, padx=5)
            self.weight_sliders[ptype] = slider

    def _on_teacher_changed(self, selected_name: str) -> None:
        for t in self.teachers:
            if t.name == selected_name:
                self.selected_teacher_id = t.id
                break
        self._load_teacher_data()

    def _toggle_slot(self, day: int, period: int) -> None:
        """Cycles slot state: 0 (Available) -> 1 (Unavailable) -> 2 (Preferred) -> 3 (Avoid) -> 0."""
        current = self.slot_states.get((day, period), 0)
        new_state = (current + 1) % 4
        self.slot_states[(day, period)] = new_state
        self._update_slot_button_display(day, period, new_state)

    def _update_slot_button_display(self, day: int, period: int, state: int) -> None:
        btn = self.slot_buttons.get((day, period))
        if not btn:
            return

        if state == 0:
            btn.configure(text="Available", fg_color="#2E7D32")  # Green
        elif state == 1:
            btn.configure(text="Unavailable", fg_color="#C62828")  # Red (Hard restriction)
        elif state == 2:
            btn.configure(text="Preferred", fg_color="#1565C0")  # Blue (Soft prefer)
        elif state == 3:
            btn.configure(text="Avoid", fg_color="#E65100")  # Orange (Soft avoid)

    def _load_teacher_data(self) -> None:
        """Populates UI with selected teacher's saved availability and preferences."""
        if not self.selected_teacher_id:
            return

        tid = self.selected_teacher_id
        unavailable = self.service.get_availability(tid)
        slot_weights = self.service.get_preferences(tid)

        self.slot_states.clear()
        for day in self.institution.working_days:
            for p in range(self.institution.periods_per_day):
                key = (day, p)
                if key in unavailable:
                    state = 1  # Unavailable
                else:
                    weight = slot_weights.get(key, 0)
                    if weight > 0:
                        state = 2  # Preferred
                    elif weight < 0:
                        state = 3  # Avoid
                    else:
                        state = 0  # Available
                self.slot_states[key] = state
                self._update_slot_button_display(day, p, state)

        # Load soft preferences
        soft_prefs = self.service.get_soft_preferences(tid)
        pref_map = {p.preference_type: p for p in soft_prefs}

        for ptype, var in self.pref_vars.items():
            if ptype in pref_map and pref_map[ptype].is_active:
                var.set(True)
                if ptype in self.weight_sliders:
                    self.weight_sliders[ptype].set(pref_map[ptype].weight)
            else:
                var.set(False)

        if hasattr(self, "status_label"):
            self.status_label.configure(text="")

    def save_configuration(self) -> None:
        """Saves current UI selections to the WorkloadService."""
        if not self.selected_teacher_id:
            return

        tid = self.selected_teacher_id

        # 1. Save unavailable slots
        unavailable: Set[Tuple[int, int]] = set()
        slot_weights: Dict[Tuple[int, int], int] = {}

        for (day, p), state in self.slot_states.items():
            if state == 1:
                unavailable.add((day, p))
            elif state == 2:
                slot_weights[(day, p)] = 5  # Preferred
            elif state == 3:
                slot_weights[(day, p)] = -5  # Avoid

        self.service.set_availability(tid, unavailable)
        self.service.set_preferences(tid, slot_weights)

        # 2. Save soft preferences
        new_prefs: List[DetailedTeacherPreference] = []
        for ptype, var in self.pref_vars.items():
            if var.get():
                slider_val = int(self.weight_sliders[ptype].get())
                new_prefs.append(
                    DetailedTeacherPreference(
                        teacher_id=tid,
                        preference_type=ptype,
                        weight=slider_val,
                        is_active=True,
                    )
                )

        self.service.set_soft_preferences(tid, new_prefs)

        if hasattr(self, "status_label"):
            self.status_label.configure(
                text="Preferences & Availability saved successfully!",
                text_color="green",
            )

        if self.on_save_callback:
            self.on_save_callback(tid)

    def reset_to_defaults(self) -> None:
        """Resets all slots to Available and disables soft preferences."""
        for (day, p) in self.slot_states:
            self.slot_states[(day, p)] = 0
            self._update_slot_button_display(day, p, 0)

        for var in self.pref_vars.values():
            var.set(False)

        if hasattr(self, "status_label"):
            self.status_label.configure(
                text="Reset to default available schedule (unsaved).",
                text_color="orange",
            )
