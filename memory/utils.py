import re
import json
import threading


# ── Namespace locks (D2 fix) ───────────────────────────────────────────────────
# Prevents concurrent read-write races when multiple background threads
# write to the same namespace simultaneously.

_ns_locks: dict       = {}
_ns_locks_lock        = threading.Lock()

def get_ns_lock(namespace: tuple) -> threading.Lock:
    key = str(namespace)
    with _ns_locks_lock:
        if key not in _ns_locks:
            _ns_locks[key] = threading.Lock()
        return _ns_locks[key]


# ── Message formatting ─────────────────────────────────────────────────────────

def format_messages(messages: list) -> str:
    lines = []
    for m in messages:
        if hasattr(m, "type"):
            role = "User" if m.type == "human" else "Parker"
            lines.append(f"{role}: {m.content}")
        elif isinstance(m, dict):
            role = "User" if m.get("role") == "user" else "Parker"
            lines.append(f"{role}: {m.get('content', '')}")
    return "\n".join(lines)


# ── JSON parsing ───────────────────────────────────────────────────────────────

def parse_json_object(text: str) -> dict:
    try:
        text   = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def parse_json_array(text: str) -> list:
    try:
        text   = _strip_fences(text)
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ── Store helpers ──────────────────────────────────────────────────────────────

def semantic_search(store, namespace: tuple, query: str, limit: int) -> list:
    try:
        return store.search(namespace, query=query, limit=limit)
    except Exception as e:
        print(f"[Search] Semantic search failed on {namespace}: {e}")
        return []


def full_scan(store, namespace: tuple) -> list:
    try:
        return store.search(namespace)
    except Exception as e:
        print(f"[Search] Full scan failed on {namespace}: {e}")
        return []


def deduplicate(items_a: list, items_b: list) -> list:
    seen = {}
    for item in items_a:
        seen[item.key] = item
    for item in items_b:
        if item.key not in seen:
            seen[item.key] = item
    return list(seen.values())


# ── Internal ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """
    M3 fix: use regex instead of split() to reliably extract JSON
    from markdown fences regardless of spacing or multiple blocks.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text