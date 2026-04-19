"""
grocery_module.py — Integration stub for the grocery bot.

This module does NOT rebuild the grocery bot. It reads a simple status JSON
file that the grocery bot (or a human) populates, and surfaces the relevant
status in the Family OS digest.

To connect your existing grocery bot: have it write its status to data/grocery.json
in the format defined in that file.
"""

import logging

from data_loader import load_json

logger = logging.getLogger(__name__)

_GROCERY_DEFAULTS = {
    "status_summary": "No grocery data available.",
    "needs_attention": False,
    "notes": "",
    "next_run": None,
    "last_run": None,
}


def get_grocery_status() -> dict:
    """Return the current grocery bot status for digest inclusion.

    Reads data/grocery.json. Returns safe defaults if the file is missing.

    Returns:
        dict with keys:
            status_summary  — human-readable one-line status
            needs_attention — bool, True if the digest should highlight grocery
            notes           — optional additional context
            next_run        — ISO date string of next scheduled grocery run
            last_run        — ISO date string of last completed run
    """
    data = load_json("grocery.json", default=_GROCERY_DEFAULTS)

    # Ensure all expected keys are present, fall back to defaults for any missing
    result = {**_GROCERY_DEFAULTS, **data}

    if result["needs_attention"]:
        logger.info("Grocery status: needs attention.")
    else:
        logger.info(f"Grocery status: {result['status_summary']}")

    return result
