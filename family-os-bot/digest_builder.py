"""
digest_builder.py — Pure HTML renderer for Daily Digest and Weekly Reset emails.

Receives pre-filtered section data from routing_engine.
Contains NO business logic, NO task selection, NO priority decisions.
Only renders what it is given.

Mobile-first, inline styles only (for iPhone Mail compatibility).
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)

# ── Inline CSS ────────────────────────────────────────────────────────────────

_CSS = """
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif;
    font-size: 16px;
    line-height: 1.6;
    color: #171717;
    background: #ffffff;
    max-width: 580px;
    margin: 0 auto;
    padding: 24px 18px 32px 18px;
  }
  .header-title {
    font-size: 28px;
    font-weight: 700;
    color: #141414;
    margin: 0 0 4px 0;
    letter-spacing: -0.02em;
  }
  .header-date {
    font-size: 14px;
    color: #8b8b8b;
    margin: 0 0 26px 0;
  }
  .section-heading {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #7b7b7b;
    margin: 24px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #ececec;
  }
  ul { margin: 0; padding-left: 20px; }
  li { margin-bottom: 10px; font-size: 16px; }
  .badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 3px 7px;
    border-radius: 5px;
    margin-right: 7px;
    vertical-align: middle;
  }
  .badge-critical  { background: #fce3e3; color: #8a1f1f; }
  .badge-important { background: #fdf3cf; color: #6f5d00; }
  .badge-light     { background: #e8f2ff; color: #24558b; }
  .badge-overdue   { background: #c92a2a; color: #ffffff; }
  .badge-waiting   { background: #f0e6ff; color: #5b21b6; }
  .item-note {
    display: block;
    font-size: 13px;
    color: #7f7f7f;
    margin-top: 2px;
    padding-left: 2px;
    line-height: 1.45;
  }
  .due-label    { font-size: 12px; color: #a0a0a0; margin-left: 4px; }
  .action-label { font-size: 11px; color: #b0b0b0; margin-left: 6px; font-style: italic; }
  .ap-notice {
    font-size: 13px;
    color: #6f5d00;
    background: #fff7d6;
    padding: 9px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
  }
  .footer {
    margin-top: 32px;
    padding-top: 12px;
    border-top: 1px solid #ececec;
    font-size: 11px;
    color: #b5b5b5;
    text-align: center;
  }
  .no-items { font-size: 14px; color: #9a9a9a; font-style: italic; }
  .muted-li  { color: #888; font-style: italic; }
"""


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _wrap_html(title: str, subtitle: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{_CSS}</style>
</head>
<body>
  <p class="header-title">{title}</p>
  <p class="header-date">{subtitle}</p>
  {body}
  <div class="footer">Family OS v2 &middot; GitHub Actions</div>
</body>
</html>"""


def _badge(task: dict) -> str:
    """Render a priority or state badge for a task."""
    effective = task.get("effective_state", task.get("state", ""))
    priority = task.get("priority", "light")

    if effective == "overdue":
        return '<span class="badge badge-overdue">Overdue</span>'
    if effective == "waiting":
        return '<span class="badge badge-waiting">Waiting</span>'

    css_map = {"critical": "badge-critical", "important": "badge-important", "light": "badge-light"}
    css = css_map.get(priority, "badge-light")
    return f'<span class="badge {css}">{priority.capitalize()}</span>'


def _item_li(
    task: dict,
    show_badge: bool = True,
    show_due: bool = False,
    show_action: bool = False,
) -> str:
    """Render a single task as an HTML list item."""
    title = task.get("title", "(untitled)")
    notes = task.get("notes", "")

    badge_html = _badge(task) if show_badge else ""

    due_html = ""
    if show_due and task.get("due_date"):
        due_html = f'<span class="due-label">· {task["due_date"]}</span>'

    action_html = ""
    action_type = task.get("action_type", "do")
    if show_action and action_type and action_type != "do":
        label = action_type.replace("_", " ")
        action_html = f'<span class="action-label">[{label}]</span>'

    notes_html = f'<span class="item-note">{notes}</span>' if notes else ""

    return f"<li>{badge_html}{title}{due_html}{action_html}{notes_html}</li>"


def _section(heading: str, inner_html: str) -> str:
    """Wrap content in a labeled section. Returns empty string if inner_html is blank."""
    stripped = inner_html.strip()
    if not stripped:
        return ""
    return f'<div class="section-heading">{heading}</div><ul>{stripped}</ul>'


def _ap_notice_li(message: str) -> str:
    return (
        '<li style="list-style:none; padding-left:0;">'
        f'<div class="ap-notice">{message}</div>'
        "</li>"
    )


def _muted_li(text: str) -> str:
    return f'<li class="muted-li">{text}</li>'


# ── Daily Digest ──────────────────────────────────────────────────────────────

def build_daily_digest(sections: dict, today: date) -> str:
    """Render Daily Digest HTML from pre-routed section data.

    Args:
        sections: Output of routing_engine.route_daily()
        today:    Current date for the subtitle line
    """
    subtitle = today.strftime("%A, %B %-d, %Y")
    parts = []

    # Must Do
    must_do_html = "".join(
        _item_li(t, show_due=True) for t in sections.get("must_do", [])
    )
    parts.append(_section("Must Do", must_do_html))

    # Admissions Focus
    af_html = ""
    if sections.get("in_ap_window"):
        af_html += _ap_notice_li(
            "AP exam protection window active — only urgent admissions items are shown."
        )
    af_html += "".join(
        _item_li(t, show_due=True) for t in sections.get("admissions_focus", [])
    )
    parts.append(_section("Admissions Focus", af_html))

    # Today
    today_html = "".join(
        _item_li(t, show_action=True) for t in sections.get("today_items", [])
    )
    parts.append(_section("Today", today_html))

    # This Week
    week_html = "".join(
        _item_li(t, show_due=True) for t in sections.get("week_items", [])
    )
    parts.append(_section("This Week", week_html))

    # Watchouts
    watchouts_html = "".join(
        _item_li(t, show_badge=True, show_due=True) for t in sections.get("watchouts", [])
    )
    parts.append(_section("Watchouts", watchouts_html))

    body = "\n".join(p for p in parts if p)
    if not body:
        body = '<p class="no-items">Nothing to surface today.</p>'

    return _wrap_html("Daily Digest", subtitle, body)


# ── Weekly Reset ──────────────────────────────────────────────────────────────

def build_weekly_reset(sections: dict, today: date) -> str:
    """Render Weekly Reset HTML from pre-routed section data.

    Args:
        sections: Output of routing_engine.route_weekly()
        today:    Current date for the subtitle line
    """
    subtitle = f"Week of {today.strftime('%B %-d, %Y')}"
    parts = []

    # This Week's Criticals
    criticals_html = "".join(
        _item_li(t, show_due=True) for t in sections.get("criticals", [])
    )
    if not criticals_html:
        criticals_html = _muted_li("No critical items this week.")
    parts.append(_section("This Week's Criticals", criticals_html))

    # Deadlines in 14 Days
    deadlines_html = "".join(
        _item_li(t, show_due=True) for t in sections.get("deadlines", [])
    )
    parts.append(_section("Deadlines — Next 14 Days", deadlines_html))

    # Sarah Load Check
    sarah_html = ""
    if sections.get("in_ap_window"):
        sarah_html += _ap_notice_li(
            "AP protection window is active — keep Sarah's load lean this week."
        )
    sarah_html += "".join(_item_li(t) for t in sections.get("sarah_items", []))
    if not sarah_html.strip():
        sarah_html = _muted_li("No Sarah-specific items flagged this week.")
    parts.append(_section("Sarah Load Check", sarah_html))

    # Open Loops (waiting)
    waiting_html = "".join(
        _item_li(t, show_badge=True) for t in sections.get("waiting_items", [])
    )
    parts.append(_section("Open Loops", waiting_html))

    # Suggested Order
    order_html = "".join(f"<li>{s}</li>" for s in sections.get("suggested_order", []))
    parts.append(_section("Suggested Order", order_html))

    # Planning Questions
    q_html = "".join(f"<li>{q}</li>" for q in sections.get("planning_questions", []))
    parts.append(_section("Questions For You", q_html))

    body = "\n".join(p for p in parts if p)
    if not body:
        body = '<p class="no-items">Nothing significant to surface this week.</p>'

    return _wrap_html("Weekly Reset", subtitle, body)
