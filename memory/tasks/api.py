# memory/tasks/api.py
import time
from datetime import datetime

from memory.utils import full_scan, semantic_search
from .constants import NAMESPACE, ARCHIVE_NS, SNOOZE_BY_PRIORITY
from .conditions import condition_matches

def load_pending_tasks(store, user_id: str) -> list:
    all_tasks = full_scan(store, NAMESPACE(user_id))
    return [
        t for t in all_tasks
        if t.value.get("status") in ("pending", "snoozed")
    ]

def check_conditions(store, user_id: str, message: str) -> list:
    now          = datetime.now()
    current_hour = now.hour
    current_day  = now.weekday()
    message_low  = message.lower()

    pending   = load_pending_tasks(store, user_id)
    triggered = {}

    for task in pending:
        v        = task.value
        priority = v.get("priority", "normal")

        sessions_to_wait = SNOOZE_BY_PRIORITY.get(priority, 2)
        sessions_since   = v.get("sessions_since_notify", 999)
        if sessions_since < sessions_to_wait:
            continue

        if condition_matches(v, message_low, current_hour, current_day, now):
            triggered[task.key] = task

    from memory.reminder_gate import _is_greeting, _is_acknowledgment
    if not _is_greeting(message) and not _is_acknowledgment(message):
        relevant = semantic_search(
            store, NAMESPACE(user_id),
            query=message,
            limit=5
        )
        for task in relevant:
            if task.key not in triggered:
                if task.value.get("status") in ("pending", "snoozed"):
                    triggered[task.key] = task

    return list(triggered.values())

def tick_sessions(store, user_id: str):
    ns         = NAMESPACE(user_id)
    archive_ns = ARCHIVE_NS(user_id)
    now        = time.time()

    try:
        all_tasks = full_scan(store, ns)

        for item in all_tasks:
            updated = item.value.copy()
            status  = updated.get("status", "pending")

            if status in ("pending", "snoozed"):
                updated["sessions_since_notify"] = (
                    updated.get("sessions_since_notify", 0) + 1
                )
                store.put(ns, item.key, updated)

            elif status == "completed":
                completed_at    = updated.get("completed_at", now)
                days_since      = (now - completed_at) / 86400
                fade_after_days = updated.get("fade_after_days")

                if fade_after_days is not None and days_since > fade_after_days:
                    store.put(archive_ns, item.key, updated)
                    try:
                        store.delete(ns, item.key)
                    except Exception as e:
                        print(f"[Tasks] Delete failed for {item.key}: {e}")
                    print(f"[Tasks] Faded: {item.key}")

    except Exception as e:
        print(f"[Tasks] Tick failed: {e}")

def format_for_prompt(tasks: list) -> str:
    if not tasks:
        return "(none)"

    lines = []
    for task in tasks:
        v        = task.value
        content  = v.get("content", "")
        priority = v.get("priority", "normal")
        prefix   = "[urgent] " if priority == "urgent" else (
                   "[high] "   if priority == "high"   else ""
        )
        lines.append(f"- {prefix}{content}")

    return "\n".join(lines)
