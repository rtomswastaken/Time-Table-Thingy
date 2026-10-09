"""
UI Theme, styling constants, typography, and palette definitions for CustomTkinter screens.
Supports both dark and light modes cleanly.
"""

from typing import Tuple

# Color Palette (CustomTkinter light / dark tuples)
COLOR_BG_PRIMARY: Tuple[str, str] = ("#F8FAFC", "#0F172A")
COLOR_BG_SECONDARY: Tuple[str, str] = ("#FFFFFF", "#1E293B")
COLOR_BG_CARD: Tuple[str, str] = ("#FFFFFF", "#1E293B")
COLOR_BORDER: Tuple[str, str] = ("#E2E8F0", "#334155")

# Accent Colors
COLOR_PRIMARY: Tuple[str, str] = ("#2563EB", "#3B82F6")        # Blue
COLOR_PRIMARY_HOVER: Tuple[str, str] = ("#1D4ED8", "#2563EB")
COLOR_SUCCESS: Tuple[str, str] = ("#16A34A", "#22C55E")        # Green
COLOR_WARNING: Tuple[str, str] = ("#D97706", "#F59E0B")        # Amber
COLOR_DANGER: Tuple[str, str] = ("#DC2626", "#EF4444")         # Red
COLOR_DANGER_HOVER: Tuple[str, str] = ("#B91C1C", "#DC2626")

# Text Colors
COLOR_TEXT_PRIMARY: Tuple[str, str] = ("#0F172A", "#F8FAFC")
COLOR_TEXT_SECONDARY: Tuple[str, str] = ("#475569", "#94A3B8")
COLOR_TEXT_MUTED: Tuple[str, str] = ("#64748B", "#64748B")

# Typography
FONT_FAMILY: str = "Helvetica"
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 15, "bold")
FONT_SECTION = (FONT_FAMILY, 13, "bold")
FONT_BODY = (FONT_FAMILY, 12, "normal")
FONT_BODY_BOLD = (FONT_FAMILY, 12, "bold")
FONT_CAPTION = (FONT_FAMILY, 11, "normal")
FONT_ERROR = (FONT_FAMILY, 11, "normal")

# Spacing & Sizing
PADDING_TINY = 4
PADDING_SMALL = 8
PADDING_MEDIUM = 16
PADDING_LARGE = 24
CORNER_RADIUS_CARD = 8
CORNER_RADIUS_BUTTON = 6
CORNER_RADIUS_INPUT = 6
