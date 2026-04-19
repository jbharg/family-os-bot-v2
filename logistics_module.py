"""
logistics_module.py — Reads and filters logistics, transportation, and household tasks.

Provides categorized views of logistics data:
  - transportation: car, scheduling, and travel-related items
  - household_today: household/admin items due today
  - household_week: household/admin items due later this week
  - errands: grouped errand items due this week

Items marked status="done" are always excluded.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from data_loader import load_json

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"critical": 0, "important": 1, "light": 2}
TRANSPORTATION_CATEGORIES = {"transportation", "car", "travel", "scheduling"}
HOUSEHOLD_CATEGORIES = {"household", "admin", "home"}
ERRAND_CATEGORIES = {"errand", "errands"}


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        logger.debug(f"Could not parse date: {date_str!r}")
        return None


def _is_due_today(item: dict, today: date) -> bool:
    """Return True if the item is due on today's date or weekday."""
    due_date = _parse_date(item.get("due_date"))
    if due_date and due_date == today:
        return True
    due_day = item.get("due_day", "")
    if due_day and due_day.lower() == today.strftime("%A").lower():
        return True
    # Overdue items surface as due today
    if due_date and due_date < today:
        return True
    return False


def _is_due_this_week(item: dict, today: date) -> bool:
    """Return True if the item is due within the next 7 days (inclusive of today)."""
    week_end = today + timedelta(days=7)

    due_date = _parse_date(item.get("due_date"))
    if due_date and due_date <= week_end:
        # Include overdue items (past due but not done)
        return True

    due_day = item.get("due_day", "")
    if due_day:
        for offset in range(8):
            candidate = today + timedelta(days=offset)
            if candidate.strftime("%A").lower() == due_day.lower():
                return True

    if item.get("recurrence") in ("daily", "weekly") and item.get("status") != "done":
        return True

    return False


def get_logistics_summary(today: Optional[date] = None) -> dict:
    """Return a structured summary of logistics tasks for digest building.

    Returns:
        dict with keys:
            transportation  — transport/scheduling items due this week
            household_today — household/admin items due today (incl. overdue)
            household_week  — household/admin items due later this week
            errands         — errand items due this week
    """
    if today is None:
        today = date.today()

    data = load_json("logistics.json", default={"items": []})
    # Exclude completed items upfront
    items = [i for i in data.get("items", []) if i.get("status") != "done"]

    def _sort(lst: list) -> list:
        return sorted(lst, key=lambda x: PRIORITY_ORDER.get(x.get("priority", "light"), 2))

    transportation = _sort([
        i for i in items
        if i.get("category", "").lower() in TRANSPORTATION_CATEGORIES
        and _is_due_this_week(i, today)
    ])

    household_today = _sort([
        i for i in items
        if i.get("category", "").lower() in HOUSEHOLD_CATEGORIES
        and _is_due_today(i, today)
    ])

    household_week = _sort([
        i for i in items
        if i.get("category", "").lower() in HOUSEHOLD_CATEGORIES
        and not _is_due_today(i, today)
        and _is_due_this_week(i, today)
    ])

    errands = _sort([
        i for i in items
        if i.get("category", "").lower() in ERRAND_CATEGORIES
        and _is_due_this_week(i, today)
    ])

    logger.info(
        f"Logistics summary — transportation: {len(transportation)}, "
        f"household today: {len(household_today)}, "
        f"household week: {len(household_week)}, errands: {len(errands)}"
    )

    return {
        "transportation": transportation,
        "household_today": household_today,
        "household_week": household_week,
        "errands": errands,
    }
