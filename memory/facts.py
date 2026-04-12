import time
from langchain_core.messages import SystemMessage

from models import facts_llm
from prompts.memory import FACTS_EXTRACTION_PROMPT
from memory.utils import (
    format_messages, parse_json_array,
    semantic_search, full_scan, deduplicate, get_ns_lock, start_background_job
)


NAMESPACE    = lambda user_id: ("user", user_id, "facts")
ARCHIVE_NS   = lambda user_id: ("user", user_id, "facts_archive")

ARCHIVE_AFTER_DAYS = {
    "critical": None,
    "high":     None,
    "normal":   365,
    "low":      90,
}


def load_critical_facts(store, user_id: str) -> list:
    all_items = full_scan(store, NAMESPACE(user_id))
    return [i for i in all_items if i.value.get("importance") == "critical"]


def load_relevant_facts(store, user_id: str, query: str, active_project_names: list) -> list:
    ns = NAMESPACE(user_id)
    by_message = semantic_search(store, ns, query=query, limit=8)
    project_query = query + " " + " ".join(active_project_names)
    by_project = semantic_search(store, ns, query=project_query, limit=5)
    combined = deduplicate(by_message, by_project)
    return [i for i in combined if i.value.get("importance") != "critical"]


def load_archive_relevant(store, user_id: str, query: str) -> list:
    return semantic_search(store, ARCHIVE_NS(user_id), query=query, limit=3)


def save_facts(store, user_id: str, messages: list):
    start_background_job(
        _extract_and_save,
        store,
        user_id,
        messages,
        name="facts-save",
    )


def archive_stale_facts(store, user_id: str):
    ns         = NAMESPACE(user_id)
    archive_ns = ARCHIVE_NS(user_id)
    now        = time.time()

    try:
        all_facts = full_scan(store, ns)
        for item in all_facts:
            importance = item.value.get("importance", "normal")
            updated_at = item.value.get("updated_at", now)
            days_old   = (now - updated_at) / 86400
            threshold  = ARCHIVE_AFTER_DAYS.get(importance)

            if threshold and days_old > threshold:
                store.put(archive_ns, item.key, item.value)
                try:
                    store.delete(ns, item.key)
                except Exception as del_err:
                    print(f"[Facts] Delete failed for {item.key}: {del_err}")
                print(f"[Facts] Archived: {item.key} ({int(days_old)} days old)")

    except Exception as e:
        print(f"[Facts] Archive scan failed: {e}")


def format_critical_for_prompt(items: list) -> str:
    if not items:
        return "(none)"
    return "\n".join(f"- {i.value.get('content', '')}" for i in items)


def format_relevant_for_prompt(items: list) -> str:
    if not items:
        return "(none)"

    importance_rank = {"high": 0, "normal": 1, "low": 2}
    ranked = sorted(
        items,
        key=lambda i: (
            importance_rank.get(i.value.get("importance", "normal"), 1),
            -(i.value.get("updated_at", 0)),
        )
    )

    lines = []
    for item in ranked:
        content    = item.value.get("content", "")
        importance = item.value.get("importance", "normal")
        prefix     = "[high] " if importance == "high" else ""
        lines.append(f"- {prefix}{content}")

    return "\n".join(lines)


# ── Internal ───────────────────────────────────────────────────────────────────

def _extract_and_save(store, user_id: str, messages: list):
    # D2 fix: lock namespace before read-modify-write
    with get_ns_lock(NAMESPACE(user_id)):
        try:
            ns           = NAMESPACE(user_id)
            conversation = format_messages(messages)
            now          = time.time()

            # M2 fix: one semantic_search serves both dedup AND created_at lookup
            # No separate full_scan needed — existing_items covers both purposes
            existing_items = full_scan(store, ns)
            existing_text = _format_existing_for_prompt(existing_items)

            response = facts_llm.invoke([
                SystemMessage(content=FACTS_EXTRACTION_PROMPT.format(
                    existing_facts=existing_text or "(empty)",
                    conversation=conversation,
                ))
            ])

            extracted = parse_json_array(response.content)
            if not extracted:
                return

            for fact in extracted:
                action     = fact.get("action", "add").strip()
                category   = fact.get("category", "").strip()
                content    = fact.get("content", "").strip()
                importance = fact.get("importance", "normal").strip()

                if not category or not content:
                    continue
                existing_match = None
                for item in existing_items:
                    if item.key == category:
                        existing_match = item
                        break
                if existing_match is None:
                    existing_match = store.get(ns, category)
                if action == "skip":
                    continue

                store.put(ns, category, {
                    "content":    content,
                    "importance": importance,
                    "updated_at": now,
                    "created_at": existing_match.value.get("created_at", now) if existing_match else now,
                    "text":       content,
                })
                print(f"[Facts] {action.upper()}: {category}")

        except Exception as e:
            print(f"[Facts] Extraction failed: {e}")


def _get_created_at(existing_items: list, category: str, fallback: float) -> float:
    for item in existing_items:
        if item.key == category:
            return item.value.get("created_at", fallback)
    return fallback


def _format_existing_for_prompt(items: list) -> str:
    if not items:
        return "(empty)"
    lines = []
    for item in items:
        lines.append(
            f"- category: {item.key} | "
            f"content: {item.value.get('content', '')} | "
            f"importance: {item.value.get('importance', 'normal')}"
        )
    return "\n".join(lines)
