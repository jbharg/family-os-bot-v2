"""
capture_module.py — Gmail IMAP capture and command processing for Family OS v2.

Reads the Gmail inbox for unread emails FROM the NOTIFY_EMAIL address. Each
email is classified as either a command (modifying an existing task) or a
capture (creating a new task). All emails are processed in a single IMAP
connection and marked read afterward.

Called via run_capture_and_commands(store) from main.py at the start of each
digest run. No separate workflow or cron loop required.

─── COMMAND PREFIXES (modify existing tasks) ───────────────────────────────

    DONE: task title              → set state=done
    MOVE: task title | new_state  → set state to inbox/today/this_week/waiting/done
    PRIORITY: task title | level  → set priority to critical/important/light
    WAITING: task title           → set state=waiting  (falls back to capture if no match)
    DELETE: task title            → remove task from store entirely

─── CAPTURE PREFIXES (create new tasks) ────────────────────────────────────

    CARE:        → domain=care,       state=inbox,     action_type=do
    ADMISSIONS:  → domain=admissions, state=inbox,     action_type=do
    TODAY:       → domain=personal,   state=today,     action_type=do  (forced)
    WEEK:        → domain=personal,   state=this_week, action_type=do
    WAITING:     → domain=personal,   state=waiting,   action_type=waiting_on  (fallback)
    BUY:         → domain=grocery,    state=inbox,     action_type=buy
    DRAFT:       → domain=personal,   state=inbox,     action_type=draft
    SCHEDULE:    → domain=personal,   state=inbox,     action_type=schedule
    FOLLOWUP:    → domain=personal,   state=inbox,     action_type=follow_up
    HOUSEHOLD:   → domain=household,  state=inbox,     action_type=do
    FINANCE:     → domain=finance,    state=inbox,     action_type=do

─── TITLE MATCHING ─────────────────────────────────────────────────────────

Commands locate tasks via a 3-pass title search:
  1. Exact match (case-insensitive)
  2. Substring match — prefers shortest title if multiple match
  3. Word-overlap match — min 2 words > 2 chars in common; must be a clear winner

If no match is found, the command is logged as unmatched and skipped.
WAITING is the only prefix that falls through to capture on no match.
"""

import email as email_lib
import imaplib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from task_store import get_tasks, make_task

logger = logging.getLogger(__name__)

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# ── Command configuration ────────────────────────────────────────────────────

_COMMAND_PREFIXES = {"DONE", "MOVE", "PRIORITY", "WAITING", "DELETE"}

_VALID_MOVE_STATES = {"inbox", "today", "this_week", "waiting", "done"}
_VALID_PRIORITIES = {"critical", "important", "light"}

# ── Capture configuration ────────────────────────────────────────────────────

# Maps capture prefix → (domain, state, action_type)
_CAPTURE_MAP: dict[str, tuple[str, str, str]] = {
    "CARE":       ("care",       "inbox",     "do"),
    "ADMISSIONS": ("admissions", "inbox",     "do"),
    "TODAY":      ("personal",   "today",     "do"),
    "WEEK":       ("personal",   "this_week", "do"),
    "WAITING":    ("personal",   "waiting",   "waiting_on"),
    "BUY":        ("grocery",    "inbox",     "buy"),
    "DRAFT":      ("personal",   "inbox",     "draft"),
    "SCHEDULE":   ("personal",   "inbox",     "schedule"),
    "FOLLOWUP":   ("personal",   "inbox",     "follow_up"),
    "HOUSEHOLD":  ("household",  "inbox",     "do"),
    "FINANCE":    ("finance",    "inbox",     "do"),
}

# All recognized prefixes — commands first so WAITING resolution is clear
_ALL_PREFIXES = _COMMAND_PREFIXES | set(_CAPTURE_MAP.keys())

_SUBJECT_RE = re.compile(
    r"^(" + "|".join(re.escape(k) for k in _ALL_PREFIXES) + r"):\s*(.+)$",
    re.IGNORECASE,
)


# ── Header decoding ──────────────────────────────────────────────────────────

def _decode_header(raw: str) -> str:
    """Decode an RFC 2047 email header value to a plain string."""
    parts = email_lib.header.decode_header(raw or "")
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return "".join(decoded).strip()


# ── Title matching ───────────────────────────────────────────────────────────

