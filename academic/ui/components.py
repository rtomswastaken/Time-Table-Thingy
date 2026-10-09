"""
Reusable CustomTkinter components for academic management screens.
Includes DataTable, FormField, ModalDialog, ConfirmDialog, and NotificationBanner.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import customtkinter as ctk

from academic.ui.theme import (
    COLOR_BG_CARD,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    CORNER_RADIUS_BUTTON,
    CORNER_RADIUS_CARD,
    CORNER_RADIUS_INPUT,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_CAPTION,
    FONT_ERROR,
    FONT_SECTION,
    FONT_SUBTITLE,
    PADDING_MEDIUM,
    PADDING_SMALL,
)


class NotificationBanner(ctk.CTkFrame):
    """Temporary alert banner showing success, warning, or error messages."""

    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=CORNER_RADIUS_CARD, fg_color="transparent", **kwargs)
        self.label = ctk.CTkLabel(
            self,
            text="",
            font=FONT_BODY,
            corner_radius=CORNER_RADIUS_CARD,
            padx=PADDING_MEDIUM,
            pady=PADDING_SMALL,
        )
        self.label.pack(fill="x", expand=True)
        self.pack_forget()

    def show_success(self, message: str, timeout_ms: int = 4000) -> None:
        self._display(message, ("#DCFCE7", "#14532D"), ("#15803D", "#86EFAC"), timeout_ms)

    def show_error(self, message: str, timeout_ms: int = 6000) -> None:
        self._display(message, ("#FEE2E2", "#7F1D1D"), ("#B91C1C", "#FCA5A5"), timeout_ms)

    def show_info(self, message: str, timeout_ms: int = 4000) -> None:
        self._display(message, ("#DBEAFE", "#1E3A8A"), ("#1D4ED8", "#93C5FD"), timeout_ms)

    def _display(self, message: str, bg_color: Any, text_color: Any, timeout_ms: int) -> None:
        self.label.configure(text=message, fg_color=bg_color, text_color=text_color)
        self.pack(fill="x", padx=PADDING_MEDIUM, pady=(0, PADDING_SMALL))
        if timeout_ms > 0:
            self.after(timeout_ms, self.hide)

    def hide(self) -> None:
        self.pack_forget()


class FormField(ctk.CTkFrame):
    """Labeled input field with inline validation error display."""

    def __init__(
        self,
        master,
        label_text: str,
        field_type: str = "entry",
        options: Optional[List[str]] = None,
        default_value: Any = "",
        required: bool = False,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.required = required

        label_suffix = " *" if required else ""
        self.label = ctk.CTkLabel(
            self,
            text=f"{label_text}{label_suffix}",
            font=FONT_BODY_BOLD,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.label.pack(fill="x", pady=(0, 2))

        self.field_type = field_type
        if field_type == "entry":
            self.input = ctk.CTkEntry(
                self,
                corner_radius=CORNER_RADIUS_INPUT,
                font=FONT_BODY,
                height=34,
            )
            if default_value:
                self.input.insert(0, str(default_value))
            self.input.pack(fill="x")
        elif field_type == "combobox":
            self.input = ctk.CTkComboBox(
                self,
                values=options or [],
                corner_radius=CORNER_RADIUS_INPUT,
                font=FONT_BODY,
                height=34,
                state="readonly" if options else "normal",
            )
            if default_value:
                self.input.set(str(default_value))
            self.input.pack(fill="x")
        elif field_type == "checkbox":
            self.var = ctk.BooleanVar(value=bool(default_value))
            self.input = ctk.CTkCheckBox(
                self,
                text="",
                variable=self.var,
                corner_radius=4,
                height=24,
            )
            self.input.pack(anchor="w")
        elif field_type == "spinbox":
            self.input = ctk.CTkEntry(
                self,
                corner_radius=CORNER_RADIUS_INPUT,
                font=FONT_BODY,
                height=34,
            )
            self.input.insert(0, str(default_value if default_value != "" else 0))
            self.input.pack(fill="x")

        # Inline error label
        self.error_label = ctk.CTkLabel(
            self,
            text="",
            font=FONT_ERROR,
            text_color=COLOR_DANGER,
            anchor="w",
        )

    def get_value(self) -> Any:
        if self.field_type == "checkbox":
            return self.var.get()
        return self.input.get()

    def set_value(self, value: Any) -> None:
        if self.field_type == "checkbox":
            self.var.set(bool(value))
        elif self.field_type == "combobox":
            self.input.set(str(value))
        else:
            self.input.delete(0, "end")
            self.input.insert(0, str(value))

    def set_options(self, options: List[str]) -> None:
        if self.field_type == "combobox":
            self.input.configure(values=options)
            if options and not self.input.get():
                self.input.set(options[0])

    def show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.error_label.pack(fill="x", pady=(2, 0))

    def clear_error(self) -> None:
        self.error_label.configure(text="")
        self.error_label.pack_forget()


class ConfirmDialog(ctk.CTkToplevel):
    """Modal dialog asking user to confirm an action."""

    def __init__(
        self,
        master,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        confirm_text: str = "Confirm",
        is_destructive: bool = False,
    ):
        super().__init__(master)
        self.title(title)
        self.geometry("380x180")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.on_confirm = on_confirm

        # Content frame
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        title_lbl = ctk.CTkLabel(content_frame, text=title, font=FONT_SUBTITLE, anchor="w")
        title_lbl.pack(fill="x", pady=(0, PADDING_SMALL))

        msg_lbl = ctk.CTkLabel(
            content_frame,
            text=message,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
            justify="left",
            wraplength=340,
        )
        msg_lbl.pack(fill="x", pady=(0, PADDING_MEDIUM))

        btn_row = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            font=FONT_BODY,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.destroy,
            width=90,
            height=32,
        )
        cancel_btn.pack(side="right", padx=(PADDING_SMALL, 0))

        confirm_btn = ctk.CTkButton(
            btn_row,
            text=confirm_text,
            font=FONT_BODY_BOLD,
            fg_color=COLOR_DANGER if is_destructive else COLOR_PRIMARY,
            hover_color=COLOR_DANGER_HOVER if is_destructive else COLOR_PRIMARY_HOVER,
            command=self._do_confirm,
            width=90,
            height=32,
        )
        confirm_btn.pack(side="right")

    def _do_confirm(self) -> None:
        self.destroy()
        self.on_confirm()


class DataTable(ctk.CTkFrame):
    """
    Scrollable tabular data view with headers, rows, action buttons, and empty-state support.
    """

    def __init__(
        self,
        master,
        columns: List[Tuple[str, str, int]],  # (column_key, column_label, width)
        on_edit: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_delete: Optional[Callable[[Dict[str, Any]], None]] = None,
        empty_text: str = "No records found.",
        **kwargs,
    ):
        super().__init__(master, fg_color=COLOR_BG_CARD, corner_radius=CORNER_RADIUS_CARD, **kwargs)
        self.columns = columns
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.empty_text = empty_text
        self.items: List[Dict[str, Any]] = []

        # Header Row
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=36)
        self.header_frame.pack(fill="x", padx=PADDING_MEDIUM, pady=(PADDING_SMALL, 0))

        for col_key, col_label, col_width in columns:
            lbl = ctk.CTkLabel(
                self.header_frame,
                text=col_label,
                font=FONT_BODY_BOLD,
                text_color=COLOR_TEXT_SECONDARY,
                width=col_width,
                anchor="w",
            )
            lbl.pack(side="left", padx=4)

        if on_edit or on_delete:
            actions_lbl = ctk.CTkLabel(
                self.header_frame,
                text="Actions",
                font=FONT_BODY_BOLD,
                text_color=COLOR_TEXT_SECONDARY,
                width=110,
                anchor="e",
            )
            actions_lbl.pack(side="right", padx=4)

        # Divider
        divider = ctk.CTkFrame(self, height=1, fg_color=COLOR_BORDER)
        divider.pack(fill="x", padx=PADDING_MEDIUM, pady=4)

        # Scrollable rows frame
        self.rows_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.rows_frame.pack(fill="both", expand=True, padx=PADDING_SMALL, pady=(0, PADDING_SMALL))

        # Empty state label
        self.empty_label = ctk.CTkLabel(
            self.rows_frame,
            text=empty_text,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            pady=PADDING_MEDIUM,
        )

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        self.items = data
        for widget in self.rows_frame.winfo_children():
            widget.destroy()

        if not data:
            self.empty_label = ctk.CTkLabel(
                self.rows_frame,
                text=self.empty_text,
                font=FONT_BODY,
                text_color=COLOR_TEXT_SECONDARY,
                pady=PADDING_MEDIUM,
            )
            self.empty_label.pack(fill="both", expand=True, pady=PADDING_MEDIUM)
            return

        for index, item in enumerate(data):
            row = ctk.CTkFrame(self.rows_frame, fg_color="transparent", height=38)
            row.pack(fill="x", pady=2)

            for col_key, col_label, col_width in self.columns:
                val = str(item.get(col_key, ""))
                val_lbl = ctk.CTkLabel(
                    row,
                    text=val,
                    font=FONT_BODY,
                    text_color=COLOR_TEXT_PRIMARY,
                    width=col_width,
                    anchor="w",
                )
                val_lbl.pack(side="left", padx=4)

            # Actions
            if self.on_edit or self.on_delete:
                actions_box = ctk.CTkFrame(row, fg_color="transparent", width=110)
                actions_box.pack(side="right", padx=4)

                if self.on_delete:
                    del_btn = ctk.CTkButton(
                        actions_box,
                        text="Delete",
                        font=FONT_CAPTION,
                        fg_color=COLOR_DANGER,
                        hover_color=COLOR_DANGER_HOVER,
                        width=50,
                        height=26,
                        command=lambda it=item: self.on_delete(it),
                    )
                    del_btn.pack(side="right", padx=(2, 0))

                if self.on_edit:
                    edit_btn = ctk.CTkButton(
                        actions_box,
                        text="Edit",
                        font=FONT_CAPTION,
                        fg_color=COLOR_PRIMARY,
                        hover_color=COLOR_PRIMARY_HOVER,
                        width=46,
                        height=26,
                        command=lambda it=item: self.on_edit(it),
                    )
                    edit_btn.pack(side="right", padx=(0, 2))
