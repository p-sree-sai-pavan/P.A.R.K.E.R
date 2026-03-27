# memory/tasks/actions.py
import time
from datetime import datetime, timedelta

from .constants import NAMESPACE

def advance_due_date(due_str: str, rule: str) -> str:
    if not due_str or not rule:
        return due_str
    try:
        dt = datetime.fromisoformat(due_str)
        rule = rule.lower()
        if rule == "daily":
            dt += timedelta(days=1)
        elif rule == "weekly":
            dt += timedelta(days=7)
        elif rule == "weekdays":
            # add 1 day until it is weekday
            dt += timedelta(days=1)
            while dt.weekday() >= 5:
                dt += timedelta(days=1)
        elif rule == "weekends":
            # add 1 day until it is weekend
            dt += timedelta(days=1)
            while dt.weekday() < 5:
                dt += timedelta(days=1)
        return dt.isoformat()
    except Exception:
        return due_str


def mark_completed(store, user_id: str, task_key: str):
    ns   = NAMESPACE(user_id)
    item = store.get(ns, task_key)

    if item is None:
        print(f"[Tasks] mark_completed: key not found: {task_key}")
        return

    updated         = item.value.copy()
    recurrence_rule = updated.get("recurrence_rule")

    if recurrence_rule:
        updated["status"]                = "pending"
        updated["completed_at"]          = None
        updated["sessions_since_notify"] = 0
        updated["last_notified"]         = time.time()
        
        # Advance the due date!
        old_due = updated.get("due")
        if old_due:
            updated["due"] = advance_due_date(old_due, recurrence_rule)
        
        store.put(ns, task_key, updated)
        print(f"[Tasks] RESET (recurring {recurrence_rule}, new due: {updated.get('due')}): {task_key}")
    else:
        updated["status"]       = "completed"
        updated["completed_at"] = time.time()
        store.put(ns, task_key, updated)
        print(f"[Tasks] Completed: {task_key}")


def increment_notify(store, user_id: str, task_key: str):
    ns   = NAMESPACE(user_id)
    item = store.get(ns, task_key)

    if item is None:
        return

    updated                          = item.value.copy()
    updated["notify_count"]          = updated.get("notify_count", 0) + 1
    updated["last_notified"]         = time.time()
    updated["sessions_since_notify"] = 0
    store.put(ns, task_key, updated)
