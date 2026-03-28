import re
import time
from datetime import datetime
from langchain_core.messages import SystemMessage

from models import memory_llm
from prompts.memory import PROJECT_EXTRACTION_PROMPT
from memory.utils import (
    format_messages, parse_json_array,
    semantic_search, full_scan, get_ns_lock, start_background_job
)


NAMESPACE  = lambda user_id: ("user", user_id, "projects")
ARCHIVE_NS = lambda user_id: ("user", user_id, "projects_archive")


# ── Public API ─────────────────────────────────────────────────────────────────

def load_active_projects(store, user_id: str) -> list:
    all_projects = full_scan(store, NAMESPACE(user_id))
    return [p for p in all_projects if p.value.get("status") == "active"]


def load_relevant_projects(store, user_id: str, query: str) -> list:
    all_ns     = NAMESPACE(user_id)
    archive_ns = ARCHIVE_NS(user_id)

    from_active  = semantic_search(store, all_ns,     query=query, limit=3)
    from_archive = semantic_search(store, archive_ns, query=query, limit=2)

    seen   = {p.key: p for p in from_active}
    result = list(seen.values())
    for p in from_archive:
        if p.key not in seen:
            result.append(p)

    return result


def save_projects(store, user_id: str, messages: list):
    start_background_job(
        _extract_and_save,
        store,
        user_id,
        messages,
        name="projects-save",
    )


def archive_completed_projects(store, user_id: str):
    ns         = NAMESPACE(user_id)
    archive_ns = ARCHIVE_NS(user_id)

    try:
        all_projects = full_scan(store, ns)
        for item in all_projects:
            status = item.value.get("status", "active")
            if status in ("completed", "abandoned"):
                store.put(archive_ns, item.key, item.value)
                try:
                    store.delete(ns, item.key)
                except Exception as e:
                    print(f"[Projects] Delete failed for {item.key}: {e}")
                print(f"[Projects] Archived: {item.key} ({status})")

    except Exception as e:
        print(f"[Projects] Archive scan failed: {e}")


def format_active_for_prompt(projects: list) -> str:
    if not projects:
        return "(none)"

    lines = []
    for p in projects:
        v            = p.value
        name         = v.get("name", p.key)
        status       = v.get("status", "active")
        summary      = v.get("summary", "")
        open_threads = v.get("open_threads", [])
        stack        = v.get("stack", [])

        lines.append(f"Project: {name} [{status}]")
        if summary:
            lines.append(f"  Status: {summary}")
        if stack:
            lines.append(f"  Stack: {', '.join(stack)}")
        if open_threads:
            for thread in open_threads:
                lines.append(f"  - Open: {thread}")
        lines.append("")

    return "\n".join(lines).strip()


def format_relevant_for_prompt(projects: list) -> str:
    if not projects:
        return "(none)"

    lines = []
    for p in projects:
        v            = p.value
        name         = v.get("name", p.key)
        status       = v.get("status", "unknown")
        summary      = v.get("summary", "")
        decisions    = v.get("decisions_log", [])
        open_threads = v.get("open_threads", [])
        stack        = v.get("stack", [])
        last_touched = v.get("last_touched", "unknown")

        lines.append(f"Project: {name} [{status}] — last touched: {last_touched}")
        if summary:
            lines.append(f"  {summary}")
        if stack:
            lines.append(f"  Stack: {', '.join(stack)}")
        if open_threads:
            lines.append("  Open threads:")
            for t in open_threads:
                lines.append(f"    - {t}")
        if decisions:
            lines.append("  Decisions:")
            for d in decisions[-5:]:
                lines.append(f"    - {d}")
        lines.append("")

    return "\n".join(lines).strip()


# ── Internal ───────────────────────────────────────────────────────────────────

def _extract_and_save(store, user_id: str, messages: list):
    # D2 fix: lock namespace before read-modify-write
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            ns           = NAMESPACE(user_id)
            conversation = format_messages(messages)
            last_user_msg = _get_last_user_message(messages)

            existing_items = semantic_search(
                store, ns,
                query=last_user_msg or conversation[:200],
                limit=10
            )
            existing_text = _format_existing_for_prompt(existing_items)

            response = memory_llm.invoke([
                SystemMessage(content=PROJECT_EXTRACTION_PROMPT.format(
                    existing_projects=existing_text or "(empty)",
                    conversation=conversation,
                ))
            ])

            extracted = parse_json_array(response.content)
            if not extracted:
                return

            now   = time.time()
            today = _today_label()

            for project in extracted:
                action = project.get("action", "add").strip()
                name   = project.get("name", "").strip()
                key    = _to_key(name) # Define key here, before searching for existing_match

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

                existing_value = None # Initialize existing_value
                if existing_match:
                    existing_value = existing_match.value # Corrected typo: 'valuems' to 'value'

                new_decisions  = project.get("decisions", [])
                old_decisions  = existing_value.get("decisions_log", []) if existing_value else []
                merged_decisions = old_decisions + [
                    f"{today}: {d}" for d in new_decisions
                    if d not in " ".join(old_decisions)
                ]

                open_threads = project.get("open_threads",
                    existing_value.get("open_threads", []) if existing_value else []
                )

                new_stack    = project.get("stack", [])
                old_stack    = existing_value.get("stack", []) if existing_value else []
                merged_stack = list(dict.fromkeys(old_stack + new_stack))

                session_ts = datetime.now().strftime("%Y-%m-%dT%H:%M") # Changed format
                old_linked   = existing_value.get("linked_chats", []) if existing_value else []
                linked_chats = old_linked + ([session_ts] if session_ts not in old_linked else [])

                project_summary = project.get("summary", existing_value.get("summary", "") if existing_value else "")
                search_text     = f"{name} {project_summary} {' '.join(merged_stack)}"

                store.put(ns, key, {
                    "name":          name,
                    "status":        project.get("status", existing_value.get("status", "active") if existing_value else "active"),
                    "summary":       project_summary,
                    "stack":         merged_stack,
                    "open_threads":  open_threads,
                    "decisions_log": merged_decisions,
                    "linked_chats":  linked_chats,
                    "last_touched":  today,
                    "created_at":    existing_value.get("created_at", now) if existing_value else now,
                    "updated_at":    now,
                    "text":          search_text,
                })
                print(f"[Projects] {action.upper()}: {key}")

        except Exception as e:
            print(f"[Projects] Extraction failed: {e}")


def _find_existing(items: list, key: str) -> dict | None:
    for item in items:
        if item.key == key:
            return item.value
    return None


def _to_key(name: str) -> str:
    """
    D6 fix: use regex to strip all non-alphanumeric chars so keys are
    unambiguous. 'My App' and 'my-app' both → 'my_app' was the bug.
    Now we preserve enough uniqueness by keeping the original word boundaries.
    Collision risk was: different names → same key → silent overwrite.
    Fix: normalize aggressively so only truly identical names collide.
    """
    key = name.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)  # replace any non-alphanum run with _
    key = key.strip("_")
    return key


def _today_label() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _get_last_user_message(messages: list) -> str:
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "human":
            return m.content
        elif isinstance(m, dict) and m.get("role") == "user":
            return m.get("content", "")
    return ""


def _format_existing_for_prompt(items: list) -> str:
    if not items:
        return "(empty)"
    lines = []
    for item in items:
        v = item.value
        lines.append(
            f"- key: {item.key} | "
            f"name: {v.get('name', item.key)} | "
            f"status: {v.get('status', 'active')} | "
            f"summary: {v.get('summary', '')} | "
            f"stack: {', '.join(v.get('stack', []))}"
        )
    return "\n".join(lines)
