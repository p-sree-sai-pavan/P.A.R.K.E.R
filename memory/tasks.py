import time
import threading
from datetime import datetime
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts import TASK_EXTRACTION_PROMPT
from memory.utils import (
    format_messages, parse_json_array,
    semantic_search, full_scan
)


NAMESPACE  = lambda user_id: ("user", user_id, "tasks")
ARCHIVE_NS   = lambda user_id: ("user", user_id, "tasks_archive")
CANDIDATE_NS = lambda user_id: ("user", user_id, "candidates", "tasks")

# Snooze derived from priority — semantic, not arbitrary
SNOOZE_BY_PRIORITY = {
    "urgent": 0,   # resurface every session
    "high":   1,   # wait 1 session
    "normal": 2,   # wait 2 sessions
    "low":    5,   # wait 5 sessions
}


# ── Public API ─────────────────────────────────────────────────────────────────

def load_pending_tasks(store, user_id: str) -> list:
    """
    Plain scan — we need ALL pending tasks for condition checking.
    Semantic search would silently miss time-sensitive ones.
    """
    all_tasks = full_scan(store, NAMESPACE(user_id))
    return [
        t for t in all_tasks
        if t.value.get("status") in ("pending", "snoozed")
    ]


def check_conditions(store, user_id: str, message: str) -> list:
    """
    Core condition engine. Fully data-driven — no hardcoded assumptions.

    Two passes:
    Pass 1 — evaluate each pending task's stored condition against
              current time and current message.
    Pass 2 — semantic search for tasks related to what user said,
              catches tasks that don't have a condition but are relevant.

    Merged, deduplicated, filtered by snooze rules.
    Returns list of task items that should be surfaced this turn.
    """
    now          = datetime.now()
    current_hour = now.hour
    current_day  = now.weekday()   # 0=Monday, 6=Sunday
    message_low  = message.lower()

    pending    = load_pending_tasks(store, user_id)
    triggered  = {}

    # Pass 1 — condition-based
    for task in pending:
        v        = task.value
        priority = v.get("priority", "normal")

        # Snooze check — has enough sessions passed since last notify?
        sessions_to_wait   = SNOOZE_BY_PRIORITY.get(priority, 2)
        sessions_since     = v.get("sessions_since_notify", 999)
        if sessions_since < sessions_to_wait:
            continue

        if _condition_matches(v, message_low, current_hour, current_day, now):
            triggered[task.key] = task

    # Pass 2 — semantic relevance
    # Skip on greetings/acks — wastes a DB call and gate suppresses anyway.
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


def mark_completed(store, user_id: str, task_key: str):
    """
    For one-shot tasks: mark completed.
    For recurring tasks (recurrence_rule set): reset to pending.
    Without this, daily/weekly reminders permanently die after first completion.
    """
    ns    = NAMESPACE(user_id)
    items = full_scan(store, ns)

    for item in items:
        if item.key == task_key:
            updated         = item.value.copy()
            recurrence_rule = updated.get("recurrence_rule")

            if recurrence_rule:
                # Recurring — reset to pending for next cycle
                updated["status"]                = "pending"
                updated["completed_at"]          = None
                updated["sessions_since_notify"] = 0
                updated["last_notified"]         = time.time()
                store.put(ns, task_key, updated)
                print(f"[Tasks] RESET (recurring {recurrence_rule}): {task_key}")
            else:
                # One-shot — mark complete
                updated["status"]       = "completed"
                updated["completed_at"] = time.time()
                store.put(ns, task_key, updated)
                print(f"[Tasks] Completed: {task_key}")
            return

    print(f"[Tasks] mark_completed: key not found: {task_key}")


def increment_notify(store, user_id: str, task_key: str):
    """
    Called after a task is surfaced in a response.
    Increments notify_count, resets sessions_since_notify.
    """
    ns    = NAMESPACE(user_id)
    items = full_scan(store, ns)

    for item in items:
        if item.key == task_key:
            updated = item.value.copy()
            updated["notify_count"]          = updated.get("notify_count", 0) + 1
            updated["last_notified"]         = time.time()
            updated["sessions_since_notify"] = 0
            store.put(ns, task_key, updated)
            return  # stop scanning after update


