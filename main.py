"""
main.py — Entry point for Family OS v2.

Pipeline per run:
  capture → task_store → state_engine → routing_engine → digest_builder → notifier

Capture is integrated directly into each digest run.
No separate cron loop or capture workflow required.

GitHub Actions calls:
  python -c "from main import run_daily_digest; run_daily_digest()"
  python -c "from main import run_weekly_reset; run_weekly_reset()"

CLI:
  python main.py daily
  python main.py weekly
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from capture_module import run_capture_and_commands
from digest_builder import build_daily_digest, build_weekly_reset
from notifier import send_email
from routing_engine import route_daily, route_weekly
from state_engine import apply_states
from task_store import append_tasks, get_tasks, load_tasks, save_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _get_today() -> date:
    """Return the current date in the configured timezone.

    Reads BOT_TIMEZONE from environment (default: America/New_York).
    Falls back to UTC if the timezone is unrecognized.
    """
    tz_name = os.environ.get("BOT_TIMEZONE", "America/New_York").strip()
    try:
        return datetime.now(tz=ZoneInfo(tz_name)).date()
    except ZoneInfoNotFoundError:
        logger.warning(f"Unknown timezone '{tz_name}'. Falling back to UTC.")
        return datetime.now(tz=ZoneInfo("UTC")).date()


def _capture_and_load() -> list:
    """Run capture and commands, persist changes to tasks.json, return full task list.

    Steps:
      1. Load current tasks.json.
      2. Run Gmail IMAP pass — processes commands (DONE/MOVE/PRIORITY/WAITING/DELETE)
         and capture emails (new tasks) in a single connection.
      3. Persist if commands modified the store or new tasks were captured.
      4. Return the full task list.
    """
    store = load_tasks()

    new_tasks, command_store, commands_modified = run_capture_and_commands(store)

    final_store = command_store
    if new_tasks:
        final_store = append_tasks(command_store, new_tasks)

    if new_tasks or commands_modified:
        save_tasks(final_store)

    return get_tasks(final_store)


def run_daily_digest() -> None:
    """Build and send the Daily Digest email.

    Exits with code 1 if the email fails to send, so GitHub Actions
    marks the workflow run as failed.
    """
    logger.info("=" * 50)
    logger.info("Family OS v2 — Daily Digest")
    logger.info("=" * 50)

    today = _get_today()
    logger.info(f"Date: {today.strftime('%A, %B %-d, %Y')}")

    tasks = _capture_and_load()
    logger.info(f"Loaded {len(tasks)} tasks from store.")

    enriched = apply_states(tasks, today)
    sections = route_daily(enriched, today)
    html = build_daily_digest(sections, today)

    subject = f"Daily Digest · {today.strftime('%A, %B %-d')}"
    if not send_email(subject, html):
        logger.error("Daily Digest failed to send.")
        sys.exit(1)
    logger.info("Daily Digest sent successfully.")


def run_weekly_reset() -> None:
    """Build and send the Weekly Reset email.

    Intended to run on Sundays. The GitHub Actions schedule enforces this,
    but the function itself does not validate the day of week.

    Exits with code 1 if the email fails to send.
    """
    logger.info("=" * 50)
    logger.info("Family OS v2 — Weekly Reset")
    logger.info("=" * 50)

    today = _get_today()
    logger.info(f"Date: {today.strftime('%A, %B %-d, %Y')}")

    tasks = _capture_and_load()
    logger.info(f"Loaded {len(tasks)} tasks from store.")

    enriched = apply_states(tasks, today)
    sections = route_weekly(enriched, today)
    html = build_weekly_reset(sections, today)

    subject = f"Weekly Reset · Week of {today.strftime('%B %-d')}"
    if not send_email(subject, html):
        logger.error("Weekly Reset failed to send.")
        sys.exit(1)
    logger.info("Weekly Reset sent successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Family OS v2")
    parser.add_argument(
        "command",
        choices=["daily", "weekly"],
        help="'daily' for Daily Digest, 'weekly' for Weekly Reset.",
    )
    args = parser.parse_args()

    if args.command == "daily":
        run_daily_digest()
    else:
        run_weekly_reset()
