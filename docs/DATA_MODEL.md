# Timetable Thingy - Domain Data Model Specification

## 1. Domain Modeling Principles & Foundations

To ensure Agent 2 (Database), Agent 3 (Academic), Agent 4 (Workload), Agent 5 (Solver), and Agent 6 (Grid) operate on identical assumptions, the core domain entities must strictly separate physical structures, academic curricula, resource allocations, and temporal schedules.

### Key Conceptual Distinctions
1. **Academic Credits vs. Weekly Contact Hours**:
   - `Subject.credits` represents academic weighting (e.g., 3 credits).
   - `Subject.contact_hours` represents weekly classroom hours (e.g., 4 or 5 hours/week).
   - `Subject.period_count` represents how many discrete timetable periods this requires per week, based on the standard period duration (e.g., a 60-minute period vs. a 45-minute period).
2. **Subject vs. SubjectOffering**:
   - `Subject`: Master catalog definition (e.g., "CS101 - Intro to Programming", 3 credits).
   - `SubjectOffering`: The offering of a Subject in a specific Semester/Academic Year with dedicated session requirements (e.g., 3 Theory lectures + 1 two-period Lab block).
3. **ClassGroup vs. StudentGroup**:
   - `ClassGroup`: A cohort/section (e.g., "Semester 3 Computer Science - Section A", 60 students).
   - `StudentGroup`: A partition or lab batch within a ClassGroup (e.g., "Batch A1", 30 students) for practicals, or combined batches across sections.
4. **Teacher vs. TeacherQualification**:
   - `Teacher`: Personal and institutional identity (e.g., Dr. Alice Smith, full-time).
   - `TeacherQualification`: Certification or permission matrix indicating which subjects a teacher can teach, optionally with preference or competency tiers.
5. **ScheduledSession vs. Recurring Weekly Timetable Assignment**:
   - All institutional schedules in this application are modeled as **weekly recurring cycles** (e.g., "Every Monday Period 1"). A `ScheduledSession` represents this weekly recurring placement.
6. **Hard Constraints vs. Soft Preferences**:
   - `Hard Constraints`: Non-negotiable physical and administrative laws (no double booking, teacher availability, room capacity, lab block continuity). Any violation renders a schedule invalid.
   - `Soft Preferences`: Desirable optimization goals (morning slots for theory, teacher day-off preferences, minimize gaps in student schedule). Scored via penalty weights.
7. **Timetable Draft vs. Published Timetable**:
   - A `Draft` is an active workspace undergoing manual or automated solver modifications.
   - A `Published` timetable is immutable and active for institutional viewing/export until explicitly cloned into a new draft version.

---

## 2. Entity Specifications

All primary keys use UUID strings (`str`) or structured slugs to support local generation without database auto-increment dependency.

### 2.1 Institution & Academic Structure

#### `Institution`
Represents the educational entity (school, university, polytechnic).
- `id: str` (UUID)
- `name: str` (e.g., "St. Jude Institute of Technology")
- `code: str` (e.g., "SJIT")
- `working_days: list[int]` (0=Monday ... 6=Sunday; default: `[0, 1, 2, 3, 4]`)
- `periods_per_day: int` (e.g., 6 or 8)
- `period_duration_minutes: int` (e.g., 60 or 50)
- `created_at: str` (ISO 8601)

#### `Department`
Academic division within an institution.
- `id: str` (UUID)
- `institution_id: str` (FK -> Institution)
- `name: str` (e.g., "Computer Science & Engineering")
- `code: str` (e.g., "CSE")

#### `AcademicYear`
Active cycle of study.
- `id: str` (UUID)
- `name: str` (e.g., "2026-2027")
- `start_date: str` (YYYY-MM-DD)
- `end_date: str` (YYYY-MM-DD)
- `is_current: bool`

#### `Semester`
Sub-period within an academic year.
- `id: str` (UUID)
- `academic_year_id: str` (FK -> AcademicYear)
- `number: int` (e.g., 1, 2, 3, 4, 5, 6, 7, 8)
- `term_name: str` (e.g., "Fall 2026", "Odd Semester")

#### `ClassGroup`
A primary cohort of students following a common syllabus.
- `id: str` (UUID)
- `department_id: str` (FK -> Department)
- `semester_id: str` (FK -> Semester)
- `name: str` (e.g., "CS-3A", "S3 AD")
- `student_count: int` (Total cohort size)
- `home_room_id: Optional[str]` (Default assigned classroom)

#### `StudentGroup`
Sub-division of a ClassGroup for laboratory, tutorial, or elective tracks.
- `id: str` (UUID)
- `class_group_id: str` (FK -> ClassGroup)
- `name: str` (e.g., "Batch 1", "Group A")
- `student_count: int` (e.g., 30)

---

### 2.2 Faculty & Preferences

#### `Teacher`
Faculty member.
- `id: str` (UUID)
- `department_id: str` (FK -> Department)
- `name: str` (e.g., "Dr. Alan Turing")
- `employee_id: str` (Unique institutional identifier)
- `email: Optional[str]`
- `is_full_time: bool` (default True)

#### `TeacherQualification`
Subject eligibility mapping.
- `id: str` (UUID)
- `teacher_id: str` (FK -> Teacher)
- `subject_id: str` (FK -> Subject)
- `competency_level: int` (1=Primary, 2=Secondary/Backup)
- `preference_score: int` (1 to 5, where 5 is highly preferred)

#### `TeacherAvailability`
Hard temporal availability constraints.
- `id: str` (UUID)
- `teacher_id: str` (FK -> Teacher)
- `day_of_week: int` (0..6)
- `period_index: int` (0..periods_per_day - 1)
- `is_available: bool` (False = Hard constraint: teacher cannot teach during this slot)

