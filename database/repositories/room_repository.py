"""
Repository for Room and RoomAvailability entities.
Implements core.interfaces.Repository[Room].
"""

from typing import Any, Dict, List, Optional
from core.models import Room, RoomAvailability, RoomType
from .base import BaseRepository


class RoomRepository(BaseRepository):
    """Persistence operations for physical spaces and equipment."""

    # --- Room Operations (Repository[Room]) ---

    def get_by_id(self, entity_id: str) -> Optional[Room]:
        sql = "SELECT id, name, code, room_type, capacity, building, floor FROM rooms WHERE id = ?;"
        row = self.fetchone(sql, (str(entity_id),))
        if not row:
            return None
        return self._row_to_room(row)

    def get_by_code(self, code: str) -> Optional[Room]:
        sql = "SELECT id, name, code, room_type, capacity, building, floor FROM rooms WHERE code = ?;"
        row = self.fetchone(sql, (code,))
        if not row:
            return None
        return self._row_to_room(row)

    def list_all(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Room]:
        sql = "SELECT id, name, code, room_type, capacity, building, floor FROM rooms"
        params = []
        if filter_params and "room_type" in filter_params:
            sql += " WHERE room_type = ?"
            rtype = filter_params["room_type"]
            params.append(rtype.value if isinstance(rtype, RoomType) else str(rtype))
        sql += " ORDER BY code ASC;"

        rows = self.fetchall(sql, tuple(params))
        return [self._row_to_room(r) for r in rows]

    def list_by_type(self, room_type: RoomType) -> List[Room]:
        return self.list_all({"room_type": room_type})

    def save(self, entity: Room) -> Room:
        existing = self.get_by_id(str(entity.id))
        rtype_val = entity.room_type.value if isinstance(entity.room_type, RoomType) else str(entity.room_type)
        if existing is None:
            sql = """
                INSERT INTO rooms (id, name, code, room_type, capacity, building, floor)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """
            self.execute(
                sql,
                (str(entity.id), entity.name, entity.code, rtype_val, entity.capacity, entity.building, entity.floor),
            )
        else:
            sql = """
                UPDATE rooms
                SET name = ?, code = ?, room_type = ?, capacity = ?, building = ?, floor = ?
                WHERE id = ?;
            """
            self.execute(
                sql,
                (entity.name, entity.code, rtype_val, entity.capacity, entity.building, entity.floor, str(entity.id)),
            )
        return entity

    def delete(self, entity_id: str) -> bool:
        sql = "DELETE FROM rooms WHERE id = ?;"
        cursor = self.execute(sql, (str(entity_id),))
        return cursor.rowcount > 0

    # --- Availability Operations ---

    def set_availability(self, avail: RoomAvailability) -> None:
        sql = """
            INSERT INTO room_availabilities (id, room_id, day_of_week, period_index, is_available)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(room_id, day_of_week, period_index)
            DO UPDATE SET is_available = excluded.is_available;
        """
        self.execute(
            sql,
            (str(avail.id), str(avail.room_id), avail.day_of_week, avail.period_index, 1 if avail.is_available else 0),
        )

    def is_room_available(self, room_id: str, day_of_week: int, period_index: int) -> bool:
        sql = "SELECT is_available FROM room_availabilities WHERE room_id = ? AND day_of_week = ? AND period_index = ?;"
        row = self.fetchone(sql, (str(room_id), day_of_week, period_index))
        if row is None:
            return True
        return bool(row["is_available"])

    @staticmethod
    def _row_to_room(row) -> Room:
        return Room(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            room_type=RoomType(row["room_type"]),
            capacity=int(row["capacity"]),
            building=row["building"],
            floor=row["floor"],
        )
