# Family OS v2

A cloud-run personal operating system that runs on GitHub Actions and delivers two scheduled emails to your iCloud inbox. Built for a high-load household managing care, school admissions, logistics, and everything else.

---

## What it does

**Daily Digest** — every morning at 7 AM Eastern

- Must Do: top critical items due today or overdue
- Admissions Focus: top 2 active admissions items
- Today: remaining tasks that belong today
- This Week: relevant but not urgent items
- Watchouts: overdue overflow, stale waiting items, upcoming deadlines

**Weekly Reset** — every Sunday at 3 PM Eastern

- This Week's Criticals: all critical open items
- Deadlines in 14 Days: sorted by date
- Sarah Load Check: items owned by or involving Sarah
- Open Loops: waiting items that may need a follow-up
- Suggested Order: plain-English priority guidance
- Questions For You: 3–4 planning prompts based on what is open

---

## How to update tasks via email

Send command emails FROM your iCloud address (same as `NOTIFY_EMAIL`) TO your iCloud address. Commands are processed at the next digest run. All emails are marked read after processing.

### Command format

Commands locate an existing task by title. The match is fuzzy — you don't need exact wording.

| Command | Format | What it does |
|---|---|---|
| `DONE: task title` | No pipe needed | Sets state = done. Task disappears from future digests. |
| `MOVE: task title \| new_state` | Pipe + target state | Moves task to `inbox`, `today`, `this_week`, `waiting`, or `done`. |
| `PRIORITY: task title \| level` | Pipe + priority | Sets priority to `critical`, `important`, or `light`. |
| `WAITING: task title` | No pipe needed | Sets state = waiting. If no match found, falls back to creating a new waiting task. |
| `DELETE: task title` | No pipe needed | Permanently removes the task from the store. Cannot be undone. |

**Examples:**

```
Subject: DONE: call insurance about Xavier claim
Subject: MOVE: counselor follow-up | this_week
Subject: PRIORITY: ACT registration deadline | critical
Subject: WAITING: hear back from McCann on fee waiver
Subject: DELETE: order overnight supplies
```

**Title matching (3-pass):**
1. Exact match (case-insensitive)
2. Substring — picks the shortest title if multiple match
3. Word overlap — needs ≥2 words >2 chars in common; must be a clear winner

If no match is found, the command is logged and skipped. `WAITING` is the only command that falls back to creating a new task when no existing task matches.

---

## How to add tasks

### Option 1 — Send an email from your iCloud address

Email format: `PREFIX: task title in plain English`

| Subject prefix | What it means |
|---|---|
| `CARE: refill Xavier prescription` | Care domain, lands in inbox |
| `ADMISSIONS: send counselor follow-up` | Admissions domain, lands in inbox |
| `TODAY: call insurance about Xavier claim` | Forces state = today (appears in Today section) |
| `WEEK: schedule oil change` | This week, lower urgency |
| `WAITING: hear back from McCann on ACT waiver` | Waiting state, surfaces in Open Loops |
| `BUY: order Xavier overnight supplies` | Grocery domain, buy action |
| `SCHEDULE: book car A/C estimate` | Personal, schedule action |
| `FOLLOWUP: check on tutoring sessions` | Personal, follow up action |
| `DRAFT: counselor meeting talking points` | Personal, draft action |
| `HOUSEHOLD: fix back door lock` | Household domain |
| `FINANCE: check insurance EOB` | Finance domain |

Send from your iCloud address (same as `NOTIFY_EMAIL`). The next digest run will pick it up, add it to `tasks.json`, and include it in that day's email.

**Important:** The `TODAY:` prefix is the only prefix that overrides state. All other prefixes land in `inbox` and the system decides where they appear based on priority and due date.

### Option 2 — Edit tasks.json directly

Open `data/tasks.json` in the GitHub editor or locally. Add a task entry:

```json
{
  "id": "a1b2c3d4",
  "title": "Example task",
  "domain": "admissions",
  "category": "act",
  "state": "inbox",
  "priority": "critical",
  "action_type": "do",
  "owner": "JB",
  "due_date": "2026-04-30",
  "due_day": null,
  "recurrence": null,
  "notes": "Optional context note",
  "tags": [],
  "protected_during_ap_window": false,
  "source": "manual",
  "created_at": "2026-04-15T00:00:00",
  "updated_at": "2026-04-15T00:00:00"
}
```

Use `uuid` or any 8-character hex string for the `id`. It must be unique within the file.

---

## How to mark a task done

