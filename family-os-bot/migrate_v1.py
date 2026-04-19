"""
migrate_v1.py — One-time migration from v1 JSON files to v2 tasks.json.

Run this ONCE locally before deploying v2:
  python migrate_v1.py

Reads:  data/care.json, data/admissions.json, data/logistics.json
Writes: data/tasks.json, data/config.json

Does NOT delete original v1 files. Review data/tasks.json before deploying.

Migration rules (simple):
  - v1 status "done"    → v2 state "done"
  - v1 status "overdue" → v2 state "overdue"
  - v1 status "pending" → v2 state "inbox"  (state engine computes from here)
  - action_type defaults to "do" for all migrated items
  - All other fields mapped directly where they match the v2 schema
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _load(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  [skip] {filename} not found")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _map_state(status: str) -> str:
    """Map v1 status → v2 state."""
    return {
        "done":    "done",
        "overdue": "overdue",
    }.get(str(status).lower(), "inbox")  # pending and anything else → inbox


def _logistics_domain(category: str) -> str:
    """Infer v2 domain from v1 logistics category."""
    cat = (category or "").lower()
    if cat in ("transport", "transportation", "car", "travel", "scheduling", "sarah"):
        return "logistics"
    if cat in ("household", "admin", "home", "errand", "errands"):
        return "household"
    return "logistics"


def _migrate_item(item: dict, domain: str) -> dict:
    """Map a v1 item to a v2 task. Essential fields only; defaults for the rest."""
    return {
        "id":                         _new_id(),
        "title":                      item.get("title", "(untitled)"),
        "domain":                     domain,
        "category":                   item.get("category", ""),
        "state":                      _map_state(item.get("status", "pending")),
        "priority":                   item.get("priority", "important"),
        "action_type":                "do",
        "owner":                      item.get("owner", "JB"),
        "due_date":                   item.get("due_date"),
        "due_day":                    item.get("due_day"),
        "recurrence":                 item.get("recurrence"),
        "notes":                      item.get("notes", ""),
        "tags":                       item.get("tags", []),
        "protected_during_ap_window": item.get("protected_during_ap_window", False),
        "source":                     "migrated_v1",
        "created_at":                 NOW,
        "updated_at":                 NOW,
    }


def migrate() -> None:
    print("Family OS — v1 → v2 Migration")
    print("=" * 40)

    all_tasks = []

    # ── Care ──────────────────────────────────────────────────────────────────
    care_data = _load("care.json")
    care_items = care_data.get("care_items", care_data.get("items", []))
    for item in care_items:
        all_tasks.append(_migrate_item(item, domain="care"))
    print(f"  care:        {len(care_items)} items")

    # ── Admissions ────────────────────────────────────────────────────────────
    admissions_data = _load("admissions.json")
    adm_items = admissions_data.get("items", [])
    for item in adm_items:
        all_tasks.append(_migrate_item(item, domain="admissions"))
    print(f"  admissions:  {len(adm_items)} items")

    # ── Logistics ─────────────────────────────────────────────────────────────
    logistics_data = _load("logistics.json")
    log_items = logistics_data.get("items", [])
    for item in log_items:
        domain = _logistics_domain(item.get("category", ""))
        all_tasks.append(_migrate_item(item, domain=domain))
    print(f"  logistics:   {len(log_items)} items")

    total = len(all_tasks)

    # ── Write tasks.json ──────────────────────────────────────────────────────
    store = {"version": "2", "tasks": all_tasks}
    tasks_path = DATA_DIR / "tasks.json"
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
    print(f"\n  tasks.json written  — {total} tasks total")

    # ── Write config.json (extract AP windows) ────────────────────────────────
    ap_windows = admissions_data.get("ap_windows", [])
    config = {"ap_windows": ap_windows}
    config_path = DATA_DIR / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"  config.json written — {len(ap_windows)} AP window(s)")

    print()
    print("Migration complete.")
    print("Next steps:")
    print("  1. Review data/tasks.json — adjust states or priorities as needed")
    print("  2. Commit data/tasks.json and data/config.json to the repo")
    print("  3. Deploy v2 modules and workflows")
    print("  4. Original v1 files are untouched — delete them after you verify one digest run")


if __name__ == "__main__":
    migrate()
