# memory/tasks/extractor.py
import time
import threading
from datetime import datetime
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts.memory import TASK_EXTRACTION_PROMPT
from memory.utils import (
    format_messages, parse_json_array,
    semantic_search, get_ns_lock
)
from memory.gate import evaluate_item
from .constants import NAMESPACE, CANDIDATE_NS, SNOOZE_BY_PRIORITY
from .actions import mark_completed


def save_tasks(store, user_id: str, messages: list):
    t = threading.Thread(
        target=_extract_and_save,
        args=(store, user_id, messages),
        daemon=True,
    )
    t.start()


def _extract_and_save(store, user_id: str, messages: list):
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            ns           = NAMESPACE(user_id)
            conversation = format_messages(messages)

            last_user_msg = ""
            for m in reversed(messages):
                if hasattr(m, "type") and m.type == "human":
                    last_user_msg = m.content
                    break
                elif isinstance(m, dict) and m.get("role") == "user":
                    last_user_msg = m.get("content", "")
                    break

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

            for task in extracted:
                action  = task.get("action", "add").strip()
                key     = task.get("key",    "").strip()
                content = task.get("content","").strip()

                if not key or not content:
                    continue

                if action == "skip":
                    continue

                if action == "complete":
                    mark_completed(store, user_id, key)
                    continue

                decision = evaluate_item({
                    "content":   content,
                    "type":      task.get("type"),
                    "priority":  task.get("priority"),
                    "condition": task.get("condition"),
                    "due":       task.get("due"),
                })

                if decision["decision"] == "reject":
                    print(f"[Tasks] REJECTED: {key} ({decision['reason']})")
                    continue

                # LOGIC ISSUE 1 FIX: fetch explicit exact key match from store if not in semantic hits
                existing_match = None
                for item in existing_items:
                    if item.key == key:
                        existing_match = item
                        break
                if existing_match is None:
                    existing_match = store.get(ns, key)
                
                created_at = existing_match.value.get("created_at", now) if existing_match else now

                existing_candidates = semantic_search(
                    store, CANDIDATE_NS(user_id),
                    query=content,
                    limit=3
                )

                promoted = False

                for cand in existing_candidates:
                    cand_value   = cand.value
                    cand_conf    = cand_value.get("confidence", 0)
                    cand_content = cand_value.get("content", "").lower()

                    key_match     = (cand.key == f"cand_{key}")
                    words_cand    = set(cand_content.split())
                    words_new     = set(content.lower().split())
                    overlap_ratio = len(words_cand & words_new) / max(1, len(words_cand | words_new))

                    if not (key_match or overlap_ratio > 0.4):
                        continue

                    if decision["confidence"] >= 0.8 or cand_conf >= 0.7:
                        # Promote condition
                        created_at = cand_value.get("created_at", created_at)

                        store.put(ns, key, _build_task_value(task, content, created_at, now, existing_match))

                        try:
                            store.delete(CANDIDATE_NS(user_id), cand.key)
                        except Exception:
                            pass

                        print(f"[Tasks] PROMOTED: {key}")
                        promoted = True
                        break

                if promoted:
                    continue

                if decision["decision"] == "candidate":
                    candidate_key = f"cand_{key}"
                    store.put(CANDIDATE_NS(user_id), candidate_key, {
                        "content":         content,
                        "type":            task.get("type", "reminder"),
                        "condition":       task.get("condition"),
                        "condition_hours": task.get("condition_hours"),
                        "condition_days":  task.get("condition_days"),
                        "keywords":        task.get("keywords", []),
                        "priority":        task.get("priority", "normal"),
                        "confidence":      decision["confidence"],
                        "status":          "candidate",
                        "created_at":      created_at,
                        "updated_at":      now,
                        "text":            content,
                    })
                    print(f"[Tasks] CANDIDATE: {key} ({decision['confidence']:.2f})")
                    continue

                store.put(ns, key, _build_task_value(task, content, created_at, now, existing_match))
                print(f"[Tasks] {action.upper()}: {key}")

        except Exception as e:
            print(f"[Tasks] Extraction failed: {e}")


def _build_task_value(task: dict, content: str, created_at: float, now: float, existing_match=None) -> dict:
    existing_value = existing_match.value if existing_match else {}
    priority = task.get("priority", existing_value.get("priority", "normal"))
    
    # LOGIC ISSUE 3 FIX: Start tracking `sessions_since_notify` fully elapsed right away to avoid initial wait
    sessions_to_wait = SNOOZE_BY_PRIORITY.get(priority, 2)

    return {
        "content":               content,
        "type":                  task.get("type", existing_value.get("type", "reminder")),
        "status":                existing_value.get("status", "pending"),
        "condition":             task.get("condition", existing_value.get("condition")),
        "condition_hours":       task.get("condition_hours", existing_value.get("condition_hours")),
        "condition_days":        task.get("condition_days", existing_value.get("condition_days")),
        "recurrence_rule":       task.get("recurrence_rule", existing_value.get("recurrence_rule")),
        "keywords":              task.get("keywords", existing_value.get("keywords", [])),
        "due":                   task.get("due", existing_value.get("due")),
        "priority":              priority,
        "fade_after_days":       task.get("fade_after_days", existing_value.get("fade_after_days")),
        "notify_count":          existing_value.get("notify_count", 0),
        "sessions_since_notify": existing_value.get("sessions_since_notify", sessions_to_wait),
        "last_notified":         existing_value.get("last_notified"),
        "completed_at":          existing_value.get("completed_at"),
        "created_at":            created_at,
        "updated_at":            now,
        "text":                  content + " " + " ".join(task.get("keywords", [])),
    }


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
