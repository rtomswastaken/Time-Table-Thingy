"""Default application configurations and preset values."""

from core.models import SchedulingConfig

# Default working cycle: Monday to Friday (5 days), 6 periods per day, 60 minutes each
DEFAULT_WORKING_DAYS = [0, 1, 2, 3, 4]  # 0=Monday, 4=Friday
DEFAULT_PERIODS_PER_DAY = 6
DEFAULT_PERIOD_DURATION_MINUTES = 60
DEFAULT_BREAK_PERIODS = {3}  # Period index 3 (e.g. Lunch after 3 periods)

# Default Solver Settings
DEFAULT_SCHEDULING_CONFIG = SchedulingConfig(
    time_limit_seconds=60.0,
    random_seed=42,
    allow_partial_solution=False,
    weight_teacher_preference=10,
    weight_minimize_teacher_gaps=15,
    weight_minimize_student_gaps=20,
    weight_preferred_room=5,
    weight_balanced_daily_load=10,
)

# Standard Database File Path
DEFAULT_DB_FILENAME = "timetable_thingy.db"
