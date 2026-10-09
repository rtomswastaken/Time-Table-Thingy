"""
Repository for TeacherPreference, ConstraintViolation, and Audit History entities.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from core.models import ConstraintType, ConstraintViolation, TeacherPreference
from .base import BaseRepository


class PreferenceRepository(BaseRepository):
    """Persistence operations for faculty preferences, conflict reports, and audit history."""

    # --- Teacher Preferences ---

    def save_preference(self, pref: TeacherPreference) -> TeacherPreference:
        sql = """
            INSERT INTO teacher_preferences (id, teacher_id, day_of_week, period_index, preference_weight)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(teacher_id, day_of_week, period_index)
            DO UPDATE SET preference_weight = excluded.preference_weight;
        """
        self.execute(
            sql,
            (str(pref.id), str(pref.teacher_id), pref.day_of_week, pref.period_index, pref.preference_weight),
        )
        return pref

    def list_by_teacher(self, teacher_id: str) -> List[TeacherPreference]:
        sql = """
            SELECT id, teacher_id, day_of_week, period_index, preference_weight
            FROM teacher_preferences WHERE teacher_id = ?
            ORDER BY day_of_week ASC, period_index ASC;
        """
        rows = self.fetchall(sql, (str(teacher_id),))
        return [
            TeacherPreference(
                id=r["id"],
                teacher_id=r["teacher_id"],
                day_of_week=int(r["day_of_week"]),
                period_index=int(r["period_index"]),
                preference_weight=int(r["preference_weight"]),
            )
            for r in rows
        ]

    def delete_preference(self, pref_id: str) -> bool:
        sql = "DELETE FROM teacher_preferences WHERE id = ?;"
        cursor = self.execute(sql, (str(pref_id),))
        return cursor.rowcount > 0

    # --- Conflict Records & Validation Reports ---

    def record_conflicts(self, timetable_id: str, violations: List[ConstraintViolation]) -> None:
        """Atomically replaces recorded conflicts for a timetable."""
        with self.db_manager.transaction() as tx:
            tx.execute("DELETE FROM conflict_records WHERE timetable_id = ?;", (str(timetable_id),))
            insert_sql = """
                INSERT INTO conflict_records (id, timetable_id, violation_type, is_hard, severity, message, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """
            import uuid
            for v in violations:
                details = {
                    "sessions": [str(s) for s in v.involved_sessions],
                    "teachers": [str(t) for t in v.involved_teachers],
                    "rooms": [str(r) for r in v.involved_rooms],
                    "classes": [str(c) for c in v.involved_classes],
                }
                tx.execute(
                    insert_sql,
                    (
                        str(uuid.uuid4()),
                        str(timetable_id),
                        v.violation_type.value if isinstance(v.violation_type, ConstraintType) else str(v.violation_type),
                        1 if v.is_hard else 0,
                        v.severity,
                        v.message,
                        json.dumps(details),
                    ),
                )

    def list_conflicts(self, timetable_id: str) -> List[ConstraintViolation]:
        sql = """
            SELECT id, timetable_id, violation_type, is_hard, severity, message, details_json
            FROM conflict_records WHERE timetable_id = ?;
        """
        rows = self.fetchall(sql, (str(timetable_id),))
        violations: List[ConstraintViolation] = []
        for r in rows:
            details = json.loads(r["details_json"]) if r["details_json"] else {}
            violations.append(
                ConstraintViolation(
                    violation_type=ConstraintType(r["violation_type"]),
                    is_hard=bool(r["is_hard"]),
                    severity=r["severity"],
                    message=r["message"],
                    involved_sessions=details.get("sessions", []),
                    involved_teachers=details.get("teachers", []),
                    involved_rooms=details.get("rooms", []),
                    involved_classes=details.get("classes", []),
                )
            )
        return violations

    # --- Change & Audit Logging ---

    def log_change(
        self,
        timetable_id: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        details_json: Optional[str] = None,
    ) -> str:
        import uuid
        log_id = str(uuid.uuid4())
        sql = """
            INSERT INTO timetable_change_logs (id, timetable_id, action, entity_type, entity_id, details_json)
            VALUES (?, ?, ?, ?, ?, ?);
        """
        self.execute(sql, (log_id, str(timetable_id), action, entity_type, entity_id, details_json))
        return log_id

    def list_audit_log(self, timetable_id: str) -> List[Dict[str, Any]]:
        sql = """
            SELECT id, timetable_id, action, entity_type, entity_id, details_json, changed_at
            FROM timetable_change_logs WHERE timetable_id = ? ORDER BY changed_at DESC;
        """
        rows = self.fetchall(sql, (str(timetable_id),))
        return [
            {
                "id": r["id"],
                "timetable_id": r["timetable_id"],
                "action": r["action"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "details": json.loads(r["details_json"]) if r["details_json"] else None,
                "changed_at": r["changed_at"],
            }
            for r in rows
        ]
