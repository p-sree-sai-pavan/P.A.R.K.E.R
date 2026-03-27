# memory/reminder_gate.py

import re
import json
from langchain_core.messages import SystemMessage
from datetime import datetime

from prompts.chat import REMINDER_GATE_PROMPT
from memory.utils import format_messages


# ── Public API ─────────────────────────────────────────────────────────────────

def run(llm, user_message: str, recent_history: list, due_tasks: list) -> dict:
    if not due_tasks:
        return {"approved_tasks": [], "suppressed": [], "complete": []}

    if _is_greeting(user_message) or _is_acknowledgment(user_message):
        suppressed = [
            {"key": t.key, "reason": "greeting suppression" if _is_greeting(user_message) else "acknowledgment suppression"}
            for t in due_tasks
        ]
        return {"approved_tasks": [], "suppressed": suppressed, "complete": []}

    due_text     = _format_due_for_gate(due_tasks)
    history_text = format_messages(recent_history[-12:])

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

_GREETINGS = {
    "hello", "hi", "hey", "sup", "yo", "hii", "heyy", "helloooo",
    "good morning", "good evening", "good night", "what's up", "whats up",
    "morning", "evening", "night", "howdy", "greetings",
}

_ACKS = {
    "ok", "okay", "k", "got it", "sure", "thanks", "thank you", "thx",
    "np", "no problem", "fine", "noted", "alright", "understood", "cool",
    "makes sense", "got", "yep", "yup", "right", "sounds good",
}


def _is_greeting(message: str) -> bool:
    msg = message.strip().lower().rstrip("!.,")
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
    """
    M3 fix: use regex to extract JSON from fence blocks reliably.
    Old split("```")[1] broke on multiple blocks or ` ```json ` with spaces.
    """
    try:
        text = text.strip()
        # Try regex extraction first
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}