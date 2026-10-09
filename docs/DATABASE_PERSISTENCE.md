# Timetable Thingy - Database & Persistence Layer Architecture

**Owner**: Agent 2 (Database Architect)  
**Target Consumers**: Agent 3 (Academic Management), Agent 4 (Workload & Preferences), Agent 5 (Solver), Agent 6 (Timetable Grid), Agent 7 (Import/Export & Reports), Agent 8 (Shell & Coordinator)  
**Standard Compliance**: Conforms directly to `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, `docs/INTEGRATION_CONTRACTS.md`, and `core.interfaces.py`.

---

## 1. Database Technology & Infrastructure

- **Engine**: Local SQLite database using Python's standard library `sqlite3`.
- **Zero Cloud / Zero Server**: Runs 100% locally with zero internet dependency.
- **WAL Journaling**: Configured with `PRAGMA journal_mode = WAL;` (Write-Ahead Logging) and `PRAGMA synchronous = NORMAL;`, allowing non-blocking concurrent readers while background workers or transactions write.
- **Foreign Key Enforcement**: `PRAGMA foreign_keys = ON;` is strictly executed on **every** connection.
- **Concurrency & Busy Handling**: `PRAGMA busy_timeout = 10000;` prevents instant contention errors between UI reading threads and background optimization workers.
- **Transaction Safety**: Configured with `isolation_level = None` for explicit transaction management via `db_manager.transaction()`, which uses `BEGIN IMMEDIATE` and safe `COMMIT`/`ROLLBACK` based on transaction state.
- **Thread Isolation**: `DatabaseManager` maintains thread-local connections to guarantee worker threads and the main GUI thread never share open SQLite connection handles.

---

## 2. Relational Schema & Entity Coverage

The relational schema is defined declaratively and versioned in `database/migrations/001_initial_schema.sql`.

### 2.1 Academic Structure
- `institutions`: Institutional root profile (`id`, `name`, `code`, `working_days`, `periods_per_day`, `period_duration_minutes`, `created_at`).
- `departments`: Academic departments with unique constraint on `(institution_id, code)`.
- `academic_years`: Study cycles (`id`, `name`, `start_date`, `end_date`, `is_current`).
- `semesters`: Term subdivisions with unique constraint on `(academic_year_id, number)`.
- `class_groups`: Student cohorts/sections with unique constraint on `(department_id, semester_id, name)`.
- `student_groups`: Lab partitions and batches with unique constraint on `(class_group_id, name)`.

### 2.2 Faculty & Preferences
- `teachers`: Faculty member identities with unique constraint on `employee_id`.
- `teacher_qualifications`: Faculty-to-subject eligibility mapping (`competency_level`, `preference_score`), explicitly separated from timetable assignments.
- `teacher_availabilities`: Hard time-slot availability matrix (`day_of_week`, `period_index`, `is_available`).
- `teacher_preferences`: Soft temporal preference weighting (`preference_weight` from -10 to +10).
- `teacher_workload_rules`: Contractual workload boundaries (`max_periods_per_week`, `min_periods_per_week`, `max_periods_per_day`, `max_consecutive_periods`).

### 2.3 Subjects & Curricular Offerings
- `subjects`: Master catalog course definitions (`id`, `code`, `name`, `credits`, `is_elective`).
- `subject_offerings`: Instantiation of a subject in a semester, storing **physical classroom requirements** (`weekly_contact_hours`, `weekly_periods`) strictly distinct from academic credits.
- `subject_session_requirements`: Breakdown into consecutive blocks (`session_type`, `consecutive_periods`, `frequency_per_week`, `requires_lab`, `preferred_room_type`).
- `class_subject_assignments`: Delivery binding linking class cohort, offering, primary teacher, and optional co-teacher or lab batch.

### 2.4 Physical Resources
- `rooms`: Rooms, halls, and laboratories (`id`, `name`, `code`, `room_type`, `capacity`, `building`, `floor`).
- `room_availabilities`: Availability matrix for rooms across recurring weekly periods.

### 2.5 Timetable & Assignments
- `timetables`: Schedule container (`id`, `name`, `academic_year_id`, `semester_id`, `version`, `is_published`, `created_at`, `updated_at`).
- `scheduled_sessions`: Placed session entries in the recurring weekly schedule (`timetable_id`, `class_subject_assignment_id`, `day_of_week`, `start_period`, `duration_periods`, `room_id`, `teacher_id`, `class_group_id`, `is_locked`).

### 2.6 Validation, Reporting & Audit History
- `scheduling_runs`: Solver run summaries, execution timing, and objective bounds.
- `conflict_records`: Structured validation failure reports (`violation_type`, `is_hard`, `severity`, `message`, `details_json`).
- `timetable_change_logs`: Audit trail recording actions (`create`, `update`, `delete`, `lock`, `unlock`, `publish`, `clone`).

---

## 3. Preserved Domain Distinctions

1. **Academic Credits vs. Weekly Contact Hours**:
   - `Subject.credits` represents academic credit weighting (e.g. 3.0 credits).
   - `SubjectOffering.weekly_contact_hours` represents physical classroom hours required on the timetable (e.g. 5.0 hours/week).
   - Stored in separate tables and columns; contact hours are never inferred from credits.
2. **Subject Catalog vs. Subject Offering**:
   - A `Subject` is the institution's course definition.
   - A `SubjectOffering` is the scheduled delivery in a specific semester.
3. **Teacher Qualification vs. Class Assignment**:
   - `TeacherQualification` represents subject eligibility/competency (which subjects a teacher *can* teach).
   - `ClassSubjectAssignment` represents institutional assignment (which subjects a teacher *is assigned* to teach).
4. **Recurring Weekly Schedule vs. Calendar Date**:
   - All schedules are modeled as recurring weekly time slots (`day_of_week` 0..6 and `start_period` 0..N).
   - The database does not tie general timetables to individual calendar dates.
5. **Draft vs. Published Timetables**:
   - Working schedules are saved as drafts (`is_published = False`).
   - Publishing a timetable marks it as published (`is_published = True`) and guarantees that prior published schedules are never overwritten.
   - Drafting modifications on an existing timetable is performed via `clone_as_new_version()`.

---

## 4. Repository Protocols & Consumer Interfaces

All repositories implement the typed interfaces in `core.interfaces.Repository[T]` and `core.interfaces.TimetableRepository`:

| Repository | Protocol Implemented | Entity Managed |
|---|---|---|
| `InstitutionRepository` | `Repository[Institution]` | `Institution`, `AcademicYear`, `Semester` |
| `DepartmentRepository` | `Repository[Department]` | `Department` |
| `TeacherRepository` | `Repository[Teacher]` | `Teacher`, `TeacherQualification`, `TeacherAvailability`, `TeacherWorkloadRule` |
| `SubjectRepository` | `Repository[Subject]` | `Subject`, `SubjectOffering`, `SubjectSessionRequirement`, `ClassSubjectAssignment` |
| `ClassGroupRepository` | `Repository[ClassGroup]` | `ClassGroup`, `StudentGroup` |
| `RoomRepository` | `Repository[Room]` | `Room`, `RoomAvailability` |
| `TimetableRepository` | `TimetableRepository` | `Timetable`, `ScheduledSession` (atomic persistence) |
| `ScheduledSessionRepository` | N/A | Fine-grained `ScheduledSession` operations & locking |
| `PreferenceRepository` | N/A | `TeacherPreference`, `ConstraintViolation`, `AuditLog` |

### Integration Examples for Downstream Agents

```python
from database import get_db_manager, InstitutionRepository, TimetableRepository, TeacherRepository
from core.models import Institution, Timetable, ScheduledSession

