import time
from datetime import datetime
from langchain_core.messages import SystemMessage

from models import facts_llm as tasks_llm  # Reuse key 3 (facts/episodes key)
from prompts.memory import TASK_EXTRACTION_PROMPT
from memory.utils import (
    format_messages, parse_json_array,
    semantic_search, full_scan, get_ns_lock, start_background_job
)

NAMESPACE  = lambda user_id: ("user", user_id, "tasks")
ARCHIVE_NS = lambda user_id: ("user", user_id, "tasks_archive")


def load_active_tasks(store, user_id: str) -> list:
    all_tasks = full_scan(store, NAMESPACE(user_id))
    return [t for t in all_tasks if t.value.get("status") == "active"]


def load_relevant_tasks(store, user_id: str, query: str) -> list:
    ns = NAMESPACE(user_id)
    by_query = semantic_search(store, ns, query=query, limit=5)
    all_active = load_active_tasks(store, user_id)
    
    # Prioritize: 
    # 1. Urgent/High priority tasks (always return)
    # 2. Tasks due soon (within 24h)
    # 3. Semantically matching tasks
    urgent_high = [t for t in all_active if t.value.get("priority") in ("urgent", "high")]
    
    seen = {t.key for t in urgent_high}
    result = list(urgent_high)
    
    for t in by_query:
        if t.key not in seen and t.value.get("status") == "active":
            seen.add(t.key)
            result.append(t)
            
    return result


def save_tasks(store, user_id: str, messages: list):
    start_background_job(
        _extract_and_save,
        store,
        user_id,
        messages,
        name="tasks-save",
    )


def archive_completed_tasks(store, user_id: str):
    ns         = NAMESPACE(user_id)
    archive_ns = ARCHIVE_NS(user_id)

    try:
        all_tasks = full_scan(store, ns)
        for item in all_tasks:
            status = item.value.get("status", "active")
            if status == "completed":
                store.put(archive_ns, item.key, item.value)
                try:
                    store.delete(ns, item.key)
                except Exception as e:
                    print(f"[Tasks] Delete failed for {item.key}: {e}")
                print(f"[Tasks] Archived completed task: {item.key}")
    except Exception as e:
        print(f"[Tasks] Archive scan failed: {e}")


def format_tasks_for_prompt(tasks: list) -> str:
    if not tasks:
        return "(none)"

    lines = []
    # Sort: urgent -> high -> normal -> low, then by due date
    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    sorted_tasks = sorted(
        tasks,
        key=lambda t: (
            priority_order.get(t.value.get("priority", "normal"), 2),
            t.value.get("due") or "9999-12-31"
        )
    )

    for t in sorted_tasks:
        v = t.value
        content = v.get("content", "")
        priority = v.get("priority", "normal").upper()
        due = v.get("due")
        cond = v.get("condition")
        
        due_str = f" | Due: {due}" if due else ""
        cond_str = f" | Trigger: {cond}" if cond and cond != "none" else ""
        
        lines.append(f"- [{priority}] {content}{due_str}{cond_str}")

    return "\n".join(lines).strip()


def _extract_and_save(store, user_id: str, messages: list):
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            ns = NAMESPACE(user_id)
            conversation = format_messages(messages)
            current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            existing_items = full_scan(store, ns)
            existing_text = _format_existing_for_prompt(existing_items)

            response = tasks_llm.invoke([
                SystemMessage(content=TASK_EXTRACTION_PROMPT.format(
                    current_time=current_time,
                    existing_tasks=existing_text or "(empty)",
                    conversation=conversation,
                ))
            ])

            extracted = parse_json_array(response.content)
            if not extracted:
                return

            now = time.time()
            for task in extracted:
                action = task.get("action", "add").strip()
                key = task.get("key", "").strip()
                content = task.get("content", "").strip()

                if not key:
                    continue
                if action == "skip":
                    continue

                existing_match = None
                for item in existing_items:
                    if item.key == key:
                        existing_match = item
                        break
                if existing_match is None:
                    existing_match = store.get(ns, key)

                if action == "complete":
                    if existing_match:
                        val = existing_match.value.copy()
                        val["status"] = "completed"
                        val["updated_at"] = now
                        store.put(ns, key, val)
                        print(f"[Tasks] Completed: {key}")
                    continue

                # Store/Update task
                status = "active"
                store.put(ns, key, {
                    "content": content or (existing_match.value.get("content", "") if existing_match else ""),
                    "type": task.get("type", existing_match.value.get("type", "reminder") if existing_match else "reminder"),
                    "condition": task.get("condition", existing_match.value.get("condition", "none") if existing_match else "none"),
                    "condition_hours": task.get("condition_hours", existing_match.value.get("condition_hours") if existing_match else None),
                    "condition_days": task.get("condition_days", existing_match.value.get("condition_days") if existing_match else None),
                    "recurrence_rule": task.get("recurrence_rule", existing_match.value.get("recurrence_rule") if existing_match else None),
                    "keywords": task.get("keywords", existing_match.value.get("keywords", []) if existing_match else []),
                    "priority": task.get("priority", existing_match.value.get("priority", "normal") if existing_match else "normal"),
                    "due": task.get("due", existing_match.value.get("due") if existing_match else None),
                    "fade_after_days": task.get("fade_after_days", existing_match.value.get("fade_after_days") if existing_match else None),
                    "status": status,
                    "created_at": existing_match.value.get("created_at", now) if existing_match else now,
                    "updated_at": now,
                    "text": f"{content} {key} {task.get('priority', 'normal')}",
                })
                print(f"[Tasks] {action.upper()}: {key}")

        except Exception as e:
            print(f"[Tasks] Extraction failed: {e}")


def _format_existing_for_prompt(items: list) -> str:
    if not items:
        return "(empty)"
    lines = []
    for item in items:
        v = item.value
        lines.append(
            f"- key: {item.key} | "
            f"content: {v.get('content', '')} | "
            f"priority: {v.get('priority', 'normal')} | "
            f"due: {v.get('due') or 'none'} | "
            f"status: {v.get('status', 'active')}"
        )
    return "\n".join(lines)
