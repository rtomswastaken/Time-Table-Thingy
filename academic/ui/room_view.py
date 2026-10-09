"""
Classroom, Laboratory, and Resource Management Screen.
Allows administrators to manage rooms, laboratory spaces, capacity, and facility types.
"""

from typing import Any, Dict, Optional
import customtkinter as ctk

from core.exceptions import ValidationError
from core.models import RoomType
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


class RoomView(ctk.CTkFrame):
    """View for managing Classrooms, Laboratories, and Physical Facilities."""

    def __init__(self, master, room_service: RoomService, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.room_service = room_service

        self._build_ui()
        self.load_data()

    def _build_ui(self) -> None:
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.pack(fill="x", padx=PADDING_LARGE, pady=(PADDING_LARGE, PADDING_MEDIUM))

        title = ctk.CTkLabel(title_box, text="Classrooms & Laboratories", font=FONT_TITLE, anchor="w")
        title.pack(side="left")

        add_room_btn = ctk.CTkButton(
            title_box,
            text="+ Add Room / Lab",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            command=self._open_add_room_dialog,
            height=34,
        )
        add_room_btn.pack(side="right")

        self.banner = NotificationBanner(self)
        self.banner.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_SMALL))

        # Search and Filter
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=8, height=48)
        bar.pack(fill="x", padx=PADDING_LARGE, pady=(0, PADDING_MEDIUM))

        search_lbl = ctk.CTkLabel(bar, text="Search:", font=FONT_BODY_BOLD)
        search_lbl.pack(side="left", padx=(PADDING_MEDIUM, PADDING_SMALL))

        self.search_entry = ctk.CTkEntry(bar, placeholder_text="Search code or name...", width=240)
        self.search_entry.pack(side="left", padx=(0, PADDING_MEDIUM))
        self.search_entry.bind("<KeyRelease>", lambda _: self.load_data())

        type_lbl = ctk.CTkLabel(bar, text="Room Type:", font=FONT_BODY_BOLD)
        type_lbl.pack(side="left", padx=(0, PADDING_SMALL))

        type_options = ["All Types"] + [t.value for t in RoomType]
        self.type_filter = ctk.CTkComboBox(bar, values=type_options, command=lambda _: self.load_data())
        self.type_filter.pack(side="left")

        # Table
        columns = [
            ("code", "Room Code", 120),
            ("name", "Facility Name", 240),
            ("room_type", "Type", 160),
            ("capacity", "Capacity", 90),
            ("location", "Building & Floor", 180),
        ]
        self.table = DataTable(
            self,
            columns=columns,
            on_edit=self._open_edit_room_dialog,
            on_delete=self._confirm_delete_room,
            empty_text="No rooms or laboratories configured. Click '+ Add Room / Lab' to create one.",
        )
        self.table.pack(fill="both", expand=True, padx=PADDING_LARGE, pady=(0, PADDING_LARGE))

    def load_data(self) -> None:
        chosen_type = self.type_filter.get()
        room_type = None
        if chosen_type and chosen_type != "All Types":
            room_type = RoomType(chosen_type)

        search_text = self.search_entry.get().strip()
        rooms = self.room_service.list_rooms(room_type=room_type, search=search_text)

        rows = []
        for r in rooms:
            loc = []
            if r.building:
                loc.append(r.building)
            if r.floor is not None:
                loc.append(f"Floor {r.floor}")
            loc_str = ", ".join(loc) if loc else "Main Campus"

            rows.append({
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "room_type": r.room_type.value if hasattr(r.room_type, "value") else str(r.room_type),
                "capacity": r.capacity,
                "location": loc_str,
            })
        self.table.set_data(rows)

    def _open_add_room_dialog(self) -> None:
        self._show_room_dialog("Add Room or Laboratory", None)

    def _open_edit_room_dialog(self, item: Dict[str, Any]) -> None:
        self._show_room_dialog("Edit Room", item)

    def _show_room_dialog(self, title: str, room_data: Optional[Dict[str, Any]]) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x380")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=PADDING_MEDIUM, pady=PADDING_MEDIUM)

        code_f = FormField(form, "Room Code (e.g. LH-101, LAB-CS)", default_value=room_data.get("code", "") if room_data else "", required=True)
        code_f.pack(fill="x", pady=(0, PADDING_SMALL))

        name_f = FormField(form, "Facility Display Name", default_value=room_data.get("name", "") if room_data else "", required=True)
        name_f.pack(fill="x", pady=(0, PADDING_SMALL))

        type_vals = [t.value for t in RoomType]
        type_f = FormField(form, "Room / Facility Type", field_type="combobox", options=type_vals, default_value=room_data.get("room_type", type_vals[0]) if room_data else type_vals[0], required=True)
        type_f.pack(fill="x", pady=(0, PADDING_SMALL))

        cap_val = room_data.get("capacity", 60) if room_data else 60
        cap_f = FormField(form, "Seating Capacity", field_type="spinbox", default_value=cap_val, required=True)
        cap_f.pack(fill="x", pady=(0, PADDING_SMALL))

        bldg_f = FormField(form, "Building (Optional)", default_value="Academic Block")
        bldg_f.pack(fill="x", pady=(0, PADDING_MEDIUM))

        def save_room():
            code = code_f.get_value()
            name = name_f.get_value()
            rtype = RoomType(type_f.get_value())
            cap = int(cap_f.get_value())
            bldg = bldg_f.get_value()

            try:
                if room_data:
                    self.room_service.update_room(
                        room_id=room_data["id"],
                        name=name,
                        code=code,
                        room_type=rtype,
                        capacity=cap,
                        building=bldg,
                    )
                    self.banner.show_success(f"Room '{code}' updated.")
                else:
                    self.room_service.create_room(
                        name=name,
                        code=code,
                        room_type=rtype,
                        capacity=cap,
                        building=bldg,
                    )
                    self.banner.show_success(f"Room '{code}' created.")
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

        save_btn = ctk.CTkButton(btn_row, text="Save", command=save_room, width=80)
        save_btn.pack(side="right")

    def _confirm_delete_room(self, item: Dict[str, Any]) -> None:
        ConfirmDialog(
            master=self,
            title="Delete Room",
            message=f"Are you sure you want to delete room '{item.get('name')}' ({item.get('code')})?",
            on_confirm=lambda: self._delete_room(item["id"]),
            is_destructive=True,
        )

    def _delete_room(self, room_id: str) -> None:
        try:
            self.room_service.delete_room(room_id)
            self.banner.show_success("Room deleted.")
            self.load_data()
        except Exception as e:
            self.banner.show_error(f"Cannot delete room: {e}")
