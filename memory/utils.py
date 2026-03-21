import json


def format_messages(messages: list) -> str:
    """
    Shared message formatter used by all memory modules.
    Handles both LangChain message objects and raw dicts.
    """
    lines = []
    for m in messages:
        if hasattr(m, "type"):
            role = "User" if m.type == "human" else "Parker"
            lines.append(f"{role}: {m.content}")
        elif isinstance(m, dict):
            role = "User" if m.get("role") == "user" else "Parker"
            lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


def parse_json_object(text: str) -> dict:
    """
    Safely parse LLM response as a JSON object.
    Strips markdown fences if present.
    Returns empty dict on failure.
    """
    try:
        text = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def parse_json_array(text: str) -> list:
    """
    Safely parse LLM response as a JSON array.
    Strips markdown fences if present.
    Returns empty list on failure.
    """
    try:
        text = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def semantic_search(store, namespace: tuple, query: str, limit: int) -> list:
    """
    Semantic search with a query string.
    Use when you want relevance-ranked results.
    """
    try:
        return store.search(namespace, query=query, limit=limit)
    except Exception as e:
        print(f"[Search] Semantic search failed on {namespace}: {e}")
        return []


def full_scan(store, namespace: tuple) -> list:
    """
    Plain scan — returns all items in a namespace.
    Use when you need everything regardless of relevance:
    - Loading all critical facts
    - Loading all active projects
    - Loading all pending tasks for condition checking
    - Archival scans
    """
    try:
        return store.search(namespace)
    except Exception as e:
        print(f"[Search] Full scan failed on {namespace}: {e}")
        return []


def deduplicate(items_a: list, items_b: list) -> list:
    """
    Merge two result lists, removing duplicates by key.
    items_a takes priority (its values are kept on collision).
    """
    seen = {}
    for item in items_a:
        seen[item.key] = item
    for item in items_b:
        if item.key not in seen:
            seen[item.key] = item
    return list(seen.values())


def _strip_fences(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        # parts[1] is the content inside fences
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()