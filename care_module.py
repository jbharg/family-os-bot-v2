"""
care_module.py — Reads and filters care-related tasks.

Provides three views of care data:
  - overdue: items past their due date and not marked done
  - due_today: items due on the current day (by date or weekday)
  - weekly_criticals: critical items due within the next 7 days

Recurrence support: daily items surface every day unless marked done.
Weekly items surface on their configured due_day.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from data_loader import load_json

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "important": 1, "light": 2}


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        logger.debug(f"Could not parse date: {date_str!r}")
        return None


def _is_overdue(item: dict, today: date) -> bool:
    """Return True if the item is past due and not completed."""
    if item.get("status") == "done":
        return False
    if item.get("status") == "overdue":
        return True
    due_date = _parse_date(item.get("due_date"))
    if due_date and due_date < today:
        return True
    return False


def _is_due_today(item: dict, today: date) -> bool:
    """Return True if the item is due on today's date or weekday."""
    # Specific date match
    due_date = _parse_date(item.get("due_date"))
    if due_date and due_date == today:
        return True

    # Weekday-based recurrence
    due_day = item.get("due_day", "")
    if due_day and due_day.lower() == today.strftime("%A").lower():
        return True

    # Daily recurrence always surfaces
    if item.get("recurrence") == "daily" and item.get("status") != "done":
        return True

    return False


def _is_due_this_week(item: dict, today: date) -> bool:
    """Return True if the item falls within the next 7 days."""
    week_end = today + timedelta(days=7)

    due_date = _parse_date(item.get("due_date"))
    if due_date and today < due_date <= week_end:
        return True

    due_day = item.get("due_day", "")
    if due_day:
        for offset in range(1, 8):
            candidate = today + timedelta(days=offset)
            if candidate.strftime("%A").lower() == due_day.lower():
                return True

    if item.get("recurrence") == "weekly" and item.get("status") != "done":
        return True

    return False


def get_care_summary(today: Optional[date] = None) -> dict:
    """Return a structured summary of care tasks for digest building.

    Returns:
        dict with keys:
            overdue       — items that are past due (sorted critical-first)
            due_today     — items due today, not overdue
            weekly_criticals — critical items due this week, not today
    """
    if today is None:
        today = date.today()

    data = load_json("care.json", default={"items": []})
    items = data.get("items", [])

    overdue = sorted(
        [i for i in items if _is_overdue(i, today)],
        key=lambda x: PRIORITY_ORDER.get(x.get("priority", "light"), 2),
    )

    due_today = sorted(
        [i for i in items if not _is_overdue(i, today) and _is_due_today(i, today)],
        key=lambda x: PRIORITY_ORDER.get(x.get("priority", "light"), 2),
    )

    weekly_criticals = sorted(
        [
            i for i in items
            if i.get("priority") == "critical"
            and i.get("status") != "done"
            and not _is_overdue(i, today)
            and not _is_due_today(i, today)
            and _is_due_this_week(i, today)
        ],
        key=lambda x: PRIORITY_ORDER.get(x.get("priority", "light"), 2),
    )

    logger.info(
        f"Care summary — overdue: {len(overdue)}, "
        f"due today: {len(due_today)}, weekly criticals: {len(weekly_criticals)}"
    )

    return {
        "overdue": overdue,
        "due_today": due_today,
        "weekly_criticals": weekly_criticals,
    }