#### `TeacherPreference`
Soft temporal preferences for faculty happiness.
- `id: str` (UUID)
- `teacher_id: str` (FK -> Teacher)
- `day_of_week: int` (0..6)
- `period_index: int`
- `preference_weight: int` (-10 to +10, e.g., -5 for "prefers not", +5 for "strongly prefers")

#### `TeacherWorkloadRule`
Contractual and pedagogical teaching load restrictions.
- `id: str` (UUID)
- `teacher_id: str` (FK -> Teacher)
- `max_periods_per_week: int` (e.g., 18 periods)
- `min_periods_per_week: int` (e.g., 12 periods)
- `max_periods_per_day: int` (e.g., 4 periods)
- `max_consecutive_periods: int` (e.g., 2 periods without break)

---

### 2.3 Subjects & Curricular Offerings

#### `Subject`
Master course catalog record.
- `id: str` (UUID)
- `department_id: str` (FK -> Department)
- `code: str` (e.g., "CS301")
- `name: str` (e.g., "Data Structures and Algorithms")
- `credits: float` (e.g., 4.0)
- `is_elective: bool` (default False)

#### `SubjectOffering`
The instantiation of a subject in a semester.
- `id: str` (UUID)
- `subject_id: str` (FK -> Subject)
- `semester_id: str` (FK -> Semester)
- `weekly_contact_hours: float` (e.g., 5.0)
- `weekly_periods: int` (e.g., 5)

#### `SubjectSessionRequirement`
Specifies how a subject's weekly periods must be broken down into discrete sessions.
- `id: str` (UUID)
- `offering_id: str` (FK -> SubjectOffering)
- `session_type: SessionType` (`THEORY`, `LABORATORY`, `PRACTICAL`, `TUTORIAL`, `SEMINAR`, `PROJECT`)
- `consecutive_periods: int` (e.g., 1 for Theory; 2 or 3 for Lab)
- `frequency_per_week: int` (e.g., 3 single Theory sessions + 1 double Lab session)
- `requires_lab: bool`
- `preferred_room_type: Optional[RoomType]`

#### `ClassSubjectAssignment`
Assignment linking class cohort, subject offering, and designated faculty.
- `id: str` (UUID)
- `class_group_id: str` (FK -> ClassGroup)
- `offering_id: str` (FK -> SubjectOffering)
- `primary_teacher_id: str` (FK -> Teacher)
- `secondary_teacher_id: Optional[str]` (For co-taught labs)
- `student_group_id: Optional[str]` (If assigned to a subset/batch)

---

### 2.4 Physical Resources

#### `Room`
Physical scheduling facility.
- `id: str` (UUID)
- `name: str` (e.g., "Room 304", "AI Computing Lab")
- `code: str` (e.g., "R-304")
- `room_type: RoomType` (`LECTURE_HALL`, `COMPUTER_LAB`, `HARDWARE_LAB`, `SEMINAR_ROOM`, `WORKSHOP`)
- `capacity: int` (Max seats)
- `building: Optional[str]`
- `floor: Optional[int]`

#### `RoomAvailability`
Hard availability restriction for maintenance or shared bookings.
- `id: str` (UUID)
- `room_id: str` (FK -> Room)
- `day_of_week: int`
- `period_index: int`
- `is_available: bool`

---

### 2.5 Timetable & Assignments

#### `TimeSlot`
A discrete atomic schedulable interval in the recurring weekly grid.
- `day_of_week: int` (0=Monday ... 4=Friday / 6=Sunday)
- `period_index: int` (0 .. N-1)
- `start_time: str` (e.g., "09:00")
- `end_time: str` (e.g., "10:00")
- `is_break: bool` (e.g., lunch hour or recess)

#### `ScheduledSession`
A placed session assignment in the recurring weekly timetable.
- `id: str` (UUID)
- `timetable_id: str` (FK -> Timetable)
- `class_subject_assignment_id: str` (FK -> ClassSubjectAssignment)
- `day_of_week: int`
- `start_period: int`
- `duration_periods: int` (1 for single, 2 for double lab, etc.)
- `room_id: str` (FK -> Room)
- `teacher_id: str` (FK -> Teacher)
- `class_group_id: str` (FK -> ClassGroup)
- `student_group_id: Optional[str]`
- `is_locked: bool` (True if pinned by user; solver cannot move it)

#### `Timetable`
Container for a complete institutional schedule.
- `id: str` (UUID)
- `name: str` (e.g., "Odd Semester 2026 Schedule - Final Draft")
- `academic_year_id: str`
- `semester_id: str`
- `version: int` (e.g., 1, 2, 3)
- `is_published: bool` (False = Draft)
- `created_at: str`
- `updated_at: str`

#### `LockedAssignment`
An immutable slot anchor requested by the user.
- `assignment_id: str`
- `day_of_week: int`
- `start_period: int`
- `room_id: Optional[str]`

---

### 2.6 Validation & Metrics

#### `ConstraintViolation`
Structured report for validation failures.
- `violation_type: ConstraintType`
- `is_hard: bool`
- `severity: str` ("ERROR" for hard, "WARNING" for soft)
- `message: str`
- `involved_sessions: list[str]` (IDs of conflicting sessions)
- `involved_teachers: list[str]`
- `involved_rooms: list[str]`
- `involved_classes: list[str]`

#### `OptimizationMetrics`
Quantitative evaluation of a timetable's quality.
- `total_hard_violations: int` (Must be 0 for valid schedule)
- `soft_penalty_score: float` (Lower is better)
- `teacher_idle_gaps: int` (Number of empty window periods for teachers)
- `student_idle_gaps: int`
- `faculty_preference_satisfaction_rate: float` (0.0 to 1.0)
- `room_utilization_percentage: float`
- `solver_runtime_seconds: float`
