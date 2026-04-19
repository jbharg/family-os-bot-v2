"""
routing_engine.py — Surfaces the right tasks for each digest section.

Receives tasks already enriched with effective_state by state_engine.
Returns structured section dicts that digest_builder renders into HTML.

All business logic lives here. digest_builder does rendering only.

AP window logic: during a configured AP exam window, tasks marked
protected_during_ap_window=true are suppressed unless they are critical.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from data_loader import load_json

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"critical": 0, "important": 1, "light": 2}
_DEADLINE_LOOKAHEAD_DAYS = 14
_STALE_WAITING_SURFACE_LIMIT = 2
_MUST_DO_LIMIT = 5
_ADMISSIONS_FOCUS_LIMIT = 2
_TODAY_LIMIT = 4
_WEEK_LIMIT = 4
_WATCHOUT_OVERDUE_LIMIT = 2
_WATCHOUT_DEADLINE_LIMIT = 2
_CRITICALS_WEEKLY_LIMIT = 6
_DEADLINES_WEEKLY_LIMIT = 6
_SARAH_LIMIT = 5
_WAITING_LIMIT = 4


def _sort(items: list) -> list:
    """Sort by priority descending (critical first)."""
    return sorted(items, key=lambda x: _PRIORITY_ORDER.get(x.get("priority", "light"), 2))


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _load_ap_windows() -> list:
    config = load_json("config.json", default={"ap_windows": []})
    return config.get("ap_windows", [])


def _in_ap_window(today: date, ap_windows: list) -> bool:
    """Return True if today falls within any configured AP exam protection window."""
    for window in ap_windows:
        start = _parse_date(window.get("start"))
        end = _parse_date(window.get("end"))
        if start and end and start <= today <= end:
            logger.info(f"AP protection window active: {start} to {end}")
            return True
    return False


def _suppress_for_ap(task: dict, in_ap: bool) -> bool:
    """Return True if this task should be hidden during an AP window.

    Critical tasks always surface. Only protected non-critical tasks are suppressed.
    """
    if not in_ap:
        return False
    if task.get("priority") == "critical":
        return False
    return task.get("protected_during_ap_window", False)


def route_daily(tasks: list, today: date) -> dict:
    """Build section data for the Daily Digest.

    Returns a dict with keys:
        must_do           — top critical items due today or overdue, max 5
        admissions_focus  — top admissions items (any priority), max 2
        today_items       — remaining today items, max 4
        week_items        — this_week items, max 4
        watchouts         — overdue overflow + stale waiting + upcoming deadlines
        in_ap_window      — bool
    """
    ap_windows = _load_ap_windows()
    in_ap = _in_ap_window(today, ap_windows)

    active = [
        t for t in tasks
        if t.get("effective_state") != "done"
        and not _suppress_for_ap(t, in_ap)
    ]

    # ── Must Do ───────────────────────────────────────────────────────────────
    # Critical tasks that are due today or already overdue
    must_do = _sort([
        t for t in active
        if t.get("effective_state") in ("today", "overdue")
        and t.get("priority") == "critical"
    ])[:_MUST_DO_LIMIT]
    must_do_ids = {t["id"] for t in must_do}

    # ── Admissions Focus ──────────────────────────────────────────────────────
    # Admissions domain items not already in Must Do, any priority
    admissions_focus = _sort([
        t for t in active
        if t.get("domain") == "admissions"
        and t.get("effective_state") in ("today", "this_week", "inbox")
        and t["id"] not in must_do_ids
    ])[:_ADMISSIONS_FOCUS_LIMIT]
    admissions_ids = {t["id"] for t in admissions_focus}

    # ── Today ─────────────────────────────────────────────────────────────────
    # Remaining today items not already surfaced
    today_items = _sort([
        t for t in active
        if t.get("effective_state") == "today"
        and t["id"] not in must_do_ids
        and t["id"] not in admissions_ids
    ])[:_TODAY_LIMIT]
    today_ids = {t["id"] for t in today_items}

    # ── This Week ─────────────────────────────────────────────────────────────
    shown_ids = must_do_ids | admissions_ids | today_ids
    week_items = _sort([
        t for t in active
        if t.get("effective_state") == "this_week"
        and t["id"] not in shown_ids
    ])[:_WEEK_LIMIT]
    week_ids = {t["id"] for t in week_items}

    # ── Watchouts ─────────────────────────────────────────────────────────────
    all_shown = shown_ids | week_ids

    overdue_watchouts = _sort([
        t for t in active
        if t.get("effective_state") == "overdue"
        and t["id"] not in all_shown
    ])[:_WATCHOUT_OVERDUE_LIMIT]

    stale_waiting = [
        t for t in active
        if t.get("stale_waiting")
    ][:_STALE_WAITING_SURFACE_LIMIT]

    deadline_cutoff = today + timedelta(days=_DEADLINE_LOOKAHEAD_DAYS)
    deadline_watchouts = sorted(
        [
            t for t in active
            if _parse_date(t.get("due_date")) is not None
            and today < _parse_date(t.get("due_date")) <= deadline_cutoff
            and t["id"] not in all_shown
        ],
        key=lambda x: _parse_date(x.get("due_date")) or date(2099, 1, 1),
    )[:_WATCHOUT_DEADLINE_LIMIT]

    watchouts = overdue_watchouts + stale_waiting + deadline_watchouts

    logger.info(
        f"Daily routing — must_do: {len(must_do)}, admissions: {len(admissions_focus)}, "
        f"today: {len(today_items)}, week: {len(week_items)}, watchouts: {len(watchouts)}, "
        f"ap_window: {in_ap}"
    )

    return {
        "must_do": must_do,
        "admissions_focus": admissions_focus,
        "today_items": today_items,
        "week_items": week_items,
        "watchouts": watchouts,
        "in_ap_window": in_ap,
    }


def route_weekly(tasks: list, today: date) -> dict:
    """Build section data for the Weekly Reset.

    Returns a dict with keys:
        criticals           — all critical active tasks, max 6
        deadlines           — tasks with due_date within 14 days, max 6
        sarah_items         — tasks owned by Sarah, max 5
        waiting_items       — tasks in waiting state, max 4
        suggested_order     — list of plain-text priority suggestions
        planning_questions  — list of plain-text planning prompts
        in_ap_window        — bool
    """
    ap_windows = _load_ap_windows()
    in_ap = _in_ap_window(today, ap_windows)

    active = [
        t for t in tasks
        if t.get("effective_state") != "done"
        and not _suppress_for_ap(t, in_ap)
    ]

    criticals = _sort([
        t for t in active
        if t.get("priority") == "critical"
    ])[:_CRITICALS_WEEKLY_LIMIT]

    deadline_cutoff = today + timedelta(days=_DEADLINE_LOOKAHEAD_DAYS)
    deadlines = sorted(
        [
            t for t in active
            if _parse_date(t.get("due_date")) is not None
            and _parse_date(t.get("due_date")) <= deadline_cutoff
        ],
        key=lambda x: _parse_date(x.get("due_date")) or date(2099, 1, 1),
    )[:_DEADLINES_WEEKLY_LIMIT]

    sarah_items = _sort([
        t for t in active
        if t.get("owner", "").lower() == "sarah"
    ])[:_SARAH_LIMIT]

    waiting_items = [
        t for t in active
        if t.get("effective_state") == "waiting"
    ][:_WAITING_LIMIT]

    suggested_order = _build_suggested_order(active)
    planning_questions = _build_planning_questions(active, today)

    logger.info(
        f"Weekly routing — criticals: {len(criticals)}, deadlines: {len(deadlines)}, "
        f"sarah: {len(sarah_items)}, waiting: {len(waiting_items)}, ap_window: {in_ap}"
    )

    return {
        "criticals": criticals,
        "deadlines": deadlines,
        "sarah_items": sarah_items,
        "waiting_items": waiting_items,
        "suggested_order": suggested_order,
        "planning_questions": planning_questions,
        "in_ap_window": in_ap,
    }


def _build_suggested_order(active: list) -> list:
    """Generate a short ordered list of plain-text action priorities."""
    order = []

    if any(t.get("effective_state") == "overdue" for t in active):
        order.append("Resolve overdue items first — they are blocking forward motion")
    if any(t.get("domain") == "care" and t.get("priority") == "critical" for t in active):
        order.append("Complete core care tasks early in the week")
    if any(t.get("domain") == "admissions" and t.get("priority") == "critical" for t in active):
        order.append("Handle urgent admissions deadlines next")
    if any(t.get("domain") in ("logistics", "household") for t in active):
        order.append("Confirm transportation and household tasks mid-week")
    if any(t.get("effective_state") == "waiting" for t in active):
        order.append("Follow up on stale waiting items before the week closes")
    if not order:
        order.append("Light week — stay ahead without overloading yourself")

    return order


def _build_planning_questions(active: list, today: date) -> list:
    """Generate up to 4 planning questions based on what is open."""
    questions = []

    if any(t.get("owner", "").lower() == "sarah" for t in active):
        questions.append("Is Sarah's load manageable this week?")
    if any(t.get("domain") == "admissions" and t.get("due_date") for t in active):
        questions.append("Which admissions deadline matters most this week?")
    if any(t.get("domain") == "care" and t.get("priority") == "critical" for t in active):
        questions.append("What care task needs to happen first so the week feels steadier?")
    if any(t.get("effective_state") == "waiting" for t in active):
        questions.append("Which waiting items need a follow-up nudge this week?")
    if len(questions) < 3:
        questions.append("Is there anything new that should be captured into the system?")

    return questions[:4]
