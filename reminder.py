# reminder.py
import threading
import time
from datetime import datetime

from config import REMINDER_POLL_INTERVAL
from memory.tasks import load_pending_tasks, increment_notify, mark_completed


def _is_due(task_value: dict) -> bool:
    """
    S3 fix: handle all proactive condition types, not just specific_time.
    on_mention and before_next_session intentionally excluded —
    they require message context and are handled in check_conditions().
    """
    condition    = task_value.get("condition")
    now          = datetime.now()
    current_hour = now.hour
    current_day  = now.weekday()

    # Day filter — applies to all condition types
    condition_days = task_value.get("condition_days")
    if condition_days is not None and current_day not in condition_days:
        return False

    if condition == "specific_time":
        due = task_value.get("due")
        if not due:
            return False
        try:
            return now >= datetime.fromisoformat(due)
        except Exception:
            return False

    elif condition == "time_range":
        hours = task_value.get("condition_hours")
        if hours and len(hours) == 2:
            return hours[0] <= current_hour < hours[1]
        return False

    return False


def _build_prompt(task_content: str) -> str:
    return (
        f"Reminder time! Please remind me about this: '{task_content}'. "
        f"Be natural and brief."
    )


def start_reminder_thread(store, user_id, ask_fn, graph, speak_fn, print_fn=print):
    """
    Polls every REMINDER_POLL_INTERVAL seconds (default 30).
    Fires specific_time and time_range tasks proactively.
    """

    def loop():
        while True:
            try:
                pending = load_pending_tasks(store, user_id)

                for task in pending:
                    if _is_due(task.value):
                        content = task.value.get("content", "")
                        print_fn(f"\n[Reminder] Firing: {task.key}")

                        try:
                            prompt   = _build_prompt(content)
                            response = ask_fn(graph, prompt)
                            print_fn(f"\n[Reminder]\nParker: {response}\n")
                            speak_fn(response)
                        except Exception as e:
                            print_fn(f"[Reminder] Ask failed: {e}")

                        # One-shot: mark done after firing
                        # Recurring: mark_completed resets to pending automatically
                        mark_completed(store, user_id, task.key)

            except Exception as e:
                print_fn(f"[Reminder] Poll error: {e}")

            time.sleep(REMINDER_POLL_INTERVAL)

    t = threading.Thread(target=loop, daemon=True)
    t.start()