def tick_sessions(store, user_id: str):
    """
    Called once on every session start.

    Two jobs:
    1. Increment sessions_since_notify for all pending/snoozed tasks.
    2. Archive completed tasks whose fade window has passed.
       fade_after_days is stored per task — no global assumption.
    """
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
                fade_after_days = updated.get("fade_after_days")  # per task

                # Only archive if task has a fade window AND it has passed
                if fade_after_days is not None and days_since > fade_after_days:
                    store.put(archive_ns, item.key, updated)
                    try:
                        store.delete(ns, item.key)
                    except Exception as e:
                        print(f"[Tasks] Delete failed for {item.key}: {e}")
                    print(f"[Tasks] Faded: {item.key}")

    except Exception as e:
        print(f"[Tasks] Tick failed: {e}")


def save_tasks(store, user_id: str, messages: list):
    """
    Extract new tasks from conversation and write to store.
    Detects completions — if user says they did something,
    marks matching task complete.
    Runs in background thread — non-blocking.
    """
    t = threading.Thread(
        target=_extract_and_save,
        args=(store, user_id, messages),
        daemon=True,
    )
    t.start()


def format_for_prompt(tasks: list) -> str:
    """
    Format triggered tasks for system prompt.
    Parker uses this to surface reminders naturally in conversation.
    """
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


# ── Condition engine ───────────────────────────────────────────────────────────

def _condition_matches(
    task_value: dict,
    message_low: str,
    current_hour: int,
    current_day: int,
    now: datetime,
) -> bool:
    """
    Fully data-driven condition check.
    Reads condition type and parameters from the task's stored data.
    No hardcoded time windows, no hardcoded keywords.
    """
    condition = task_value.get("condition")

    # Day filter — applies to all condition types if present
    condition_days = task_value.get("condition_days")
    if condition_days is not None:
        if current_day not in condition_days:
            return False

    if condition == "time_range":
        # condition_hours stored per task as [start, end]
        # LLM sets this at task creation based on what makes sense
        hours = task_value.get("condition_hours")
        if hours and len(hours) == 2:
            return hours[0] <= current_hour < hours[1]
        return False

    elif condition == "on_mention":
        # keywords stored per task — extracted by LLM at creation
        # from the task content itself
        keywords = task_value.get("keywords", [])
        return any(kw.lower() in message_low for kw in keywords)

    elif condition == "specific_time":
        due = task_value.get("due")
        if due:
            return _is_past_due(due, now)
        return False

    elif condition == "before_next_session":
        # Fires once per session — snooze logic in check_conditions
        # prevents it from triggering every message.
        return True

    elif condition is None or condition == "none":
        return False

    return False


def _is_past_due(due: str, now: datetime) -> bool:
    try:
        return now >= datetime.fromisoformat(due)
    except Exception:
        return False


# ── Internal extraction ────────────────────────────────────────────────────────

