"""Workload and Preference Persistence Layer.

Provides SQLite repository and in-memory repository for teacher availability,
workload rules, profiles, and soft preferences.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional, Protocol, Set, Tuple

from workload.models import (
    DetailedTeacherPreference,
    SoftPreferenceType,
    TeacherWorkloadRuleExtended,
    WorkloadProfile,
)


class BaseWorkloadRepository(Protocol):
    """Protocol for workload persistence implementations."""

    def get_unavailable_slots(self, teacher_id: str) -> Set[Tuple[int, int]]: ...
    def save_unavailable_slots(self, teacher_id: str, slots: Set[Tuple[int, int]]) -> None: ...
    def get_slot_weights(self, teacher_id: str) -> Dict[Tuple[int, int], int]: ...
    def save_slot_weights(self, teacher_id: str, weights: Dict[Tuple[int, int], int]) -> None: ...
    def get_soft_preferences(self, teacher_id: str) -> List[DetailedTeacherPreference]: ...
    def save_soft_preferences(self, teacher_id: str, prefs: List[DetailedTeacherPreference]) -> None: ...
    def get_workload_rule(self, teacher_id: str) -> Optional[TeacherWorkloadRuleExtended]: ...
    def save_workload_rule(self, rule: TeacherWorkloadRuleExtended) -> None: ...
    def get_profile(self, profile_id: str) -> Optional[WorkloadProfile]: ...
    def save_profile(self, profile: WorkloadProfile) -> None: ...
    def list_profiles(self) -> List[WorkloadProfile]: ...


class InMemoryWorkloadRepository:
    """Thread-safe in-memory repository for tests and isolated evaluation."""

    def __init__(self) -> None:
        self._availability: Dict[str, Set[Tuple[int, int]]] = {}
        self._slot_weights: Dict[str, Dict[Tuple[int, int], int]] = {}
        self._soft_preferences: Dict[str, List[DetailedTeacherPreference]] = {}
        self._rules: Dict[str, TeacherWorkloadRuleExtended] = {}
        self._profiles: Dict[str, WorkloadProfile] = {}

    def get_unavailable_slots(self, teacher_id: str) -> Set[Tuple[int, int]]:
        return set(self._availability.get(teacher_id, set()))

    def save_unavailable_slots(self, teacher_id: str, slots: Set[Tuple[int, int]]) -> None:
        self._availability[teacher_id] = set(slots)

    def get_slot_weights(self, teacher_id: str) -> Dict[Tuple[int, int], int]:
        return dict(self._slot_weights.get(teacher_id, {}))

    def save_slot_weights(self, teacher_id: str, weights: Dict[Tuple[int, int], int]) -> None:
        self._slot_weights[teacher_id] = dict(weights)

    def get_soft_preferences(self, teacher_id: str) -> List[DetailedTeacherPreference]:
        return list(self._soft_preferences.get(teacher_id, []))

    def save_soft_preferences(self, teacher_id: str, prefs: List[DetailedTeacherPreference]) -> None:
        self._soft_preferences[teacher_id] = list(prefs)

    def get_workload_rule(self, teacher_id: str) -> Optional[TeacherWorkloadRuleExtended]:
        return self._rules.get(teacher_id)

    def save_workload_rule(self, rule: TeacherWorkloadRuleExtended) -> None:
        self._rules[rule.teacher_id] = rule

    def get_profile(self, profile_id: str) -> Optional[WorkloadProfile]:
        return self._profiles.get(profile_id)

    def save_profile(self, profile: WorkloadProfile) -> None:
        self._profiles[profile.id] = profile

    def list_profiles(self) -> List[WorkloadProfile]:
        return list(self._profiles.values())


class WorkloadRepository:
    """SQLite implementation of workload and preference persistence."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        """Initializes tables for availability, preferences, and workload rules."""
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_availabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,
                period_index INTEGER NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                UNIQUE(teacher_id, day_of_week, period_index)
            );

            CREATE TABLE IF NOT EXISTS teacher_preferences (
                id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                preference_type TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 5,
                target_value_json TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                description TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS teacher_slot_weights (
                teacher_id TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,
                period_index INTEGER NOT NULL,
                weight INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (teacher_id, day_of_week, period_index)
            );

            CREATE TABLE IF NOT EXISTS teacher_workload_rules (
                teacher_id TEXT PRIMARY KEY,
                max_periods_per_week INTEGER NOT NULL DEFAULT 20,
                min_periods_per_week INTEGER NOT NULL DEFAULT 0,
                max_periods_per_day INTEGER NOT NULL DEFAULT 5,
                min_periods_per_day INTEGER NOT NULL DEFAULT 0,
                max_consecutive_periods INTEGER NOT NULL DEFAULT 3,
                max_contact_minutes_per_week INTEGER,
                min_contact_minutes_per_week INTEGER,
                max_contact_minutes_per_day INTEGER,
                max_periods_per_class_per_week INTEGER,
                min_periods_per_class_per_week INTEGER,
                max_periods_per_class_per_day INTEGER,
                max_working_days INTEGER,
                profile_id TEXT,
                subject_limits_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS workload_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                max_periods_per_week INTEGER NOT NULL,
                min_periods_per_week INTEGER NOT NULL,
                max_periods_per_day INTEGER NOT NULL,
                min_periods_per_day INTEGER NOT NULL,
                max_consecutive_periods INTEGER NOT NULL,
                max_contact_minutes_per_week INTEGER,
                min_contact_minutes_per_week INTEGER,
                max_contact_minutes_per_day INTEGER,
                max_periods_per_class_per_week INTEGER,
                min_periods_per_class_per_week INTEGER,
                max_periods_per_class_per_day INTEGER,
                max_working_days INTEGER
            );
            """
        )
        self.conn.commit()

    def get_unavailable_slots(self, teacher_id: str) -> Set[Tuple[int, int]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT day_of_week, period_index FROM teacher_availabilities WHERE teacher_id = ? AND is_available = 0",
            (teacher_id,),
        )
        return {(row[0], row[1]) for row in cur.fetchall()}

    def save_unavailable_slots(self, teacher_id: str, slots: Set[Tuple[int, int]]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM teacher_availabilities WHERE teacher_id = ?", (teacher_id,))
        for day, period in slots:
            cur.execute(
                """
                INSERT INTO teacher_availabilities (teacher_id, day_of_week, period_index, is_available)
                VALUES (?, ?, ?, 0)
                """,
                (teacher_id, day, period),
            )
        self.conn.commit()

    def get_slot_weights(self, teacher_id: str) -> Dict[Tuple[int, int], int]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT day_of_week, period_index, weight FROM teacher_slot_weights WHERE teacher_id = ?",
            (teacher_id,),
        )
        return {(row[0], row[1]): row[2] for row in cur.fetchall()}

    def save_slot_weights(self, teacher_id: str, weights: Dict[Tuple[int, int], int]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM teacher_slot_weights WHERE teacher_id = ?", (teacher_id,))
        for (day, period), weight in weights.items():
            cur.execute(
                """
                INSERT INTO teacher_slot_weights (teacher_id, day_of_week, period_index, weight)
                VALUES (?, ?, ?, ?)
                """,
                (teacher_id, day, period, weight),
            )
        self.conn.commit()

    def get_soft_preferences(self, teacher_id: str) -> List[DetailedTeacherPreference]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, preference_type, weight, target_value_json, is_active, description FROM teacher_preferences WHERE teacher_id = ?",
            (teacher_id,),
        )
        prefs = []
        for row in cur.fetchall():
            target_val = json.loads(row["target_value_json"]) if row["target_value_json"] else None
            prefs.append(
                DetailedTeacherPreference(
                    id=row["id"],
                    teacher_id=teacher_id,
                    preference_type=SoftPreferenceType(row["preference_type"]),
                    weight=row["weight"],
                    target_value=target_val,
                    is_active=bool(row["is_active"]),
                    description=row["description"] or "",
                )
            )
        return prefs

    def save_soft_preferences(self, teacher_id: str, prefs: List[DetailedTeacherPreference]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM teacher_preferences WHERE teacher_id = ?", (teacher_id,))
        for p in prefs:
            cur.execute(
                """
                INSERT INTO teacher_preferences (id, teacher_id, preference_type, weight, target_value_json, is_active, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.id,
                    teacher_id,
                    p.preference_type.value,
                    p.weight,
                    json.dumps(p.target_value) if p.target_value is not None else None,
                    1 if p.is_active else 0,
                    p.description,
                ),
            )
        self.conn.commit()

    def get_workload_rule(self, teacher_id: str) -> Optional[TeacherWorkloadRuleExtended]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM teacher_workload_rules WHERE teacher_id = ?", (teacher_id,))
        row = cur.fetchone()
        if not row:
            return None
        return TeacherWorkloadRuleExtended(
            teacher_id=row["teacher_id"],
            max_periods_per_week=row["max_periods_per_week"],
            min_periods_per_week=row["min_periods_per_week"],
            max_periods_per_day=row["max_periods_per_day"],
            min_periods_per_day=row["min_periods_per_day"],
            max_consecutive_periods=row["max_consecutive_periods"],
            max_contact_minutes_per_week=row["max_contact_minutes_per_week"],
            min_contact_minutes_per_week=row["min_contact_minutes_per_week"],
            max_contact_minutes_per_day=row["max_contact_minutes_per_day"],
            max_periods_per_class_per_week=row["max_periods_per_class_per_week"],
            min_periods_per_class_per_week=row["min_periods_per_class_per_week"],
            max_periods_per_class_per_day=row["max_periods_per_class_per_day"],
            max_working_days=row["max_working_days"],
            profile_id=row["profile_id"],
            subject_limits=json.loads(row["subject_limits_json"] or "{}"),
        )

    def save_workload_rule(self, rule: TeacherWorkloadRuleExtended) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO teacher_workload_rules (
                teacher_id, max_periods_per_week, min_periods_per_week, max_periods_per_day,
                min_periods_per_day, max_consecutive_periods, max_contact_minutes_per_week,
                min_contact_minutes_per_week, max_contact_minutes_per_day,
                max_periods_per_class_per_week, min_periods_per_class_per_week,
                max_periods_per_class_per_day, max_working_days, profile_id, subject_limits_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(teacher_id) DO UPDATE SET
                max_periods_per_week=excluded.max_periods_per_week,
                min_periods_per_week=excluded.min_periods_per_week,
                max_periods_per_day=excluded.max_periods_per_day,
                min_periods_per_day=excluded.min_periods_per_day,
                max_consecutive_periods=excluded.max_consecutive_periods,
                max_contact_minutes_per_week=excluded.max_contact_minutes_per_week,
                min_contact_minutes_per_week=excluded.min_contact_minutes_per_week,
                max_contact_minutes_per_day=excluded.max_contact_minutes_per_day,
                max_periods_per_class_per_week=excluded.max_periods_per_class_per_week,
                min_periods_per_class_per_week=excluded.min_periods_per_class_per_week,
                max_periods_per_class_per_day=excluded.max_periods_per_class_per_day,
                max_working_days=excluded.max_working_days,
                profile_id=excluded.profile_id,
                subject_limits_json=excluded.subject_limits_json
            """,
            (
                rule.teacher_id,
                rule.max_periods_per_week,
                rule.min_periods_per_week,
                rule.max_periods_per_day,
                rule.min_periods_per_day,
                rule.max_consecutive_periods,
                rule.max_contact_minutes_per_week,
                rule.min_contact_minutes_per_week,
                rule.max_contact_minutes_per_day,
                rule.max_periods_per_class_per_week,
                rule.min_periods_per_class_per_week,
                rule.max_periods_per_class_per_day,
                rule.max_working_days,
                rule.profile_id,
                json.dumps(rule.subject_limits),
            ),
        )
        self.conn.commit()

    def get_profile(self, profile_id: str) -> Optional[WorkloadProfile]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM workload_profiles WHERE id = ?", (profile_id,))
        row = cur.fetchone()
        if not row:
            return None
        return WorkloadProfile(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            max_periods_per_week=row["max_periods_per_week"],
            min_periods_per_week=row["min_periods_per_week"],
            max_periods_per_day=row["max_periods_per_day"],
            min_periods_per_day=row["min_periods_per_day"],
            max_consecutive_periods=row["max_consecutive_periods"],
            max_contact_minutes_per_week=row["max_contact_minutes_per_week"],
            min_contact_minutes_per_week=row["min_contact_minutes_per_week"],
            max_contact_minutes_per_day=row["max_contact_minutes_per_day"],
            max_periods_per_class_per_week=row["max_periods_per_class_per_week"],
            min_periods_per_class_per_week=row["min_periods_per_class_per_week"],
            max_periods_per_class_per_day=row["max_periods_per_class_per_day"],
            max_working_days=row["max_working_days"],
        )

    def save_profile(self, profile: WorkloadProfile) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO workload_profiles (
                id, name, description, max_periods_per_week, min_periods_per_week,
                max_periods_per_day, min_periods_per_day, max_consecutive_periods,
                max_contact_minutes_per_week, min_contact_minutes_per_week,
                max_contact_minutes_per_day, max_periods_per_class_per_week,
                min_periods_per_class_per_week, max_periods_per_class_per_day, max_working_days
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                max_periods_per_week=excluded.max_periods_per_week,
                min_periods_per_week=excluded.min_periods_per_week,
                max_periods_per_day=excluded.max_periods_per_day,
                min_periods_per_day=excluded.min_periods_per_day,
                max_consecutive_periods=excluded.max_consecutive_periods,
                max_contact_minutes_per_week=excluded.max_contact_minutes_per_week,
                min_contact_minutes_per_week=excluded.min_contact_minutes_per_week,
                max_contact_minutes_per_day=excluded.max_contact_minutes_per_day,
                max_periods_per_class_per_week=excluded.max_periods_per_class_per_week,
                min_periods_per_class_per_week=excluded.min_periods_per_class_per_week,
                max_periods_per_class_per_day=excluded.max_periods_per_class_per_day,
                max_working_days=excluded.max_working_days
            """,
            (
                profile.id,
                profile.name,
                profile.description,
                profile.max_periods_per_week,
                profile.min_periods_per_week,
                profile.max_periods_per_day,
                profile.min_periods_per_day,
                profile.max_consecutive_periods,
                profile.max_contact_minutes_per_week,
                profile.min_contact_minutes_per_week,
                profile.max_contact_minutes_per_day,
                profile.max_periods_per_class_per_week,
                profile.min_periods_per_class_per_week,
                profile.max_periods_per_class_per_day,
                profile.max_working_days,
            ),
        )
        self.conn.commit()

    def list_profiles(self) -> List[WorkloadProfile]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM workload_profiles ORDER BY name ASC")
        return [
            WorkloadProfile(
                id=r["id"],
                name=r["name"],
                description=r["description"] or "",
                max_periods_per_week=r["max_periods_per_week"],
                min_periods_per_week=r["min_periods_per_week"],
                max_periods_per_day=r["max_periods_per_day"],
                min_periods_per_day=r["min_periods_per_day"],
                max_consecutive_periods=r["max_consecutive_periods"],
                max_contact_minutes_per_week=r["max_contact_minutes_per_week"],
                min_contact_minutes_per_week=r["min_contact_minutes_per_week"],
                max_contact_minutes_per_day=r["max_contact_minutes_per_day"],
                max_periods_per_class_per_week=r["max_periods_per_class_per_week"],
                min_periods_per_class_per_week=r["min_periods_per_class_per_week"],
                max_periods_per_class_per_day=r["max_periods_per_class_per_day"],
                max_working_days=r["max_working_days"],
            )
            for r in cur.fetchall()
        ]