Edit `data/tasks.json` in the GitHub editor. Find the task by title, change `"state": "done"`. Commit. It will be excluded from all future digests.

---

## State model

| State | Meaning |
|---|---|
| `inbox` | Captured, not yet triaged |
| `today` | Must happen today |
| `this_week` | Relevant this week, not urgent today |
| `waiting` | Blocked on someone else |
| `done` | Completed — excluded from all output |
| `overdue` | Past due date and not done — computed automatically |

The state engine promotes tasks automatically at runtime:
- Past due_date + not done → `overdue`
- `due_day: "daily"` → `today`
- `due_day` matches today's weekday → `today`
- Critical priority + due within 2 days → `today`
- Due within 7 days → `this_week`

You do not need to manually update most states. Set the initial state and let the engine do the rest.

---

## Task fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | 8-char hex, unique |
| `title` | string | Plain-English task name |
| `domain` | string | `care`, `admissions`, `logistics`, `household`, `grocery`, `finance`, `admin`, `personal` |
| `category` | string | Free-form subcategory (e.g. `meds`, `act`, `transport`) |
| `state` | string | See state model above |
| `priority` | string | `critical`, `important`, `light` |
| `action_type` | string | `do`, `draft`, `follow_up`, `research`, `buy`, `schedule`, `decide`, `waiting_on`, `review` |
| `owner` | string | `JB`, `Sarah`, or other |
| `due_date` | string | ISO date `YYYY-MM-DD` or `null` |
| `due_day` | string | Weekday name (`Monday`) or `daily` for daily recurrence, or `null` |
| `recurrence` | string | `daily`, `weekly`, `monthly`, or `null` |
| `notes` | string | Context shown under the task title in emails |
| `tags` | list | Optional string tags |
| `protected_during_ap_window` | bool | If `true`, suppressed during AP exam window unless critical |
| `source` | string | `manual`, `email_capture`, `migrated_v1` |
| `created_at` | string | ISO datetime |
| `updated_at` | string | ISO datetime |

---

## AP exam protection window

During the Sarah AP exam window (May 4–13, 2026), any task with `protected_during_ap_window: true` is suppressed from the digest unless its priority is `critical`. The AP notice banner appears in Admissions Focus and Sarah Load Check sections.

To add or modify AP windows, edit `data/config.json`:

```json
{
  "ap_windows": [
    {
      "start": "2026-05-04",
      "end": "2026-05-13",
      "notes": "AP exam window"
    }
  ]
}
```

---

## Deployment

### First-time setup

1. Fork or clone this repo to your GitHub account.
2. Add three repository secrets (Settings → Secrets → Actions):
   - `GMAIL_USER` — your Gmail address (the sender)
   - `GMAIL_APP_PASSWORD` — a Gmail App Password (not your account password)
   - `NOTIFY_EMAIL` — your iCloud address (the recipient and capture sender)
3. Run migration to generate `tasks.json` from v1 data:
   ```
   python migrate_v1.py
   ```
4. Commit `data/tasks.json` and `data/config.json`.
5. Enable GitHub Actions on the repo. Workflows run automatically on schedule.

### Manual trigger

Go to Actions → Daily Digest (or Weekly Reset) → Run workflow.

### Capture via email

Gmail IMAP uses the same App Password as SMTP. No additional credentials needed.

---

## File structure

```
family-os-bot/
├── .github/workflows/
│   ├── daily-digest.yml      # 7 AM Eastern daily
│   └── weekly-reset.yml      # 3 PM Eastern Sundays
├── data/
│   ├── tasks.json            # Unified task store (v2)
│   └── config.json           # AP windows and system config
├── capture_module.py         # Gmail IMAP capture
├── task_store.py             # tasks.json read/write
├── state_engine.py           # Computes effective task states
├── routing_engine.py         # Surfaces tasks for each digest section
├── digest_builder.py         # HTML rendering only
├── notifier.py               # Gmail SMTP email delivery
├── data_loader.py            # JSON file utility (preserved from v1)
├── main.py                   # Pipeline entry point
├── migrate_v1.py             # One-time v1 → v2 migration
└── requirements.txt          # tzdata only (all else is stdlib)
```

---

## v1 modules (deprecated)

`care_module.py`, `admissions_module.py`, `logistics_module.py`, and `grocery_module.py` are no longer imported. Their data is now in `tasks.json` and their logic is handled by `state_engine.py` and `routing_engine.py`. They can be deleted after you verify one successful v2 digest run.