def _extract_and_save(store, user_id: str, messages: list):
    try:
        ns           = NAMESPACE(user_id)
        conversation = format_messages(messages)

        # Get last user message as search anchor
        last_user_msg = ""
        for m in reversed(messages):
            if hasattr(m, "type") and m.type == "human":
                last_user_msg = m.content
                break
            elif isinstance(m, dict) and m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        # Semantic search for related existing tasks
        existing_items = semantic_search(
            store, ns,
            query=last_user_msg or conversation[:200],
            limit=10
        )
        existing_text = _format_existing_for_prompt(existing_items)

        response = memory_llm.invoke([
            SystemMessage(content=TASK_EXTRACTION_PROMPT.format(
                current_time=datetime.now().isoformat(),
                existing_tasks=existing_text or "(empty)",
                conversation=conversation,
            ))
        ])

        extracted = parse_json_array(response.content)
        if not extracted:
            return

        now = time.time()

        from memory.gate import evaluate_item

        for task in extracted:
            action  = task.get("action", "add").strip()
            key     = task.get("key",    "").strip()
            content = task.get("content","").strip()

            if not key or not content:
                continue

            # ── Original behavior ────────────────────────────────
            if action == "skip":
                continue

            if action == "complete":
                mark_completed(store, user_id, key)
                continue

            # ── 🧠 MEMORY GATE ──────────────────────────────────
            decision = evaluate_item({
                "content": content,
                "type": task.get("type"),
                "priority": task.get("priority"),
                "condition": task.get("condition"),
            })

            if decision["decision"] == "reject":
                print(f"[Tasks] REJECTED: {key} ({decision['reason']})")
                continue

            # ── Preserve created_at ─────────────────────────────
            created_at = _get_created_at(existing_items, key, now)

            # ── 🔁 Candidate Promotion Check ─────────────────────
            existing_candidates = semantic_search(
                store,
                CANDIDATE_NS(user_id),
                query=content,
                limit=3
            )

            promoted = False

            for cand in existing_candidates:
                cand_value = cand.value
                cand_conf  = cand_value.get("confidence", 0)

                # Wait! We need to make sure this candidate is actually about the SAME task
                # semantic_search returns matches even if they aren't very similar
                cand_content = cand_value.get("content", "").lower()
                
                # Check 1: Key match
                key_match = (cand.key == f"cand_{key}")
                
                # Check 2: Strong word overlap
                words_cand = set(cand_content.split())
                words_new  = set(content.lower().split())
                overlap_ratio = len(words_cand & words_new) / max(1, len(words_cand | words_new))
                
                if not (key_match or overlap_ratio > 0.4):
                    continue  # This candidate is completely unrelated
                
                # Condition 1: Similar + confidence boost
                if decision["confidence"] >= 0.8 or cand_conf >= 0.7:
                
                    # 🔥 PROMOTE TO REAL TASK
                    created_at = cand_value.get("created_at", now)
            
                    store.put(ns, key, {
                        "content":             content,
                        "type":                task.get("type", "reminder"),
                        "status":              "pending",
                        "condition":           task.get("condition"),
                        "condition_hours":     task.get("condition_hours"),
                        "condition_days":      task.get("condition_days"),
                        "keywords":            task.get("keywords", []),
                        "due":                 task.get("due"),
                        "recurrence_rule":     task.get("recurrence_rule"),
                        "priority":            task.get("priority", "normal"),
                        "fade_after_days":     task.get("fade_after_days"),
                        "notify_count":        0,
                        "sessions_since_notify": 0,
                        "last_notified":       None,
                        "completed_at":        None,
                        "created_at":          created_at,
                        "updated_at":          now,
                        "text":                content + " " + " ".join(task.get("keywords", [])),
                    })
            
                    # remove candidate
                    try:
                        store.delete(CANDIDATE_NS(user_id), cand.key)
                    except:
                        pass
                    
                    print(f"[Tasks] PROMOTED: {key}")
                    promoted = True
                    break
                
            # If promoted, skip normal flow
            if promoted:
                continue

            # ── 🟡 Candidate Memory ─────────────────────────────
            if decision["decision"] == "candidate":
                candidate_key = f"cand_{key}"

                store.put(CANDIDATE_NS(user_id), candidate_key, {
                    "content":             content,
                    "type":                task.get("type", "reminder"),
                    "condition":           task.get("condition"),
                    "condition_hours":     task.get("condition_hours"),
                    "condition_days":      task.get("condition_days"),
                    "keywords":            task.get("keywords", []),
                    "priority":            task.get("priority", "normal"),
                    "confidence":          decision["confidence"],
                    "status":              "candidate",
                    "created_at":          created_at,
                    "updated_at":          now,
                    "text":                content,
                })

                print(f"[Tasks] CANDIDATE: {key} ({decision['confidence']:.2f})")
                continue

            # ── 🟢 REAL MEMORY (UNCHANGED CORE) ────────────────
            store.put(ns, key, {
                "content":             content,
                "type":                task.get("type", "reminder"),
                "status":              "pending",
                "condition":           task.get("condition"),
                "condition_hours":     task.get("condition_hours"),
                "condition_days":      task.get("condition_days"),
                "recurrence_rule":     task.get("recurrence_rule"),
                "keywords":            task.get("keywords", []),
                "due":                 task.get("due"),
                "priority":            task.get("priority", "normal"),
                "fade_after_days":     task.get("fade_after_days"),
                "notify_count":        0,
                "sessions_since_notify": 0,
                "last_notified":       None,
                "completed_at":        None,
                "created_at":          created_at,
                "updated_at":          now,
                "text":                content + " " + " ".join(task.get("keywords", [])),
            })

            print(f"[Tasks] {action.upper()}: {key}")

    except Exception as e:
        print(f"[Tasks] Extraction failed: {e}")

def _get_created_at(existing_items: list, key: str, fallback: float) -> float:
    for item in existing_items:
        if item.key == key:
            return item.value.get("created_at", fallback)
    return fallback


def _format_existing_for_prompt(items: list) -> str:
    if not items:
        return "(empty)"
    lines = []
    for item in items:
        v = item.value
        lines.append(
            f"- key: {item.key} | "
            f"content: {v.get('content', '')} | "
            f"status: {v.get('status', 'pending')} | "
            f"condition: {v.get('condition', 'none')} | "
            f"priority: {v.get('priority', 'normal')}"
        )
    return "\n".join(lines)