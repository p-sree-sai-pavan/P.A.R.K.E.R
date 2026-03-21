# memory/gate.py

def evaluate_item(task: dict) -> dict:
    content   = (task.get("content") or "").lower()
    action    = task.get("action", "add")
    condition = task.get("condition") or "none"
    task_type = task.get("type") or "reminder"
    due       = task.get("due")
    priority  = task.get("priority") or "normal"

    # ── 0. Always store explicit system actions ──────────
    if action == "complete":
        return {"decision": "store", "confidence": 1.0, "reason": "explicit_complete"}

    # ── 1. Always store if LLM gave a specific due time ──
    # "remind me in 1 min" → due is set → 100% intent
    if due:
        return {"decision": "store", "confidence": 1.0, "reason": "due_time_set"}

    # ── 2. Always store urgent/high priority ─────────────
    if priority in ("urgent", "high"):
        return {"decision": "store", "confidence": 0.95, "reason": "high_priority"}

    # ── 3. Always store time-bound conditions ────────────
    if condition in ("specific_time", "before_next_session"):
        return {"decision": "store", "confidence": 0.95, "reason": "time_bound"}

    # ── 4. Weak / speculative content ────────────────────
    weak_patterns = ["maybe", "thinking about", "might", "someday", "probably", "idea"]
    is_weak = any(w in content for w in weak_patterns)

    if is_weak:
        return {"decision": "reject", "confidence": 0.2, "reason": "speculative"}

    # ── 5. Garbage / too short ───────────────────────────
    if len(content.split()) < 2:
        return {"decision": "reject", "confidence": 0.1, "reason": "too_short"}

    # ── 6. Everything else — recurring reminders, goals ──
    # time_range, on_mention, none — store with normal confidence
    if condition in ("time_range", "on_mention"):
        return {"decision": "store", "confidence": 0.85, "reason": "conditioned_reminder"}

    # ── 7. Unconditioned tasks — candidate ───────────────
    # No due, no condition, not weak — user mentioned something vaguely
    return {"decision": "candidate", "confidence": 0.65, "reason": "unconditioned"}