db = get_db_manager()

# 1. Fetching Academic Entities (Agent 3 & 4)
inst_repo = InstitutionRepository(db)
inst = inst_repo.get_by_id("inst-sit")

teacher_repo = TeacherRepository(db)
teachers = teacher_repo.list_by_department("dept-cse")

# 2. Saving Timetable Generation Results (Agent 5 & 8)
tt_repo = TimetableRepository(db)
tt = tt_repo.get_by_id("tt-draft-sem3")

# Atomically saves schedule while automatically preserving pinned/locked sessions:
tt_repo.save_timetable(tt, solver_sessions)

# 3. Pinning and Unlocking Sessions in GUI (Agent 6)
from database import ScheduledSessionRepository
session_repo = ScheduledSessionRepository(db)
session_repo.lock_session("session-id-123")    # Solver will keep this pinned
session_repo.unlock_session("session-id-123")  # Solver can move this freely
```

---

## 5. Safe Online Backup and Restoration

Located in `database/backup.py`:
- **`create_backup(db_manager, backup_path)`**: Uses SQLite's native Online Backup API (`source_conn.backup(dest_conn)`). Creates an atomic, transactionally clean copy on disk without blocking reads or creating corrupted partial snapshots.
- **`validate_backup(backup_path)`**: Executes `PRAGMA integrity_check` on the backup file and verifies the presence of core relational tables before allowing restoration.
- **`restore_backup(backup_path, target_db_manager)`**:
  1. Validates the backup file first.
  2. Creates a pre-restore safety snapshot of the target database (`target_db_pre_restore_TIMESTAMP.bak`).
  3. Uses SQLite's backup API to restore pages into the target database.
  4. Executes post-restore integrity checks and automatically rolls back if restoration fails.

---

## 6. Migration & Schema Versioning

- Migration files are stored in `database/migrations/` as numbered SQL scripts (e.g., `001_initial_schema.sql`).
- The `MigrationRunner` creates and tracks applied migrations in the `schema_migrations` table.
- Initialization is **safe and idempotent**: calling `initialize_database()` on startup executes only unapplied migrations inside atomic transactions without dropping tables or wiping user data.

---

## 7. Verification & Automated Test Suite

Run all automated database tests:
```bash
.venv/bin/pytest tests/database/
```
Or with standard library unittest:
```bash
python3 -m unittest discover tests/database
```

Test coverage:
- `test_connection.py`: Foreign key PRAGMA enforcement, WAL journal mode, busy timeouts, transaction commits, rollback on error, thread-local connection isolation.
- `test_schema_migrations.py`: Migration execution, idempotency, foreign key integrity violations, unique constraints, credit vs contact hours column distinction.
- `test_repositories.py`: Protocol conformance (`isinstance(repo, Repository)`), CRUD lifecycles, qualifications, availabilities, offerings, assignments, room capacities.
- `test_timetable_persistence.py`: Protocol conformance (`isinstance(repo, TimetableRepository)`), session saving, **locked session preservation across updates**, draft publishing without overwriting past versions, version cloning.
- `test_backup_restore.py`: SQLite online backup creation, validation against corrupted/empty files, safe restoration with pre-restore safety snapshots.
- `test_seed.py`: Development dataset seeding, zero foreign-key violations check (`check_foreign_keys`), SQLite database integrity check (`check_integrity`).
