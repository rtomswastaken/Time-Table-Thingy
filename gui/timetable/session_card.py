"""CustomTkinter Session Card Component.

Displays scheduled session information with visual differentiation of session types,
lock indicators, conflict alerts, and interactive selection.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional
import customtkinter as ctk

from gui.timetable.timetable_views import SessionCardViewModel


class SessionCard(ctk.CTkFrame):
    """Reusable CustomTkinter widget for an individual scheduled session in the grid."""

    # Distinctive visual palette for session types (both light and dark theme compatible)
    TYPE_COLORS = {
        "THEORY": {"bg": ("#E0F2FE", "#0C4A6E"), "border": ("#0284C7", "#38BDF8"), "text": ("#0369A1", "#BAE6FD")},
        "LABORATORY": {"bg": ("#FEF3C7", "#78350F"), "border": ("#D97706", "#FBBF24"), "text": ("#B45309", "#FDE68A")},
        "PRACTICAL": {"bg": ("#DCFCE7", "#14532D"), "border": ("#16A34A", "#4ADE80"), "text": ("#15803D", "#BBF7D0")},
        "TUTORIAL": {"bg": ("#F3E8FF", "#581C87"), "border": ("#9333EA", "#C084FC"), "text": ("#7E22CE", "#E9D5FF")},
        "SEMINAR": {"bg": ("#FCE7F3", "#831843"), "border": ("#DB2777", "#F472B6"), "text": ("#BE185D", "#FBCFE8")},
        "PROJECT": {"bg": ("#FFEDD5", "#7C2D12"), "border": ("#EA580C", "#FB923C"), "text": ("#C2410C", "#FED7AA")},
    }

    def __init__(
        self,
        master: Any,
        view_model: SessionCardViewModel,
        on_click: Optional[Callable[[SessionCardViewModel], None]] = None,
        on_double_click: Optional[Callable[[SessionCardViewModel], None]] = None,
        is_selected: bool = False,
        perspective: str = "CLASS",
        **kwargs: Any,
    ) -> None:
        self.view_model = view_model
        self.on_click = on_click
        self.on_double_click = on_double_click
        self.is_selected = is_selected
        self.perspective = perspective

        # Determine color scheme
        s_type = view_model.session_type.upper()
        colors = self.TYPE_COLORS.get(s_type, self.TYPE_COLORS["THEORY"])

        if view_model.has_conflict:
            border_color = ("#DC2626", "#EF4444")
            border_width = 2
        elif is_selected:
            border_color = ("#2563EB", "#60A5FA")
            border_width = 3
        elif view_model.is_locked:
            border_color = ("#475569", "#94A3B8")
            border_width = 2
        else:
            border_color = colors["border"]
            border_width = 1

        bg_color = colors["bg"]

        super().__init__(
            master,
            fg_color=bg_color,
            border_color=border_color,
            border_width=border_width,
            corner_radius=6,
            **kwargs,
        )

        self._build_card_ui(colors)
        self._bind_events()

    def _build_card_ui(self, colors: dict) -> None:
        vm = self.view_model

        # Top Header: Badge, Lock icon, Conflict icon
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=4, pady=(3, 1))

        # Badge pill
        badge_text = f"[{vm.session_type_badge}]"
        if vm.duration_periods > 1:
            if vm.is_continuation:
                badge_text = f"[{vm.session_type_badge} Cont.]"
            else:
                badge_text = f"[{vm.session_type_badge} {vm.duration_periods}P]"

        badge_lbl = ctk.CTkLabel(
            header_frame,
            text=badge_text,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=colors["text"],
        )
        badge_lbl.pack(side="left")

        # Icons on right
        if vm.has_conflict:
            conf_lbl = ctk.CTkLabel(
                header_frame,
                text="⚠️ CONFLICT",
                font=ctk.CTkFont(size=8, weight="bold"),
                text_color=("#DC2626", "#EF4444"),
            )
            conf_lbl.pack(side="right", padx=1)

        if vm.is_locked:
            lock_lbl = ctk.CTkLabel(
                header_frame,
                text="🔒",
                font=ctk.CTkFont(size=9),
            )
            lock_lbl.pack(side="right", padx=1)

        # Subject Code & Name
        subj_lbl = ctk.CTkLabel(
            self,
            text=f"{vm.subject_code} - {vm.subject_name}",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
            wraplength=130,
        )
        subj_lbl.pack(fill="x", padx=5, pady=1)

        # Teacher & Room row
        details_frame = ctk.CTkFrame(self, fg_color="transparent")
        details_frame.pack(fill="x", padx=5, pady=(0, 3))

        # In Teacher view, show Class instead of Teacher; In Room view, show Class instead of Room
        if self.perspective == "TEACHER":
            primary_detail = f"👥 {vm.class_name}"
            sec_detail = f"📍 {vm.room_code}"
        elif self.perspective == "ROOM":
            primary_detail = f"👥 {vm.class_name}"
            sec_detail = f"👤 {vm.teacher_name}"
        else:
            primary_detail = f"👤 {vm.teacher_name}"
            sec_detail = f"📍 {vm.room_code}"

        primary_lbl = ctk.CTkLabel(
            details_frame,
            text=primary_detail,
            font=ctk.CTkFont(size=10),
            anchor="w",
            wraplength=130,
        )
        primary_lbl.pack(fill="x")

        sec_lbl = ctk.CTkLabel(
            details_frame,
            text=sec_detail,
            font=ctk.CTkFont(size=9),
            text_color=("gray30", "gray70"),
            anchor="w",
        )
        sec_lbl.pack(fill="x")

    def _bind_events(self) -> None:
        """Binds click and hover events recursively across all child labels."""
        def handle_click(event: Any) -> None:
            if self.on_click:
                self.on_click(self.view_model)

        def handle_double_click(event: Any) -> None:
            if self.on_double_click:
                self.on_double_click(self.view_model)

        self.bind("<Button-1>", handle_click)
        self.bind("<Double-Button-1>", handle_double_click)

        for child in self.winfo_children():
            child.bind("<Button-1>", handle_click)
            child.bind("<Double-Button-1>", handle_double_click)
            for sub in child.winfo_children():
                sub.bind("<Button-1>", handle_click)
                sub.bind("<Double-Button-1>", handle_double_click)
