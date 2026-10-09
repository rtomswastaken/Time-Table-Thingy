"""Comprehensive End-to-End Workflow Verification Test for Timetable Thingy.

Executes and verifies the complete 14-step workflow:
1. Initialize the application and SQLite persistence.
2. Create an institution and department.
3. Create an academic year and semester.
4. Create a class cohort.
5. Create teachers and availability rules.
6. Create subjects and weekly session requirements.
7. Create classrooms and laboratories.
8. Generate a timetable using the CP-SAT engine.
9. Verify that hard constraints are satisfied.
10. Open the timetable workspace service.
11. Edit a session and validate the change in real-time.
12. Save and reopen a timetable version.
13. Export the schedule to Excel and PDF.
14. Restart the application and verify persisted data remains available.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from academic.academic_service import AcademicService
from core.models import (
    ConstraintViolation,
    Institution,
    Room,
    RoomType,
    SchedulableUnit,
    ScheduledSession,
    SchedulingConfig,
    SchedulingInputBundle,
    SchedulingResult,
    SchedulingStatus,
    SessionType,
    Subject,
    Teacher,
    Timetable,
)
from database.connection import DatabaseManager
from database.repositories import (
    ClassGroupRepository,
    DepartmentRepository,
    InstitutionRepository,
    RoomRepository,
    ScheduledSessionRepository,
    SubjectRepository,
    TeacherRepository,
    TimetableRepository,
)
from database.schema import check_integrity, initialize_database
from exchange.exporters.excel_exporter import ExcelExporter
from exchange.exporters.pdf_exporter import PDFTimetableExporter
from exchange.service import ImportExportServiceImpl
from services.timetable_workspace_service import TimetableWorkspaceService
from solver.solver import solve
from solver.validator import DeterministicScheduleValidator
from workload.repository import WorkloadRepository
from workload.service import WorkloadServiceImpl


def test_complete_end_to_end_workflow():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "e2e_timetable.db"

        # ---------------------------------------------------------------------
        # Step 1: Initialize application & database
        # ---------------------------------------------------------------------
        db_manager = DatabaseManager(db_path)
        applied = initialize_database(db_manager)
        assert len(applied) >= 1
        assert check_integrity(db_manager) is True

        acad_service = AcademicService(db_manager)
        tt_repo = TimetableRepository(db_manager)
        workload_repo = WorkloadRepository(db_manager.get_connection())
        workload_service = WorkloadServiceImpl(repository=workload_repo, timetable_repo=tt_repo)

        # ---------------------------------------------------------------------
        # Step 2: Create Institution & Department
        # ---------------------------------------------------------------------
        inst = acad_service.institution_service.get_or_create_default_institution(
            name="Apex Institute of Technology", code="AIT"
        )
        assert inst.code == "AIT"

        dept = acad_service.create_department(str(inst.id), "Computer Science & Engineering", "CSE")
        assert dept.code == "CSE"

        # ---------------------------------------------------------------------
        # Step 3: Create Academic Year and Semester
        # ---------------------------------------------------------------------
        ay = acad_service.period_service.create_academic_year(
            name="2026-2027", start_date="2026-08-01", end_date="2027-05-31", is_current=True
        )
        assert ay.name == "2026-2027"

        sem = acad_service.period_service.create_semester(
            academic_year_id=str(ay.id), number=3, term_name="Fall 2026"
        )
        assert sem.number == 3

        # ---------------------------------------------------------------------
        # Step 4: Create Class Cohort
        # ---------------------------------------------------------------------
        class_group = acad_service.create_class_group(
            department_id=str(dept.id),
            semester_id=str(sem.id),
            name="CSE-3A",
            student_count=40,
        )
        assert class_group.name == "CSE-3A"

        # ---------------------------------------------------------------------
        # Step 5: Create Teachers and Availability Rules
        # ---------------------------------------------------------------------
        t1 = acad_service.create_teacher(
            department_id=str(dept.id),
            name="Dr. Alan Turing",
            employee_id="FAC-001",
            email="alan@apex.edu",
        )
        t2 = acad_service.create_teacher(
            department_id=str(dept.id),
            name="Prof. Ada Lovelace",
            employee_id="FAC-002",
            email="ada@apex.edu",
        )

        # Faculty availability: Dr. Turing unavailable Monday Period 0 (morning seminar)
        workload_service.set_availability(str(t1.id), {(0, 0)})
        assert (0, 0) in workload_service.get_availability(str(t1.id))

        # ---------------------------------------------------------------------
        # Step 6: Create Subjects and Weekly Session Requirements
        # ---------------------------------------------------------------------
        subj_theory = acad_service.create_subject(
            department_id=str(dept.id),
            code="CS301",
            name="Data Structures",
            credits=4.0,
        )
        subj_lab = acad_service.create_subject(
            department_id=str(dept.id),
            code="CS302",
            name="Algorithms Lab",
            credits=2.0,
            is_elective=False,
        )

        offering_theory = acad_service.create_offering(
            subject_id=str(subj_theory.id),
            semester_id=str(sem.id),
            weekly_contact_hours=2.0,
            weekly_periods=2,
        )
        offering_lab = acad_service.create_offering(
            subject_id=str(subj_lab.id),
            semester_id=str(sem.id),
            weekly_contact_hours=2.0,
            weekly_periods=2,
        )

        asgn_theory = acad_service.assign_subject_to_class(
            class_group_id=str(class_group.id),
            offering_id=str(offering_theory.id),
            primary_teacher_id=str(t1.id),
        )
        asgn_lab = acad_service.assign_subject_to_class(
            class_group_id=str(class_group.id),
            offering_id=str(offering_lab.id),
            primary_teacher_id=str(t2.id),
        )

        # ---------------------------------------------------------------------
        # Step 7: Create Classrooms and Laboratories
        # ---------------------------------------------------------------------
        classroom = acad_service.create_room(
            name="Lecture Hall 101",
            code="LH-101",
            room_type=RoomType.LECTURE_HALL,
            capacity=60,
        )
        lab_room = acad_service.create_room(
            name="Computing Lab 1",
            code="LAB-1",
            room_type=RoomType.COMPUTER_LAB,
            capacity=45,
        )

        # ---------------------------------------------------------------------
        # Step 8: Generate Timetable with CP-SAT
        # ---------------------------------------------------------------------
        units = [
            # 2 single Theory periods with Turing in Classroom
            SchedulableUnit(
                unit_id="u-cs301-1",
                assignment_id=str(asgn_theory.id),
                class_group_id=str(class_group.id),
                subject_id=str(subj_theory.id),
                teacher_id=str(t1.id),
                session_type=SessionType.THEORY,
                duration_periods=1,
            ),
            SchedulableUnit(
                unit_id="u-cs301-2",
                assignment_id=str(asgn_theory.id),
                class_group_id=str(class_group.id),
                subject_id=str(subj_theory.id),
                teacher_id=str(t1.id),
                session_type=SessionType.THEORY,
                duration_periods=1,
            ),
            # 1 consecutive 2-period Lab block with Lovelace in Computer Lab
            SchedulableUnit(
                unit_id="u-cs302-lab",
                assignment_id=str(asgn_lab.id),
                class_group_id=str(class_group.id),
                subject_id=str(subj_lab.id),
                teacher_id=str(t2.id),
                session_type=SessionType.LABORATORY,
                duration_periods=2,
                required_room_type=RoomType.COMPUTER_LAB,
            ),
        ]

        bundle = SchedulingInputBundle(
            institution_id=str(inst.id),
            academic_year_id=str(ay.id),
            semester_id=str(sem.id),
            days=[0, 1, 2, 3, 4],
            periods_per_day=6,
            break_periods={3},
            units=units,
            teachers=[t1, t2],
            rooms=[classroom, lab_room],
            class_groups=[class_group],
            teacher_availability={str(t1.id): {(0, 0)}},  # Turing cannot teach Mon period 0
        )

        config = SchedulingConfig(time_limit_seconds=15.0)
        solver_result = solve(bundle, config)

        assert solver_result.status in (SchedulingStatus.OPTIMAL, SchedulingStatus.FEASIBLE)
        assert len(solver_result.sessions) == 3

        # ---------------------------------------------------------------------
        # Step 9: Verify Hard Constraints Satisfied
        # ---------------------------------------------------------------------
        validator = DeterministicScheduleValidator()
        violations = validator.validate(solver_result.sessions, bundle)
        hard_violations = [v for v in violations if v.is_hard]
        assert len(hard_violations) == 0, f"Expected 0 hard violations, got: {hard_violations}"

        # Verify Turing was NOT scheduled at Mon Period 0
        for s in solver_result.sessions:
            if s.teacher_id == str(t1.id):
                assert not (s.day_of_week == 0 and 0 in s.occupied_periods)

        # ---------------------------------------------------------------------
        # Step 10: Open Timetable Workspace
        # ---------------------------------------------------------------------
        workspace_service = TimetableWorkspaceService(
            repository=tt_repo,
            validator=validator,
            bundle=bundle,
            subjects=[subj_theory, subj_lab],
        )
        timetable = workspace_service.create_draft_from_generation(solver_result)
        assert timetable.name is not None
        assert len(workspace_service.active_sessions) == 3

        # ---------------------------------------------------------------------
        # Step 11: Edit a session and validate change
        # ---------------------------------------------------------------------
        target_session = workspace_service.active_sessions[0]
        original_day = target_session.day_of_week
        new_day = (original_day + 1) % 5
        success, move_violations = workspace_service.move_session(
            timetable_id=str(timetable.id),
            session_id=str(target_session.id),
            day=new_day,
            start_period=4,
            room_id=str(classroom.id),
        )
        assert success is True
        assert target_session.day_of_week == new_day
        assert target_session.start_period == 4
        assert workspace_service.is_dirty is True

        # ---------------------------------------------------------------------
        # Step 12: Save and Reopen Timetable Version
        # ---------------------------------------------------------------------
        workspace_service.save_draft()
        assert workspace_service.is_dirty is False

        # Load back from database repository
        reopened_timetable = tt_repo.get_by_id(str(timetable.id))
        assert reopened_timetable is not None
        reopened_sessions = tt_repo.get_sessions(str(timetable.id))
        assert len(reopened_sessions) == 3

        # ---------------------------------------------------------------------
        # Step 13: Export Schedule to Excel and PDF
        # ---------------------------------------------------------------------
        excel_path = Path(temp_dir) / "exported_schedule.xlsx"
        pdf_path = Path(temp_dir) / "exported_schedule.pdf"

        excel_result = ExcelExporter.export_full_workbook(
            output_path=excel_path,
            sessions=reopened_sessions,
        )
        assert Path(excel_result.file_path).exists()
        assert Path(excel_result.file_path).stat().st_size > 0

        pdf_result = PDFTimetableExporter.export_timetable(
            output_path=pdf_path,
            sessions=reopened_sessions,
        )
        assert Path(pdf_result.file_path).exists()
        assert Path(pdf_result.file_path).stat().st_size > 0

        # ---------------------------------------------------------------------
        # Step 14: Restart Application and Verify Persistence
        # ---------------------------------------------------------------------
        fresh_db_manager = DatabaseManager(db_path)
        fresh_tt_repo = TimetableRepository(fresh_db_manager)
        fresh_class_repo = ClassGroupRepository(fresh_db_manager)
        fresh_teacher_repo = TeacherRepository(fresh_db_manager)

        persisted_classes = fresh_class_repo.list_all()
        assert any(c.name == "CSE-3A" for c in persisted_classes)

        persisted_teachers = fresh_teacher_repo.list_all()
        assert any(t.name == "Dr. Alan Turing" for t in persisted_teachers)

        persisted_tt = fresh_tt_repo.get_by_id(str(timetable.id))
        assert persisted_tt is not None
        assert persisted_tt.id == timetable.id

        persisted_sessions = fresh_tt_repo.get_sessions(str(timetable.id))
        assert len(persisted_sessions) == 3
