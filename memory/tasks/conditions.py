# memory/tasks/conditions.py
from datetime import datetime
from .constants import SNOOZE_BY_PRIORITY

def condition_matches(task_value, message_low, current_hour, current_day, now):
    condition = task_value.get("condition")

    condition_days = task_value.get("condition_days")
    if condition_days is not None:
        if current_day not in condition_days:
            return False

    if condition == "time_range":
        hours = task_value.get("condition_hours")
        if hours and len(hours) == 2:
            return hours[0] <= current_hour < hours[1]
        return False

    elif condition == "on_mention":
        keywords = task_value.get("keywords", [])
        return any(kw.lower() in message_low for kw in keywords)

    elif condition == "specific_time":
        due = task_value.get("due")
        if due:
            return _is_past_due(due, now)
        return False

    elif condition == "before_next_session":
        return True

    elif condition is None or condition == "none":
        return False

    return False

def _is_past_due(due: str, now: datetime) -> bool:
    try:
        return now >= datetime.fromisoformat(due)
    except Exception:
        return False
