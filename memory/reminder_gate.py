# memory/reminder_gate.py
#
# The DISPLAY gate — decides which due tasks to show the user RIGHT NOW.
# Distinct from gate.py (the STORAGE gate — decides which tasks to store).
#
# Pipeline:
#   check_conditions() → [due tasks] → reminder_gate.run() → [approved tasks]
#
# Wire-up in your graph/main handler:
#
#   from memory.reminder_gate import run as reminder_gate
#   from memory.tasks import check_conditions, mark_completed, increment_notify
#
#   due_tasks     = check_conditions(store, user_id, user_message)
#   gate_result   = reminder_gate(memory_llm, user_message, recent_history, due_tasks)
#
#   for key in gate_result["complete"]:
#       mark_completed(store, user_id, key)
#
#   approved_tasks = gate_result["approved_tasks"]
#   # inject approved_tasks into system prompt as {approved_reminders}
#   # call increment_notify for each approved task AFTER response is sent

import json
from langchain_core.messages import SystemMessage
from datetime import datetime

from prompts import REMINDER_GATE_PROMPT
from memory.utils import format_messages


# ── Public API ─────────────────────────────────────────────────────────────────

def run(llm, user_message: str, recent_history: list, due_tasks: list) -> dict:
    """
    Run the reminder display gate.

    Args:
        llm:            The memory LLM (Qwen 3/7B — fast, cheap, schema-following)
        user_message:   The current raw user message
        recent_history: Last 6 turns as LangChain messages or dicts
        due_tasks:      Output of tasks.check_conditions()

    Returns:
        {
            "approved_tasks": [task_item, ...],   # task store items to show
            "suppressed":     [...],               # for logging only
            "complete":       ["key1", ...]        # mark these done immediately
        }
    """
    # Fast path — nothing due, skip the LLM call entirely
    if not due_tasks:
        return {"approved_tasks": [], "suppressed": [], "complete": []}

    # Fast path — social signals that always suppress everything
    # Do this in Python to avoid wasting an LLM call on obvious cases
    if _is_greeting(user_message) or _is_acknowledgment(user_message):
        suppressed = [
            {"key": t.key, "reason": "greeting suppression" if _is_greeting(user_message) else "acknowledgment suppression"}
            for t in due_tasks
        ]
        return {"approved_tasks": [], "suppressed": suppressed, "complete": []}

    # Build due reminders text for the prompt
    due_text     = _format_due_for_gate(due_tasks)
    history_text = format_messages(recent_history[-12:])  # last 6 turns = ~12 messages

    try:
        response = llm.invoke([
            SystemMessage(content=REMINDER_GATE_PROMPT.format(
                current_time=datetime.now().isoformat(),
                user_message=user_message,
                recent_history=history_text or "(no prior conversation)",
                due_reminders=due_text,
            ))
        ])

        parsed = _safe_parse(response.content)

        # Map approved keys back to actual task items
        approved_keys  = set(parsed.get("approved", []))
        approved_tasks = [t for t in due_tasks if t.key in approved_keys]
        complete_keys  = parsed.get("complete", [])
        suppressed     = parsed.get("suppressed", [])

        return {
            "approved_tasks": approved_tasks,
            "suppressed":     suppressed,
            "complete":       complete_keys,
        }

    except Exception as e:
        print(f"[ReminderGate] Failed: {e} — suppressing all reminders this turn")
        return {"approved_tasks": [], "suppressed": [], "complete": []}


def format_approved_for_prompt(approved_tasks: list) -> str:
    """
    Format approved tasks for injection into SYSTEM_PROMPT_TEMPLATE
    as {approved_reminders}.
    """
    if not approved_tasks:
        return "(none)"

    lines = []
    for task in approved_tasks:
        v        = task.value
        content  = v.get("content", "")
        priority = v.get("priority", "normal")
        prefix   = "[urgent] " if priority == "urgent" else (
                   "[high] "   if priority == "high"   else ""
        )
        lines.append(f"- {prefix}{content}")

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────────────────

# These lists are intentionally broad — false positives (suppressing a real
# query that starts with "hey") are far less harmful than false negatives
# (nagging the user on a greeting).

_GREETINGS = {
    "hello", "hi", "hey", "sup", "yo", "hii", "heyy", "helloooo",
    "good morning", "good evening", "good night", "what's up", "whats up",
    "morning", "evening", "night", "howdy", "greetings",
}

_ACKS = {
    "ok", "okay", "k", "got it", "sure", "thanks", "thank you", "thx",
    "np", "no problem", "fine", "noted", "alright", "understood", "cool",
    "makes sense", "got", "ок", "yep", "yup", "right", "sounds good",
}


def _is_greeting(message: str) -> bool:
    msg = message.strip().lower().rstrip("!.,")
    # Exact match OR starts with a greeting word
    if msg in _GREETINGS:
        return True
    for g in _GREETINGS:
        if msg.startswith(g + " ") or msg.startswith(g + ","):
            return True
    return False


def _is_acknowledgment(message: str) -> bool:
    msg = message.strip().lower().rstrip("!.,")
    return msg in _ACKS


def _format_due_for_gate(tasks: list) -> str:
    if not tasks:
        return "(none)"
    lines = []
    for t in tasks:
        v = t.value
        lines.append(
            f"- key: {t.key} | "
            f"content: {v.get('content', '')} | "
            f"condition: {v.get('condition', 'none')} | "
            f"due: {v.get('due', 'null')} | "
            f"priority: {v.get('priority', 'normal')}"
        )
    return "\n".join(lines)


def _safe_parse(text: str) -> dict:
    try:
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}