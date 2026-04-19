"""
admissions_module.py — Reads and filters Sarah's admissions tasks.

Key features:
  - AP exam protection window: if today falls within a configured AP window,
    only critical items are surfaced; non-essential load is suppressed.
  - Upcoming deadlines: items due within the next 14 days.
  - Watchouts: items tagged "watchout" or critical items with no fixed due date.

AP windows are configured as a list in admissions.json under the key "ap_windows",
each with "start" and "end" as ISO date strings.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from data_loader import load_json

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "important": 1, "light": 2}
DEADLINE_LOOKAHEAD_DAYS = 14


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        logger.debug(f"Could not parse date: {date_str!r}")
        return None


def _in_ap_window(today: date, ap_windows: list) -> bool:
    """Return True if today falls within any configured AP exam protection window."""
    for window in ap_windows:
        start = _parse_date(window.get("start"))
        end = _parse_date(window.get("end"))
        if start and end and start <= today <= end:
            logger.info(
                f"AP protection window active: {start} – {end}"
            )
            return True
    return False


def get_admissions_summary(today: Optional[date] = None) -> dict:
    """Return a structured summary of admissions tasks for digest building.

    During AP exam protection windows, only critical tasks are surfaced.
    Items marked protected_during_ap_window=true are suppressed unless critical.

    Returns:
        dict with keys:
            top_items          — highest-priority active items (up to 4)
            upcoming_deadlines — items due within 14 days, sorted by date
            watchouts          — items needing passive monitoring
            in_ap_window       — bool, True if AP protection is currently active
    """
    if today is None:
        today = date.today()

    data = load_json("admissions.json", default={"items": [], "ap_windows": []})
    items = data.get("items", [])
    ap_windows = data.get("ap_windows", [])

    in_ap_window = _in_ap_window(today, ap_windows)
    if in_ap_window:
        logger.info("AP exam protection window active — suppressing non-urgent admissions tasks.")

    # Filter to active (not done) items, applying AP window suppression
    active_items = [i for i in items if i.get("status") != "done"]

    if in_ap_window:
        # Only show critical items during AP window; suppress others
        active_items = [
            i for i in active_items
            if i.get("priority") == "critical"
        ]

    # Top items sorted by priority
    sorted_items = sorted(
        active_items,
        key=lambda x: PRIORITY_ORDER.get(x.get("priority", "light"), 2),
    )

    # Upcoming deadlines within lookahead window
    deadline_cutoff = today + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)
    upcoming_deadlines = sorted(
        [
            i for i in active_items
            if _parse_date(i.get("due_date")) is not None
            and today <= _parse_date(i.get("due_date")) <= deadline_cutoff
        ],
        key=lambda x: _parse_date(x.get("due_date")) or date(2099, 1, 1),
    )

    # Watchouts: explicitly tagged, or critical items with no due date
    watchouts = [
        i for i in active_items
        if "watchout" in i.get("tags", [])
        or (i.get("priority") == "critical" and not i.get("due_date"))
    ]

    logger.info(
        f"Admissions summary — active: {len(sorted_items)}, "
        f"upcoming deadlines: {len(upcoming_deadlines)}, "
        f"watchouts: {len(watchouts)}, ap_window: {in_ap_window}"
    )

    return {
        "top_items": sorted_items[:4],
        "upcoming_deadlines": upcoming_deadlines[:5],
        "watchouts": watchouts[:3],
        "in_ap_window": in_ap_window,
    }
