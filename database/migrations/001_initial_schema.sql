-- ============================================================================
-- Migration 001: Initial Schema for Timetable Thingy
-- Comprehensive academic structure, faculty, subjects, rooms, timetables,
-- and validation/reporting records matching core domain architecture.
-- ============================================================================

-- 1. Academic Structure
CREATE TABLE IF NOT EXISTS institutions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    working_days TEXT NOT NULL DEFAULT '[0, 1, 2, 3, 4]',
    periods_per_day INTEGER NOT NULL DEFAULT 6 CHECK (periods_per_day >= 1),
    period_duration_minutes INTEGER NOT NULL DEFAULT 60 CHECK (period_duration_minutes >= 15),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS departments (
    id TEXT PRIMARY KEY,
    institution_id TEXT NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(institution_id, code)
);

CREATE TABLE IF NOT EXISTS academic_years (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS semesters (
    id TEXT PRIMARY KEY,
    academic_year_id TEXT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    number INTEGER NOT NULL CHECK (number >= 1),
    term_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(academic_year_id, number)
);

CREATE TABLE IF NOT EXISTS class_groups (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    semester_id TEXT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    student_count INTEGER NOT NULL DEFAULT 30 CHECK (student_count >= 1),
    home_room_id TEXT REFERENCES rooms(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(department_id, semester_id, name)
);

CREATE TABLE IF NOT EXISTS student_groups (
    id TEXT PRIMARY KEY,
    class_group_id TEXT NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    student_count INTEGER NOT NULL DEFAULT 15 CHECK (student_count >= 1),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(class_group_id, name)
);

-- 2. Faculty & Preferences
CREATE TABLE IF NOT EXISTS teachers (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    employee_id TEXT NOT NULL UNIQUE,
    email TEXT,
    is_full_time INTEGER NOT NULL DEFAULT 1 CHECK (is_full_time IN (0, 1)),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS teacher_qualifications (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    competency_level INTEGER NOT NULL DEFAULT 1,
    preference_score INTEGER NOT NULL DEFAULT 5 CHECK (preference_score BETWEEN 1 AND 5),
    UNIQUE(teacher_id, subject_id)
);

CREATE TABLE IF NOT EXISTS teacher_availabilities (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    period_index INTEGER NOT NULL CHECK (period_index >= 0),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    UNIQUE(teacher_id, day_of_week, period_index)
);

CREATE TABLE IF NOT EXISTS teacher_preferences (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    period_index INTEGER NOT NULL CHECK (period_index >= 0),
    preference_weight INTEGER NOT NULL DEFAULT 0 CHECK (preference_weight BETWEEN -10 AND 10),
    UNIQUE(teacher_id, day_of_week, period_index)
);

CREATE TABLE IF NOT EXISTS teacher_workload_rules (
    id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL UNIQUE REFERENCES teachers(id) ON DELETE CASCADE,
    max_periods_per_week INTEGER NOT NULL DEFAULT 20 CHECK (max_periods_per_week >= 0),
    min_periods_per_week INTEGER NOT NULL DEFAULT 0 CHECK (min_periods_per_week >= 0),
    max_periods_per_day INTEGER NOT NULL DEFAULT 5 CHECK (max_periods_per_day >= 1),
    max_consecutive_periods INTEGER NOT NULL DEFAULT 3 CHECK (max_consecutive_periods >= 1)
);

-- 3. Subjects & Offerings
CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    credits REAL NOT NULL DEFAULT 3.0 CHECK (credits >= 0.0),
    is_elective INTEGER NOT NULL DEFAULT 0 CHECK (is_elective IN (0, 1)),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(department_id, code)
);

CREATE TABLE IF NOT EXISTS subject_offerings (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    semester_id TEXT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    weekly_contact_hours REAL NOT NULL CHECK (weekly_contact_hours > 0.0),
    weekly_periods INTEGER NOT NULL CHECK (weekly_periods > 0),
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(subject_id, semester_id)
);

CREATE TABLE IF NOT EXISTS subject_session_requirements (
    id TEXT PRIMARY KEY,
    offering_id TEXT NOT NULL REFERENCES subject_offerings(id) ON DELETE CASCADE,
    session_type TEXT NOT NULL DEFAULT 'THEORY',
    consecutive_periods INTEGER NOT NULL DEFAULT 1 CHECK (consecutive_periods >= 1),
    frequency_per_week INTEGER NOT NULL DEFAULT 1 CHECK (frequency_per_week >= 1),
    requires_lab INTEGER NOT NULL DEFAULT 0 CHECK (requires_lab IN (0, 1)),
    preferred_room_type TEXT
);

CREATE TABLE IF NOT EXISTS class_subject_assignments (
    id TEXT PRIMARY KEY,
    class_group_id TEXT NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    offering_id TEXT NOT NULL REFERENCES subject_offerings(id) ON DELETE CASCADE,
    primary_teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    secondary_teacher_id TEXT REFERENCES teachers(id) ON DELETE SET NULL,
    student_group_id TEXT REFERENCES student_groups(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(class_group_id, offering_id, student_group_id)
);

-- 4. Rooms & Resources
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    room_type TEXT NOT NULL DEFAULT 'LECTURE_HALL',
    capacity INTEGER NOT NULL DEFAULT 40 CHECK (capacity >= 1),
    building TEXT,
    floor INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS room_availabilities (
    id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    period_index INTEGER NOT NULL CHECK (period_index >= 0),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0, 1)),
    UNIQUE(room_id, day_of_week, period_index)
);

-- 5. Timetables & Placed Sessions
CREATE TABLE IF NOT EXISTS timetables (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    academic_year_id TEXT NOT NULL REFERENCES academic_years(id) ON DELETE CASCADE,
    semester_id TEXT NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    is_published INTEGER NOT NULL DEFAULT 0 CHECK (is_published IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduled_sessions (
    id TEXT PRIMARY KEY,
    timetable_id TEXT NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
    class_subject_assignment_id TEXT NOT NULL REFERENCES class_subject_assignments(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_period INTEGER NOT NULL CHECK (start_period >= 0),
    duration_periods INTEGER NOT NULL DEFAULT 1 CHECK (duration_periods >= 1),
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    class_group_id TEXT NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    secondary_teacher_id TEXT REFERENCES teachers(id) ON DELETE SET NULL,
    student_group_id TEXT REFERENCES student_groups(id) ON DELETE SET NULL,
    is_locked INTEGER NOT NULL DEFAULT 0 CHECK (is_locked IN (0, 1)),
    created_at TEXT DEFAULT (datetime('now'))
);

-- 6. Validation, Reporting & Audit Logs
CREATE TABLE IF NOT EXISTS scheduling_runs (
    id TEXT PRIMARY KEY,
    timetable_id TEXT NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
    solver_status TEXT NOT NULL,
    execution_time_seconds REAL NOT NULL DEFAULT 0.0,
    objective_value REAL DEFAULT 0.0,
    total_sessions_scheduled INTEGER NOT NULL DEFAULT 0,
    run_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    configuration_snapshot_json TEXT
);

CREATE TABLE IF NOT EXISTS conflict_records (
    id TEXT PRIMARY KEY,
    timetable_id TEXT NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
    violation_type TEXT NOT NULL,
    is_hard INTEGER NOT NULL DEFAULT 1 CHECK (is_hard IN (0, 1)),
    severity TEXT NOT NULL DEFAULT 'ERROR',
    message TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS timetable_change_logs (
    id TEXT PRIMARY KEY,
    timetable_id TEXT NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details_json TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================================
-- Indexes for High-Performance Queries
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_dept_institution ON departments(institution_id);
CREATE INDEX IF NOT EXISTS idx_semesters_year ON semesters(academic_year_id);
CREATE INDEX IF NOT EXISTS idx_class_groups_dept ON class_groups(department_id, semester_id);
CREATE INDEX IF NOT EXISTS idx_teachers_dept ON teachers(department_id);
CREATE INDEX IF NOT EXISTS idx_teacher_qual_teacher ON teacher_qualifications(teacher_id);
CREATE INDEX IF NOT EXISTS idx_teacher_avail_lookup ON teacher_availabilities(teacher_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_subjects_dept ON subjects(department_id);
CREATE INDEX IF NOT EXISTS idx_offerings_sub ON subject_offerings(subject_id, semester_id);
CREATE INDEX IF NOT EXISTS idx_csa_class ON class_subject_assignments(class_group_id);
CREATE INDEX IF NOT EXISTS idx_csa_teacher ON class_subject_assignments(primary_teacher_id);
CREATE INDEX IF NOT EXISTS idx_timetables_sem ON timetables(semester_id, is_published);
CREATE INDEX IF NOT EXISTS idx_sessions_timetable ON scheduled_sessions(timetable_id);
CREATE INDEX IF NOT EXISTS idx_sessions_teacher ON scheduled_sessions(timetable_id, teacher_id, day_of_week, start_period);
CREATE INDEX IF NOT EXISTS idx_sessions_room ON scheduled_sessions(timetable_id, room_id, day_of_week, start_period);
CREATE INDEX IF NOT EXISTS idx_sessions_class ON scheduled_sessions(timetable_id, class_group_id, day_of_week, start_period);
CREATE INDEX IF NOT EXISTS idx_conflicts_timetable ON conflict_records(timetable_id);
CREATE INDEX IF NOT EXISTS idx_audit_timetable ON timetable_change_logs(timetable_id);
