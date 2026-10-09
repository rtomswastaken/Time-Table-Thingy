"""Reusable Weekly Timetable Grid Component.

Renders configurable working days, time slots, session cards, break periods,
and empty slot targets using CustomTkinter.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Dict, Optional, Tuple
import customtkinter as ctk

from gui.timetable.session_card import SessionCard
from gui.timetable.timetable_views import (
    GridCellViewModel,
    SessionCardViewModel,
    TimetableGridViewModel,
)


class TimetableGrid(ctk.CTkScrollableFrame):
    """Reusable CustomTkinter weekly timetable grid widget."""

    def __init__(
        self,
        master: Any,
        on_session_selected: Optional[Callable[[SessionCardViewModel], None]] = None,
        on_empty_slot_clicked: Optional[Callable[[int, int], None]] = None,
        on_session_double_click: Optional[Callable[[SessionCardViewModel], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_session_selected = on_session_selected
        self.on_empty_slot_clicked = on_empty_slot_clicked
        self.on_session_double_click = on_session_double_click

        self.selected_session_id: Optional[str] = None
        self.selected_empty_slot: Optional[Tuple[int, int]] = None
        self.current_model: Optional[TimetableGridViewModel] = None

    def render_grid(
        self,
        model: TimetableGridViewModel,
        selected_session_id: Optional[str] = None,
        selected_empty_slot: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Populates the weekly grid from the provided TimetableGridViewModel."""
        self.current_model = model
        self.selected_session_id = selected_session_id
        self.selected_empty_slot = selected_empty_slot

        # Clear existing widgets in grid
        for child in self.winfo_children():
            child.destroy()

        days = model.days
        day_names = model.day_names
        periods = model.periods
        period_labels = model.period_labels
        cells = model.cells

        # Configure columns: Column 0 is Time/Period, Columns 1..N are Days
        self.grid_columnconfigure(0, weight=0, minsize=110)
        for col_idx in range(len(days)):
            self.grid_columnconfigure(col_idx + 1, weight=1, minsize=150)

        # 1. Render Header Row (Top Left Corner + Day Labels)
        corner_lbl = ctk.CTkLabel(
            self,
            text="Time / Period",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("gray85", "gray20"),
            corner_radius=4,
            height=36,
        )
        corner_lbl.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        for col_idx, day_name in enumerate(day_names):
            day_hdr = ctk.CTkLabel(
                self,
                text=day_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=("gray85", "gray20"),
                corner_radius=4,
                height=36,
            )
            day_hdr.grid(row=0, column=col_idx + 1, sticky="nsew", padx=2, pady=2)

        # 2. Render Rows (One row per Period)
        for row_idx, (p_idx, p_label) in enumerate(zip(periods, period_labels), start=1):
            is_break_row = p_idx in model.break_periods

            # Period label cell on left
            time_lbl = ctk.CTkLabel(
                self,
                text=p_label,
                font=ctk.CTkFont(size=10, weight="bold" if is_break_row else "normal"),
                fg_color=("gray90", "gray17") if not is_break_row else ("#FEF3C7", "#78350F"),
                text_color=None if not is_break_row else ("#92400E", "#FDE68A"),
                corner_radius=4,
                height=72 if not is_break_row else 36,
            )
            time_lbl.grid(row=row_idx, column=0, sticky="nsew", padx=2, pady=2)

            # Day cells for this period
            for col_idx, d_idx in enumerate(days):
                cell_vm = cells.get((d_idx, p_idx))

                if is_break_row:
                    self._render_break_cell(row_idx, col_idx + 1, cell_vm)
                elif cell_vm and not cell_vm.is_empty:
                    self._render_session_cell(row_idx, col_idx + 1, cell_vm, model.perspective.value)
                else:
                    self._render_empty_cell(row_idx, col_idx + 1, d_idx, p_idx, cell_vm)

    def _render_session_cell(
        self,
        row: int,
        col: int,
        cell_vm: GridCellViewModel,
        perspective: str,
    ) -> None:
        """Renders scheduled session card(s) in a cell."""
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        for session_vm in cell_vm.sessions:
            is_sel = (session_vm.session_id == self.selected_session_id)
            card = SessionCard(
                container,
                view_model=session_vm,
                on_click=self._handle_session_click,
                on_double_click=self._handle_session_double_click,
                is_selected=is_sel,
                perspective=perspective,
            )
            card.pack(fill="both", expand=True, pady=1)

    def _render_empty_cell(
        self,
        row: int,
        col: int,
        day: int,
        period: int,
        cell_vm: Optional[GridCellViewModel],
    ) -> None:
        """Renders a distinctly styled empty slot."""
        is_sel_empty = (self.selected_empty_slot == (day, period))
        is_gap = cell_vm.is_gap if cell_vm else False

        if is_sel_empty:
            border_color = ("#2563EB", "#60A5FA")
            border_width = 2
            bg_color = ("#EFF6FF", "#1E293B")
            text = "🎯 Target Slot"
        elif is_gap:
            border_color = ("#F59E0B", "#D97706")
            border_width = 1
            bg_color = ("#FFFBEB", "#451A03")
            text = "⏳ Idle Gap"
        else:
            border_color = ("gray80", "gray30")
            border_width = 1
            bg_color = ("gray95", "gray13")
            text = "Empty Slot"

        slot_frame = ctk.CTkFrame(
            self,
            fg_color=bg_color,
            border_color=border_color,
            border_width=border_width,
            corner_radius=4,
            height=70,
        )
        slot_frame.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        lbl = ctk.CTkLabel(
            slot_frame,
            text=text,
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color=("gray50", "gray50"),
        )
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        def on_click(e: Any) -> None:
            if self.on_empty_slot_clicked:
                self.on_empty_slot_clicked(day, period)

        slot_frame.bind("<Button-1>", on_click)
        lbl.bind("<Button-1>", on_click)

    def _render_break_cell(
        self,
        row: int,
        col: int,
        cell_vm: Optional[GridCellViewModel],
    ) -> None:
        """Renders designated institutional break cell."""
        break_frame = ctk.CTkFrame(
            self,
            fg_color=("#FEF9C3", "#422006"),
            border_color=("#FDE047", "#713F12"),
            border_width=1,
            corner_radius=4,
            height=34,
        )
        break_frame.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        lbl = ctk.CTkLabel(
            break_frame,
            text="Recess / Break",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=("#854D0E", "#FEF08A"),
        )
        lbl.place(relx=0.5, rely=0.5, anchor="center")

    def _handle_session_click(self, session_vm: SessionCardViewModel) -> None:
        if self.on_session_selected:
            self.on_session_selected(session_vm)

    def _handle_session_double_click(self, session_vm: SessionCardViewModel) -> None:
        if self.on_session_double_click:
            self.on_session_double_click(session_vm)