def _words(text: str) -> set[str]:
    """Return lowercase words longer than 2 characters."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def _find_task(tasks: list, query: str) -> Optional[dict]:
    """Locate a task by title using a 3-pass fuzzy search.

    Pass 1 — exact match (case-insensitive)
    Pass 2 — substring match; prefers shortest title on multiple hits
    Pass 3 — word-overlap; requires ≥2 shared words >2 chars; must be a clear winner

    Returns the matching task dict, or None if no match found.
    """
    q = query.strip().lower()

    # Pass 1: exact
    for t in tasks:
        if t.get("title", "").strip().lower() == q:
            return t

    # Pass 2: substring — prefer shortest title on tie
    substring_hits = [t for t in tasks if q in t.get("title", "").lower()]
    if len(substring_hits) == 1:
        return substring_hits[0]
    if len(substring_hits) > 1:
        return min(substring_hits, key=lambda t: len(t.get("title", "")))

    # Pass 3: word overlap
    q_words = _words(query)
    if len(q_words) < 2:
        return None

    scored = []
    for t in tasks:
        shared = q_words & _words(t.get("title", ""))
        if len(shared) >= 2:
            scored.append((len(shared), t))

    if not scored:
        return None

    scored.sort(key=lambda x: -x[0])
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]

    return None  # ambiguous — no clear winner


# ── Command application ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _apply_command(
    tasks: list, command: str, title_query: str, arg: str
) -> tuple[list, bool, str]:
    """Apply a command to the task list.

    Returns:
        (updated_tasks, modified, log_message)
        - updated_tasks: new list (original unchanged)
        - modified: True if any task was changed or removed
        - log_message: human-readable outcome for logging
    """
    target = _find_task(tasks, title_query)

    if target is None:
        return tasks, False, f"Command {command}: no match for '{title_query}' — skipped"

    task_id = target.get("id")
    title = target.get("title")

    if command == "DELETE":
        updated = [t for t in tasks if t.get("id") != task_id]
        return updated, True, f"DELETE: removed '{title}'"

    if command == "DONE":
        updated = [
            {**t, "state": "done", "updated_at": _now_iso()} if t.get("id") == task_id else t
            for t in tasks
        ]
        return updated, True, f"DONE: '{title}' → state=done"

    if command == "WAITING":
        updated = [
            {**t, "state": "waiting", "updated_at": _now_iso()} if t.get("id") == task_id else t
            for t in tasks
        ]
        return updated, True, f"WAITING: '{title}' → state=waiting"

    if command == "MOVE":
        new_state = arg.strip().lower()
        if new_state not in _VALID_MOVE_STATES:
            return tasks, False, (
                f"MOVE: invalid state '{arg}' for '{title}' — "
                f"must be one of {sorted(_VALID_MOVE_STATES)}"
            )
        updated = [
            {**t, "state": new_state, "updated_at": _now_iso()} if t.get("id") == task_id else t
            for t in tasks
        ]
        return updated, True, f"MOVE: '{title}' → state={new_state}"

    if command == "PRIORITY":
        new_priority = arg.strip().lower()
        if new_priority not in _VALID_PRIORITIES:
            return tasks, False, (
                f"PRIORITY: invalid priority '{arg}' for '{title}' — "
                f"must be one of {sorted(_VALID_PRIORITIES)}"
            )
        updated = [
            {**t, "priority": new_priority, "updated_at": _now_iso()} if t.get("id") == task_id else t
            for t in tasks
        ]
        return updated, True, f"PRIORITY: '{title}' → priority={new_priority}"

    return tasks, False, f"Command {command}: unrecognized — skipped"


# ── Subject parsing ──────────────────────────────────────────────────────────

def _parse_subject(subject: str) -> Optional[tuple[str, str]]:
    """Return (prefix_upper, body) from a recognized subject line, or None."""
    match = _SUBJECT_RE.match(subject.strip())
    if not match:
        return None
    return match.group(1).upper(), match.group(2).strip()


def _parse_pipe(body: str) -> tuple[str, str]:
    """Split 'title | arg' into (title, arg). Returns (body, '') if no pipe."""
    if "|" in body:
        parts = body.split("|", 1)
        return parts[0].strip(), parts[1].strip()
    return body.strip(), ""


# ── Main entry point ─────────────────────────────────────────────────────────

def run_capture_and_commands(store: dict) -> tuple[list, dict, bool]:
    """Process unread capture/command emails from Gmail in a single IMAP pass.

    Classification order per email:
      1. Command prefix (DONE/MOVE/PRIORITY/DELETE) → always a command
      2. WAITING prefix + existing task match → command (set state=waiting)
      3. WAITING prefix + no match → capture (create new waiting task)
      4. Capture prefix → create new task

    Args:
        store: The raw task store dict from load_tasks().

    Returns:
        (new_tasks, updated_store, commands_modified)
        - new_tasks: list of newly captured task dicts to be appended
        - updated_store: store with command mutations applied in-place
        - commands_modified: True if any command changed the store
    """
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    notify_email = os.environ.get("NOTIFY_EMAIL", "").strip()

    if not gmail_user or not gmail_password or not notify_email:
        logger.warning(
            "Capture/commands skipped — GMAIL_USER, GMAIL_APP_PASSWORD, or NOTIFY_EMAIL not set."
        )
        return [], store, False

    new_tasks: list = []
    current_tasks: list = get_tasks(store)
    commands_modified = False

    try:
        logger.info(f"Capture: connecting to Gmail IMAP as {gmail_user} ...")
        with imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT) as conn:
            conn.login(gmail_user, gmail_password)
            conn.select("INBOX")

            _, data = conn.search(None, f'(UNSEEN FROM "{notify_email}")')
            msg_ids = data[0].split() if data and data[0] else []
            logger.info(f"Capture: {len(msg_ids)} unread message(s) from {notify_email}")

            for msg_id in msg_ids:
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
                subject = _decode_header(msg.get("Subject", ""))

                parsed = _parse_subject(subject)
                if not parsed:
                    # Unrecognized subject — leave unread so it can be inspected
                    logger.debug(f"Capture: skipping unrecognized subject: {subject!r}")
                    continue

                prefix, body = parsed

                # ── Command branch ───────────────────────────────────────────
                if prefix in _COMMAND_PREFIXES:
                    if prefix in ("MOVE", "PRIORITY"):
                        title_query, arg = _parse_pipe(body)
                    else:
                        title_query, arg = body, ""

                    if prefix == "WAITING":
                        # Dual behavior: try command first, fall back to capture
                        target = _find_task(current_tasks, title_query)
                        if target is None:
                            # No match → fall through to capture
                            logger.info(
                                f"WAITING: no existing task match for '{title_query}' "
                                f"— treating as capture"
                            )
                            domain, state, action_type = _CAPTURE_MAP["WAITING"]
                            task = make_task(
                                title=title_query,
                                domain=domain,
                                state=state,
                                action_type=action_type,
                                source="email_capture",
                            )
                            new_tasks.append(task)
                            logger.info(
                                f"Capture: '{title_query}' → domain={domain}, "
                                f"state={state}, action={action_type}"
                            )
                            conn.store(msg_id, "+FLAGS", "\\Seen")
                            continue

                    current_tasks, modified, log_msg = _apply_command(
                        current_tasks, prefix, title_query, arg
                    )
                    if modified:
                        commands_modified = True
                    logger.info(f"Command: {log_msg}")
                    conn.store(msg_id, "+FLAGS", "\\Seen")
                    continue

                # ── Capture branch ───────────────────────────────────────────
                if prefix in _CAPTURE_MAP:
                    domain, state, action_type = _CAPTURE_MAP[prefix]
                    if prefix == "TODAY":
                        state = "today"  # forced at creation — do not rely on state engine
                    task = make_task(
                        title=body,
                        domain=domain,
                        state=state,
                        action_type=action_type,
                        source="email_capture",
                    )
                    new_tasks.append(task)
                    logger.info(
                        f"Capture: '{body}' → domain={domain}, state={state}, action={action_type}"
                    )
                    conn.store(msg_id, "+FLAGS", "\\Seen")

    except imaplib.IMAP4.error as e:
        logger.error(f"Capture: IMAP error — {e}")
    except OSError as e:
        logger.error(f"Capture: network error — {e}")
    except Exception as e:
        logger.error(f"Capture: unexpected error — {e}")

    logger.info(
        f"Capture complete — {len(new_tasks)} new task(s), "
        f"commands modified store: {commands_modified}"
    )

    # If commands modified the task list, update the store dict in-place
    updated_store = store
    if commands_modified:
        updated_store = {**store, "tasks": current_tasks}

    return new_tasks, updated_store, commands_modified
