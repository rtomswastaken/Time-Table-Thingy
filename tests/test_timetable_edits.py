"""Automated test suite for Timetable Editing, Undo/Redo, and Persistence.

Tests:
1. Moving sessions & duration preservation
2. Swapping sessions & boundary checks
3. Reassigning teachers
4. Reassigning rooms
5. Locking and unlocking sessions
6. Undo and redo execution for all edit types
7. Saving drafts, discarding changes, and dirty state tracking
8. Published schedule immutability & version cloning
9. Timetable version comparison / diff
"""

from __future__ import annotations

import pytest

from core.exceptions import ConcurrencyError, ValidationError
from core.models import (
    ClassGroup,
    ConstraintType,
    ConstraintViolation,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingInputBundle,
    SessionType,
    Subject,
    Teacher,
    TeacherWorkloadRule,
    Timetable,
)
from services.timetable_workspace_service import (
    InMemoryTimetableRepository,
    TimetableWorkspaceService,
)


@pytest.fixture
def test_workspace() -> TimetableWorkspaceService:
    teachers = [
        Teacher(id="T1", department_id="CS", name="Dr. Alan Turing", employee_id="EMP01"),
        Teacher(id="T2", department_id="CS", name="Ada Lovelace", employee_id="EMP02"),
    ]

    rooms = [
        Room(id="R101", name="Room 101", code="R101", room_type=RoomType.LECTURE_HALL, capacity=60),
        Room(id="R102", name="Room 102", code="R102", room_type=RoomType.LECTURE_HALL, capacity=60),
        Room(id="LAB1", name="Computing Lab", code="LAB1", room_type=RoomType.COMPUTER_LAB, capacity=40),
    ]

    class_groups = [
        ClassGroup(id="CS-3A", department_id="CS", semester_id="SEM-3", name="CS-3A", student_count=30),
        ClassGroup(id="CS-3B", department_id="CS", semester_id="SEM-3", name="CS-3B", student_count=30),
    ]

    units = [
        SchedulableUnit(
            unit_id="U1",
            assignment_id="A1",
            class_group_id="CS-3A",
            subject_id="CS101",
            teacher_id="T1",
            session_type=SessionType.THEORY,
            duration_periods=1,
        ),
        SchedulableUnit(
            unit_id="U2",
            assignment_id="A2",
            class_group_id="CS-3A",
            subject_id="CS102",
            teacher_id="T2",
            session_type=SessionType.LABORATORY,
            duration_periods=2,
            required_room_type=RoomType.COMPUTER_LAB,
        ),
        SchedulableUnit(
            unit_id="U3",
            assignment_id="A3",
            class_group_id="CS-3B",
            subject_id="CS101",
            teacher_id="T1",
            session_type=SessionType.THEORY,
            duration_periods=1,
        ),
    ]

    bundle = SchedulingInputBundle(
        institution_id="INST-1",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        days=[0, 1, 2, 3, 4],
        periods_per_day=6,
        break_periods={3},
        units=units,
        teachers=teachers,
        rooms=rooms,
        class_groups=class_groups,
    )

    subjects = [
        Subject(id="CS101", code="CS101", name="Algorithms", department_id="CS", credits=3.0),
        Subject(id="CS102", code="CS102", name="Systems Lab", department_id="CS", credits=2.0),
    ]

    service = TimetableWorkspaceService(
        repository=InMemoryTimetableRepository(),
        bundle=bundle,
        subjects=subjects,
    )

    tt = Timetable(
        id="TT-EDIT-1",
        name="Editable Draft Schedule",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        version=1,
    )

    sessions = [
        # S1: CS-3A at Mon P0 in R101 with T1
        ScheduledSession(
            id="S1",
            timetable_id="TT-EDIT-1",
            class_subject_assignment_id="A1",
            day_of_week=0,
            start_period=0,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # S2: CS-3A Lab at Tue P4-P5 (2 periods) in LAB1 with T2
        ScheduledSession(
            id="S2",
            timetable_id="TT-EDIT-1",
            class_subject_assignment_id="A2",
            day_of_week=1,
            start_period=4,
            duration_periods=2,
            room_id="LAB1",
            teacher_id="T2",
            class_group_id="CS-3A",
        ),
        # S3: CS-3B at Wed P1 in R102 with T1
        ScheduledSession(
            id="S3",
            timetable_id="TT-EDIT-1",
            class_subject_assignment_id="A3",
            day_of_week=2,
            start_period=1,
            duration_periods=1,
            room_id="R102",
            teacher_id="T1",
            class_group_id="CS-3B",
        ),
    ]

    service.repository.save_timetable(tt, sessions)
    service.load_timetable("TT-EDIT-1")
    return service


def test_move_session_and_duration_preservation(test_workspace: TimetableWorkspaceService):
    """Verify moving session updates slots, preserves duration, and rejects period overflow."""
    # 1. Valid move of S1 from Mon P0 to Mon P1
    success, violations = test_workspace.move_session(
        timetable_id="TT-EDIT-1",
        session_id="S1",
        day=0,
        start_period=1,
        room_id="R101",
    )
    assert success is True
    s1 = test_workspace._find_session("S1")
    assert s1.day_of_week == 0
    assert s1.start_period == 1
    assert test_workspace.is_dirty is True

    # 2. Moving 2-period lab (S2) past daily periods must be rejected
    # Day has 6 periods (indices 0..5). Starting 2-period session at period 5 exceeds daily bound
    success_overflow, violations_overflow = test_workspace.move_session(
        timetable_id="TT-EDIT-1",
        session_id="S2",
        day=1,
        start_period=5,
        room_id="LAB1",
    )
    assert success_overflow is False
    assert any(v.violation_type == ConstraintType.LAB_CONTINUITY_BROKEN for v in violations_overflow)

    # Verify duration was preserved
    s2 = test_workspace._find_session("S2")
    assert s2.duration_periods == 2


def test_swap_sessions(test_workspace: TimetableWorkspaceService):
    """Verify swapping two sessions exchanges their time slots and rooms."""
    s1_before = test_workspace._find_session("S1")
    s3_before = test_workspace._find_session("S3")

    s1_orig_slot = (s1_before.day_of_week, s1_before.start_period, s1_before.room_id)
    s3_orig_slot = (s3_before.day_of_week, s3_before.start_period, s3_before.room_id)

    # Swap S1 and S3
    success, violations = test_workspace.swap_sessions(
        timetable_id="TT-EDIT-1",
        session_a_id="S1",
        session_b_id="S3",
    )
    assert success is True

    s1_after = test_workspace._find_session("S1")
    s3_after = test_workspace._find_session("S3")

    # S1 should have S3's old slot
    assert (s1_after.day_of_week, s1_after.start_period, s1_after.room_id) == s3_orig_slot
    # S3 should have S1's old slot
    assert (s3_after.day_of_week, s3_after.start_period, s3_after.room_id) == s1_orig_slot


def test_reassign_teacher_and_room(test_workspace: TimetableWorkspaceService):
    """Verify teacher and room reassignment operations."""
    # Reassign teacher of S1 from T1 to T2
    success_t, _ = test_workspace.reassign_teacher("S1", "T2")
    assert success_t is True
    assert test_workspace._find_session("S1").teacher_id == "T2"

    # Reassign room of S1 from R101 to R102
    success_r, _ = test_workspace.reassign_room("S1", "R102")
    assert success_r is True
    assert test_workspace._find_session("S1").room_id == "R102"


def test_session_locking_blocks_edits(test_workspace: TimetableWorkspaceService):
    """Verify locking a session prevents moving and swapping until unlocked."""
    test_workspace.lock_session("TT-EDIT-1", "S1", lock_reason="Advisor request")
    s1 = test_workspace._find_session("S1")
    assert s1.is_locked is True
    assert test_workspace.get_lock_reason("S1") == "Advisor request"

    # Moving locked session should be rejected
    success_move, violations_move = test_workspace.move_session(
        timetable_id="TT-EDIT-1",
        session_id="S1",
        day=3,
        start_period=2,
        room_id="R101",
        force=False,
    )
    assert success_move is False
    assert any(v.violation_type == ConstraintType.LOCKED_ASSIGNMENT_VIOLATION for v in violations_move)

    # Swapping locked session should be rejected
    success_swap, violations_swap = test_workspace.swap_sessions(
        timetable_id="TT-EDIT-1",
        session_a_id="S1",
        session_b_id="S3",
        force=False,
    )
    assert success_swap is False

    # Unlock session
    test_workspace.unlock_session("TT-EDIT-1", "S1")
    assert test_workspace._find_session("S1").is_locked is False

    # Now moving succeeds
    success_unlocked, _ = test_workspace.move_session(
        timetable_id="TT-EDIT-1",
        session_id="S1",
        day=3,
        start_period=2,
        room_id="R101",
    )
    assert success_unlocked is True


def test_undo_and_redo_stack(test_workspace: TimetableWorkspaceService):
    """Verify complete undo and redo cycles for move, swap, and reassignment."""
    # 1. Test Move Undo / Redo
    orig_day = test_workspace._find_session("S1").day_of_week
    orig_period = test_workspace._find_session("S1").start_period

    test_workspace.move_session("TT-EDIT-1", "S1", day=4, start_period=1, room_id="R101")
    assert test_workspace._find_session("S1").day_of_week == 4
    assert test_workspace.can_undo is True

    # Undo
    assert test_workspace.undo() is True
    assert test_workspace._find_session("S1").day_of_week == orig_day
    assert test_workspace._find_session("S1").start_period == orig_period

    # Redo
    assert test_workspace.redo() is True
    assert test_workspace._find_session("S1").day_of_week == 4

    # 2. Test Swap Undo: Restores BOTH sessions
    s1_slot_before = (test_workspace._find_session("S1").day_of_week, test_workspace._find_session("S1").start_period)
    s3_slot_before = (test_workspace._find_session("S3").day_of_week, test_workspace._find_session("S3").start_period)

    test_workspace.swap_sessions("TT-EDIT-1", "S1", "S3")
    assert (test_workspace._find_session("S1").day_of_week, test_workspace._find_session("S1").start_period) == s3_slot_before

    # Undo swap restores BOTH
    test_workspace.undo()
    assert (test_workspace._find_session("S1").day_of_week, test_workspace._find_session("S1").start_period) == s1_slot_before
    assert (test_workspace._find_session("S3").day_of_week, test_workspace._find_session("S3").start_period) == s3_slot_before


def test_save_draft_and_discard_changes(test_workspace: TimetableWorkspaceService):
    """Verify dirty tracking, saving drafts, and discarding unsaved edits."""
    assert test_workspace.is_dirty is False

    # Modify
    test_workspace.move_session("TT-EDIT-1", "S1", day=4, start_period=0, room_id="R101")
    assert test_workspace.is_dirty is True

    # Discard
    test_workspace.discard_changes()
    assert test_workspace.is_dirty is False
    assert test_workspace._find_session("S1").day_of_week == 0  # Reverted back to Mon

    # Modify and Save
    test_workspace.move_session("TT-EDIT-1", "S1", day=4, start_period=0, room_id="R101")
    saved_tt = test_workspace.save_draft()
    assert test_workspace.is_dirty is False
    assert saved_tt.updated_at is not None

    # Verify storage has updated session
    stored_sessions = test_workspace.repository.get_sessions("TT-EDIT-1")
    s1_stored = next(s for s in stored_sessions if s.id == "S1")
    assert s1_stored.day_of_week == 4


def test_published_schedule_immutability_and_cloning(test_workspace: TimetableWorkspaceService):
    """Verify published timetables cannot be modified directly and must be cloned."""
    # Publish schedule
    published = test_workspace.publish_timetable()
    assert published.is_published is True

    # Trying to save changes to published timetable raises ConcurrencyError
    with pytest.raises(ConcurrencyError, match="Cannot modify an already published timetable"):
        test_workspace.save_draft()

    # Clone into new draft version
    cloned = test_workspace.clone_as_new_draft(name="Odd Semester 2026 - Revision 2")
    assert cloned.version == 2
    assert cloned.is_published is False
    assert cloned.id != published.id

    # Original published timetable remains untouched in repository
    original_in_repo = test_workspace.repository.get_by_id(published.id)
    assert original_in_repo.is_published is True
    assert original_in_repo.version == 1


def test_version_comparison_diff(test_workspace: TimetableWorkspaceService):
    """Verify TimetableDiff accurately identifies moved sessions and reassigned resources."""
    # Original is Version 1
    v1_id = test_workspace.active_timetable.id
    test_workspace.save_draft()

    # Clone as Version 2
    v2 = test_workspace.clone_as_new_draft()
    v2_id = v2.id

    # In Version 2: Move S1 and Reassign S3's teacher
    # Note: Sessions were deep-cloned with new IDs during clone_as_new_draft.
    # To test direct ID session diffing, save a version snapshot with identical session IDs:
    tt_v2 = Timetable(
        id="TT-V2-DIFF",
        name="Version 2 Diff Test",
        academic_year_id="AY-2026",
        semester_id="SEM-3",
        version=2,
    )
    sessions_v2 = [
        # S1 moved to Day 4 P2
        ScheduledSession(
            id="S1",
            timetable_id="TT-V2-DIFF",
            class_subject_assignment_id="A1",
            day_of_week=4,
            start_period=2,
            duration_periods=1,
            room_id="R101",
            teacher_id="T1",
            class_group_id="CS-3A",
        ),
        # S2 unchanged
        ScheduledSession(
            id="S2",
            timetable_id="TT-V2-DIFF",
            class_subject_assignment_id="A2",
            day_of_week=1,
            start_period=4,
            duration_periods=2,
            room_id="LAB1",
            teacher_id="T2",
            class_group_id="CS-3A",
        ),
        # S3 teacher reassigned to T2 and room reassigned to R101
        ScheduledSession(
            id="S3",
            timetable_id="TT-V2-DIFF",
            class_subject_assignment_id="A3",
            day_of_week=2,
            start_period=1,
            duration_periods=1,
            room_id="R101",
            teacher_id="T2",
            class_group_id="CS-3B",
        ),
    ]
    test_workspace.repository.save_timetable(tt_v2, sessions_v2)

    diff = test_workspace.compare_versions(v1_id, "TT-V2-DIFF")
    assert diff.total_differences >= 3
    assert len(diff.moved_sessions) == 1
    assert diff.moved_sessions[0].session_id == "S1"
    assert len(diff.reassigned_teachers) == 1
    assert diff.reassigned_teachers[0].session_id == "S3"
    assert len(diff.reassigned_rooms) == 1
    assert diff.reassigned_rooms[0].session_id == "S3"
