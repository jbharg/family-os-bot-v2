"""
task_store.py — Read and write operations for data/tasks.json.

The task store is the single source of truth for Family OS v2.
All modules read tasks through here. Only capture and migrate write to it.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def load_tasks() -> dict:
    """Load tasks.json. Returns an empty store on missing or malformed file."""
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.debug(f"Loaded {len(data.get('tasks', []))} tasks from {TASKS_FILE}")
        return data
    except FileNotFoundError:
        logger.warning(f"{TASKS_FILE} not found — returning empty task store.")
        return {"version": "2", "tasks": []}
    except json.JSONDecodeError as e:
        logger.error(f"JSON error in {TASKS_FILE}: {e} — returning empty task store.")
        return {"version": "2", "tasks": []}
    except OSError as e:
        logger.error(f"Could not read {TASKS_FILE}: {e} — returning empty task store.")
        return {"version": "2", "tasks": []}


def save_tasks(store: dict) -> bool:
    """Write tasks.json atomically via a temp file. Returns True on success."""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        tmp = TASKS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        tmp.replace(TASKS_FILE)
        logger.info(f"Saved {len(store.get('tasks', []))} tasks to {TASKS_FILE}")
        return True
    except OSError as e:
        logger.error(f"Could not write {TASKS_FILE}: {e}")
        return False


def get_tasks(store: dict) -> list:
    """Return the task list from a store dict."""
    return store.get("tasks", [])


def make_task(
    title: str,
    domain: str = "personal",
    category: str = "",
    state: str = "inbox",
    priority: str = "important",
    action_type: str = "do",
    owner: str = "JB",
    due_date: Optional[str] = None,
    due_day: Optional[str] = None,
    recurrence: Optional[str] = None,
    notes: str = "",
    tags: Optional[list] = None,
    protected_during_ap_window: bool = False,
    source: str = "manual",
) -> dict:
    """Create a new task dict with all required fields and a stable ID."""
    now = _now_iso()
    return {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "domain": domain,
        "category": category,
        "state": state,
        "priority": priority,
        "action_type": action_type,
        "owner": owner,
        "due_date": due_date,
        "due_day": due_day,
        "recurrence": recurrence,
        "notes": notes,
        "tags": tags or [],
        "protected_during_ap_window": protected_during_ap_window,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }


def append_tasks(store: dict, new_tasks: list) -> dict:
    """Return a new store dict with new_tasks appended. Does not write to disk."""
    existing = store.get("tasks", [])
    return {**store, "tasks": existing + new_tasks}
