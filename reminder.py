# reminder.py
import threading
import time
from datetime import datetime

from memory.tasks import load_pending_tasks, increment_notify, mark_completed
from memory.utils import full_scan


def _is_due(task_value: dict) -> bool:
    condition = task_value.get("condition")
    if condition != "specific_time":
        return False

    due = task_value.get("due")
    if not due:
        return False

    try:
        return datetime.now() >= datetime.fromisoformat(due)
    except Exception:
        return False


def _build_prompt(task_content: str) -> str:
    return (
        f"Reminder time! Please remind me about this: '{task_content}'. "
        f"Be natural and brief."
    )


def start_reminder_thread(store, user_id, ask_fn, graph, speak_fn, print_fn=print):
    """
    Polls every 30 seconds.
    Fires any task whose due time has passed.
    Marks task completed after firing (one-shot reminders).
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

                        # Mark done so it doesn't fire again
                        mark_completed(store, user_id, task.key)

            except Exception as e:
                print_fn(f"[Reminder] Poll error: {e}")

            time.sleep(30)

    t = threading.Thread(target=loop, daemon=True)
    t.start()