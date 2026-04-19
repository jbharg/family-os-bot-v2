"""
state_engine.py — Compute effective task states at runtime.

Does NOT write to disk. Reads declared states from tasks.json and overlays
date-based logic to produce an effective_state for each task.

Simplified state model (v2):
  inbox      — captured, not yet triaged or scheduled
  today      — must happen today
  this_week  — relevant this week, not urgent today
  waiting    — blocked on someone else
  done       — completed (terminal)
  overdue    — past due date and not done

Rule order (first match wins):
  1. done    → done (terminal, no override)
  2. specific due_date in the past (no recurrence) → overdue
  3. due_day == "daily" → today
  4. due_day matches today's weekday → today
  5. specific due_date == today → today
  6. critical priority + due_date within 2 days → today (urgent promotion)
  7. due_date within 7 days → this_week
  8. declared state used as-is
"""

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# All valid states in the v2 model
VALID_STATES = {"inbox", "today", "this_week", "waiting", "done", "overdue"}

# Weekday names in Python weekday() order (Monday=0, Sunday=6)
_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]

# Days without an update before a waiting task is flagged as stale
_STALE_WAITING_DAYS = 14

# Days within which a critical task is force-promoted to "today"
_CRITICAL_URGENCY_DAYS = 2


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD). Returns None on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def compute_effective_state(task: dict, today: date) -> str:
    """Return the effective state for a single task.

    Applies date and priority rules on top of the declared state field.
    The declared state is used as the final fallback.
    """
    declared = task.get("state", "inbox")

    # Rule 1: done is terminal
    if declared == "done":
        return "done"

    due_date = _parse_date(task.get("due_date"))
    due_day = (task.get("due_day") or "").strip()

    # Rule 2: specific due_date in the past, non-recurring → overdue
    if due_date and due_date < today and not due_day:
        return "overdue"

    # Rule 3: daily recurrence → always today
    if due_day.lower() == "daily":
        return "today"

    # Rule 4: weekday recurrence matches today → today
    if due_day:
        try:
            target_idx = _DAY_NAMES.index(due_day.capitalize())
            days_until = (target_idx - today.weekday()) % 7
            if days_until == 0:
                return "today"
            else:
                # Any non-today weekday recurrence is this_week
                return "this_week"
        except ValueError:
            # Unrecognized due_day string — fall through
            pass

    # Rule 5: specific due_date is today
    if due_date and due_date == today:
        return "today"

    # Rule 6: critical + due within N days → promote to today
    if (
        task.get("priority") == "critical"
        and due_date
        and due_date <= today + timedelta(days=_CRITICAL_URGENCY_DAYS)
    ):
        return "today"

    # Rule 7: due within 7 days → this_week
    if due_date and due_date <= today + timedelta(days=7):
        return "this_week"

    # Rule 8: use declared state if valid, otherwise inbox
    return declared if declared in VALID_STATES else "inbox"


def is_stale_waiting(task: dict, today: date) -> bool:
    """Return True if a waiting task has not been updated in _STALE_WAITING_DAYS days."""
    if task.get("state") != "waiting":
        return False
    updated = (task.get("updated_at") or "")[:10]
    if not updated:
        return True
    try:
        updated_date = date.fromisoformat(updated)
        return (today - updated_date).days >= _STALE_WAITING_DAYS
    except (ValueError, TypeError):
        return True


def apply_states(tasks: list, today: date) -> list:
    """Return a new list of tasks, each enriched with effective_state and stale_waiting.

    Does not modify the input list or write to disk.
    """
    enriched = []
    counts = {"today": 0, "this_week": 0, "overdue": 0, "waiting": 0, "done": 0, "inbox": 0}

    for task in tasks:
        effective = compute_effective_state(task, today)
        stale = is_stale_waiting(task, today)
        enriched.append({**task, "effective_state": effective, "stale_waiting": stale})
        counts[effective] = counts.get(effective, 0) + 1

    logger.info(
        f"State engine: {len(enriched)} tasks — "
        + ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
    )
    return enriched
